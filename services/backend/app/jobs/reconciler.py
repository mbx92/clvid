from __future__ import annotations

import logging
import shutil
import time
from datetime import timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.domain.models import Asset, Export, Job, JobAttempt, OutboxEvent, Project, utcnow
from app.storage.local import LocalStorage

log = logging.getLogger("clipper.reconciler")


def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def reconcile_once() -> dict:
    settings, now = get_settings(), utcnow()
    recovered, republished = 0, 0
    with session_scope() as db:
        stale = db.execute(select(Job.id, Job.project_id).where(Job.status.in_(("running", "cancel_requested")),
                                             Job.lease_expires_at < now)).all()
        for job_id, project_id in stale:
            project = db.scalar(select(Project).where(Project.id == project_id).with_for_update(skip_locked=True))
            if not project:
                continue
            job = db.scalar(select(Job).where(Job.id == job_id, Job.status.in_(("running", "cancel_requested")),
                                               Job.lease_expires_at < now).with_for_update(skip_locked=True))
            if not job:
                continue
            cancelled = job.status == "cancel_requested" or project.lifecycle_state != "active" and job.kind != "delete_assets"
            attempt = db.scalar(select(JobAttempt).where(JobAttempt.job_id == job.id, JobAttempt.attempt == job.attempt))
            if attempt:
                attempt.outcome, attempt.finished_at = "worker_lost", now
            job.lease_expires_at, job.progress = None, None
            if cancelled:
                job.status, job.finished_at = "cancelled", now
                job.error_code, job.error_message = "worker_lost", "Worker terputus setelah pembatalan diminta. Hasil tidak dipublikasikan."
            elif job.attempt < settings.job_max_attempts:
                job.status = "queued"
                db.add(OutboxEvent(job_id=job.id, payload={"job_id": job.id}))
            else:
                job.status, job.finished_at = "failed", now
                job.error_code, job.error_message = "worker_lost", "Worker berhenti sebelum pekerjaan selesai. Batas percobaan tercapai; periksa konfigurasi server."
                if job.kind not in ("render", "track_preview") and project.lifecycle_state == "active":
                    project.status, project.error_message = ("ready" if job.kind == "analyze" else "failed"), job.error_message
            export = db.scalar(select(Export).where(Export.job_id == job.id))
            if export:
                export.status = job.status
            recovered += 1
        # Redis may lose queued deliveries after a restart. PostgreSQL remains
        # authoritative. At-least-once redelivery is safe because claim is fenced.
        queued = db.scalars(select(Job).where(Job.status == "queued")).all()
        threshold = now - timedelta(seconds=max(120, settings.job_lease_seconds * 2))
        for job in queued:
            newest = db.scalar(select(OutboxEvent).where(OutboxEvent.job_id == job.id).order_by(OutboxEvent.created_at.desc()).limit(1))
            if newest and newest.dispatched_at and as_utc(newest.dispatched_at) < threshold:
                db.add(OutboxEvent(job_id=job.id, payload={"job_id": job.id}))
                republished += 1
    return {"recovered": recovered, "republished": republished}


def cleanup_once() -> dict:
    settings, storage, now = get_settings(), LocalStorage(), time.time()
    removed = 0
    with session_scope() as db:
        active_ids = set(db.scalars(select(Job.id).where(Job.status.in_(("queued", "running", "cancel_requested")))))
        active_projects = set(db.scalars(select(Job.project_id).where(Job.status.in_(("queued", "running", "cancel_requested")))))
        registered = {asset.storage_key for asset in db.scalars(select(Asset))}
        attempt_finished = {(attempt.job_id, str(attempt.attempt)): as_utc(attempt.finished_at).timestamp()
                            for attempt in db.scalars(select(JobAttempt).where(JobAttempt.finished_at.is_not(None)))}
        cutoff = utcnow() - timedelta(seconds=settings.partial_upload_ttl_seconds)
        uploads = db.scalars(select(Asset).where(Asset.state == "uploading", Asset.created_at < cutoff)).all()
        for asset in uploads:
            project = db.scalar(select(Project).where(Project.id == asset.project_id).with_for_update(skip_locked=True))
            if not project:
                continue
            upload_key = asset.meta_json.get("upload_key")
            partial = storage.path(upload_key) if upload_key else None
            if partial and partial.exists() and now - partial.stat().st_mtime < settings.partial_upload_ttl_seconds:
                continue
            if partial:
                partial.unlink(missing_ok=True)
            asset.state = "failed"
            if project.lifecycle_state == "active" and project.source_asset_id == asset.id:
                project.source_asset_id, project.status = None, "empty"
                project.error_message = "Upload terputus atau kedaluwarsa. Pilih file dan ulangi upload dari awal."
    scratch_root = storage.path("scratch")
    if scratch_root.exists():
        for job_dir in scratch_root.iterdir():
            if job_dir.is_symlink() or not job_dir.is_dir() or job_dir.name in active_ids:
                continue
            for attempt_dir in job_dir.iterdir():
                if attempt_dir.is_symlink() or not attempt_dir.is_dir():
                    continue
                marker = attempt_dir / ".terminal"
                modified = marker.stat().st_mtime if marker.exists() else attempt_finished.get((job_dir.name, attempt_dir.name), attempt_dir.stat().st_mtime)
                if now - modified > settings.scratch_ttl_seconds:
                    shutil.rmtree(attempt_dir)
                    removed += 1
            if not any(job_dir.iterdir()):
                job_dir.rmdir()
    # API upload files live under uploads and have no committed asset yet.
    upload_root = storage.path("uploads")
    if upload_root.exists():
        for path in upload_root.glob("*.part"):
            if not path.is_symlink() and now - path.stat().st_mtime > settings.partial_upload_ttl_seconds:
                path.unlink(missing_ok=True)
                removed += 1
    # A transaction rollback can leave a published file without an Asset row.
    # Preserve registered assets and all directories with active jobs.
    projects_root = storage.path("projects")
    if projects_root.exists():
        for project_dir in projects_root.iterdir():
            if not project_dir.is_dir() or project_dir.is_symlink() or project_dir.name in active_projects:
                continue
            for path in project_dir.rglob("*"):
                if path.is_symlink() or not path.is_file():
                    continue
                key = path.relative_to(storage.root).as_posix()
                if key not in registered and now - path.stat().st_mtime > settings.scratch_ttl_seconds:
                    storage.path(key).unlink(missing_ok=True)
                    removed += 1
    return {"removed": removed}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    last_cleanup = 0
    while True:
        try:
            reconcile_once()
            if time.monotonic() - last_cleanup >= 300:
                cleanup_once()
                last_cleanup = time.monotonic()
        except Exception:
            log.error("Reconciler unavailable; retrying")
        time.sleep(get_settings().reconcile_interval_seconds)


if __name__ == "__main__":
    main()
