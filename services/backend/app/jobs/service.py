from __future__ import annotations

import hashlib
import json

from sqlalchemy import func, select

from app.config import get_settings
from app.domain.limits import processing_limits, can_retry_after_limit_increase
from app.domain.models import Asset, Job, JobRequest, OutboxEvent, Project, User, utcnow

ACTIVE = ("queued", "running", "cancel_requested")
KINDS = {"subtitle_translate", "story_generate", "story_render", "story_produce", "import_url", "validate", "prepare_preview", "transcribe", "analyze", "subtitle_generate", "track_preview", "render", "delete_assets"}


class JobConflict(ValueError):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def fingerprint(kind: str, inputs: dict) -> str:
    content = {key: value for key, value in inputs.items() if key != "export_id"}
    canonical = json.dumps({"kind": kind, "input": content, "pipeline": get_settings().pipeline_version},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_job(db, project: Project, kind: str, input_json: dict, idempotency_key: str | None = None) -> Job:
    """Caller owns the transaction; job + outbox always commit atomically."""
    if kind not in KINDS:
        raise JobConflict("invalid_job", "Jenis pekerjaan tidak dikenal.")
    project = db.scalar(select(Project).where(Project.id == project.id).with_for_update())
    if not project or project.lifecycle_state != "active" and kind != "delete_assets":
        raise JobConflict("project_deleting", "Proyek sedang dihapus dan tidak menerima pekerjaan baru.")
    value = fingerprint(kind, input_json)
    if idempotency_key:
        request = db.scalar(select(JobRequest).where(JobRequest.project_id == project.id, JobRequest.kind == kind,
                                                     JobRequest.idempotency_key == idempotency_key))
        if request:
            if request.input_fingerprint != value:
                raise JobConflict("idempotency_conflict", "Kunci permintaan sudah digunakan untuk parameter berbeda.")
            return db.get(Job, request.job_id)
        existing = db.scalar(select(Job).where(Job.project_id == project.id, Job.kind == kind,
                                               Job.idempotency_key == idempotency_key))
        if existing:
            if existing.input_fingerprint != value:
                raise JobConflict("idempotency_conflict", "Kunci permintaan sudah digunakan untuk parameter berbeda.")
            return existing
    existing = db.scalar(select(Job).where(Job.project_id == project.id, Job.input_fingerprint == value))
    if existing:
        if idempotency_key:
            db.add(JobRequest(project_id=project.id, kind=kind, idempotency_key=idempotency_key,
                              input_fingerprint=value, job_id=existing.id))
        return existing
    db.scalar(select(User).where(User.id == project.owner_id).with_for_update())
    active_count = db.scalar(select(func.count(Job.id)).join(Project).where(Project.owner_id == project.owner_id,
                                                                            Job.status.in_(ACTIVE)))
    if kind != "delete_assets" and active_count >= get_settings().max_active_jobs_per_user:
        raise JobConflict("too_many_jobs", "Terlalu banyak pekerjaan aktif. Tunggu pekerjaan selesai atau batalkan salah satunya.")
    job = Job(project_id=project.id, kind=kind, stage=kind, status="queued", input_json=input_json,
              input_fingerprint=value, idempotency_key=idempotency_key,
              limits_json=processing_limits(db, project.owner_id))
    db.add(job)
    db.flush()
    if idempotency_key:
        db.add(JobRequest(project_id=project.id, kind=kind, idempotency_key=idempotency_key,
                          input_fingerprint=value, job_id=job.id))
    db.add(OutboxEvent(job_id=job.id, payload={"job_id": job.id}))
    return job


def retry_job(db, job: Job) -> Job:
    job = db.scalar(select(Job).where(Job.id == job.id).with_for_update())
    if job.status not in ("failed", "cancelled"):
        raise JobConflict("job_not_retryable", "Hanya pekerjaan gagal atau dibatalkan yang dapat dicoba kembali.")
    project = db.get(Project, job.project_id)
    if project.lifecycle_state != "active" and job.kind != "delete_assets":
        raise JobConflict("project_deleting", "Proyek sedang dihapus.")
    limits = processing_limits(db, project.owner_id)
    if job.attempt >= get_settings().job_max_attempts and not can_retry_after_limit_increase(job, limits):
        raise JobConflict("job_retry_limit", "Batas percobaan tercapai; periksa konfigurasi server.")
    if job.kind == "import_url":
        source = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
        other = db.scalar(select(Job.id).where(Job.project_id == project.id, Job.kind == "import_url", Job.id != job.id, Job.status.in_(ACTIVE)))
        if other or source and source.state not in ("failed", "invalid"):
            raise JobConflict("source_exists", "Video sumber atau impor lain sudah tersedia. Buat proyek baru untuk URL ini.")
        project.status, project.error_message = "importing", None
    job.status, job.progress = "queued", None
    job.limits_json = limits
    job.error_code, job.error_message = None, None
    job.lease_expires_at, job.finished_at = None, None
    db.add(OutboxEvent(job_id=job.id, payload={"job_id": job.id}))
    return job


def cancel_job(db, job: Job) -> Job:
    job = db.scalar(select(Job).where(Job.id == job.id).with_for_update())
    if job.kind == "delete_assets":
        raise JobConflict("deletion_not_cancellable", "Penghapusan proyek yang sudah dimulai tidak dapat dibatalkan.")
    if job.status == "queued":
        job.status, job.finished_at = "cancelled", utcnow()
        if job.kind == "import_url":
            project = db.get(Project, job.project_id)
            project.status = "empty"
    elif job.status == "running":
        job.status = "cancel_requested"
    return job
