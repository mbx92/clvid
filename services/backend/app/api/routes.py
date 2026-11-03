import hashlib
import time
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from app.api.auth import current_user
from app.api.errors import AppError
from app.api.schemas import ClipInput, ClipPatch, ExportInput, ProcessInput, ProjectInput, SourceUrlInput, TrackingPreviewInput, ProcessingSettingsInput, SubtitleGenerateInput, RemotionEffects
from app.api.serializers import ACTIVE, asset_data, clip_data, cue_data, export_data, job_data, project_data
from app.ai.subtitle_recovery_config import recovery_signature
from app.config import get_settings
from app.db import get_db
from app.domain.limits import processing_limits, effective_settings, can_retry_after_limit_increase, MAX_CLIP_MS, MAX_SOURCE_SECONDS, MAX_SOURCE_BYTES
from app.domain.models import ProcessingSettings
from app.domain.models import Publication
from app.domain.editing import remap_cues, validate_bounds, validate_cues
from app.domain.subtitle_timing import source_words, subtitle_events
from app.domain.models import Asset, Clip, ClipRevision, Export, Job, JobAttempt, JobRequest, OutboxEvent, Project, ProviderUsage, SubtitleCue, Transcript, TranscriptSegment, User, new_id, utcnow
from app.media.process import MediaError
from app.media.remote_guard import validate_url
from app.media.subtitles import transcript_cues, validate_subtitle_layout
from app.jobs.tracking_cache import analysis_metadata, make_tracking_spec, ready_preview
from app.storage.local import LocalStorage

router = APIRouter(tags=["workspace"])


def validate_video_effects(style: dict, duration_ms: int):
    # Effects belong to the saved clip, independently of caption visibility.
    # Revalidate persisted JSON for exports as well as incoming editor drafts.
    try:
        effects = RemotionEffects.model_validate(style.get("remotion_effects", {}))
    except ValidationError as exc:
        raise AppError(422, "INVALID_REMOTION_EFFECTS", "Periksa pengaturan efek Remotion: teks intro/outro aktif wajib diisi dan rentang zoom harus valid.") from exc
    for index, zoom in enumerate(effects.zooms):
        if zoom.end_ms > duration_ms:
            raise AppError(422, "REMOTION_EFFECT_BOUNDS", f"Zoom {index + 1} melewati akhir klip. Sesuaikan waktunya setelah mengubah batas klip.")


def own_project(db, user, project_id, lock=False, allow_deleting=False):
    query = select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    if not allow_deleting:
        query = query.where(Project.lifecycle_state == "active")
    project = db.scalar(query.with_for_update() if lock else query)
    if not project:
        raise AppError(404, "PROJECT_NOT_FOUND", "Proyek tidak ditemukan atau akses telah dicabut.")
    return project


def own_clip(db, user, clip_id, lock=False):
    clip = db.get(Clip, clip_id)
    if not clip:
        raise AppError(404, "CLIP_NOT_FOUND", "Klip tidak ditemukan.")
    project = own_project(db, user, clip.project_id, lock=lock)
    if lock:
        clip = db.scalar(select(Clip).where(Clip.id == clip_id).with_for_update().execution_options(populate_existing=True))
    return clip, project


def own_job(db, user, job_id, lock=False):
    job = db.get(Job, job_id)
    if not job:
        raise AppError(404, "JOB_NOT_FOUND", "Pekerjaan tidak ditemukan.")
    project = own_project(db, user, job.project_id, lock=lock, allow_deleting=job.kind == "delete_assets")
    if lock:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    return job, project


def source_for_edit(db, project):
    source = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
    if not source or source.state != "ready" or not source.meta_json.get("duration_ms"):
        raise AppError(409, "SOURCE_NOT_READY", "Tunggu hingga validasi video selesai.")
    return source


def queue_job(db, project, kind, params, key):
    from app.jobs.service import create_job
    if key and len(key) > 128:
        raise AppError(422, "IDEMPOTENCY_KEY_INVALID", "Idempotency key terlalu panjang.")
    try:
        return create_job(db, project, kind, params, key)
    except ValueError as exc:
        status = 429 if getattr(exc, "code", "") == "too_many_jobs" else 409
        raise AppError(status, str(getattr(exc, "code", "JOB_CONFLICT")).upper(), str(exc)) from exc


def action_request(db, project, job, action, key):
    """Return True for a replay; a new key is committed with the state mutation."""
    if not key:
        return False
    if len(key) > 128:
        raise AppError(422, "IDEMPOTENCY_KEY_INVALID", "Idempotency key terlalu panjang.")
    fingerprint = hashlib.sha256(f"{action}:{job.id}".encode()).hexdigest()
    existing = db.scalar(select(JobRequest).where(JobRequest.project_id == project.id, JobRequest.kind == action, JobRequest.idempotency_key == key))
    if existing:
        if existing.input_fingerprint != fingerprint:
            raise AppError(409, "IDEMPOTENCY_CONFLICT", "Kunci permintaan sudah digunakan untuk pekerjaan berbeda.")
        return True
    db.add(JobRequest(project_id=project.id, kind=action, idempotency_key=key, input_fingerprint=fingerprint, job_id=job.id))
    return False


@router.get("/projects")
def projects(search: str = "", status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Project).where(Project.owner_id == user.id, Project.lifecycle_state == "active")
    if search:
        query = query.where(Project.name.icontains(search, autoescape=True))
    if status:
        query = query.where(Project.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Project.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [project_data(db, p) for p in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/media")
def media_library(search: str = "", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """List the current user's stored videos without exposing filesystem paths."""
    query = select(Project).where(
        Project.owner_id == user.id,
        Project.lifecycle_state == "active",
        Project.source_asset_id.is_not(None),
    )
    if search:
        query = query.where(Project.name.icontains(search, autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    projects = list(db.scalars(query.order_by(Project.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)))

    project_stats: dict[str, dict[str, int]] = {}
    if projects:
        rows = db.execute(
            select(Asset.project_id, Asset.kind, func.count(Asset.id), func.coalesce(func.sum(Asset.bytes), 0))
            .where(Asset.project_id.in_([project.id for project in projects]), Asset.state != "deleted")
            .group_by(Asset.project_id, Asset.kind)
        )
        for project_id, kind, count, size in rows:
            stats = project_stats.setdefault(project_id, {"file_count": 0, "video_count": 0, "source_bytes": 0, "preview_bytes": 0, "export_bytes": 0, "subtitle_bytes": 0, "total_bytes": 0})
            size = int(size or 0)
            stats["file_count"] += int(count or 0)
            stats["total_bytes"] += size
            if kind in ("source", "preview", "export_mp4"):
                stats["video_count"] += int(count or 0)
            if kind == "source":
                stats["source_bytes"] += size
            elif kind == "preview":
                stats["preview_bytes"] += size
            elif kind == "export_mp4":
                stats["export_bytes"] += size
            elif kind == "export_srt":
                stats["subtitle_bytes"] += size

    summary = {"project_count": 0, "video_count": 0, "source_bytes": 0, "preview_bytes": 0, "export_bytes": 0, "subtitle_bytes": 0, "total_bytes": 0}
    summary["project_count"] = int(db.scalar(select(func.count()).select_from(Project).where(
        Project.owner_id == user.id, Project.lifecycle_state == "active", Project.source_asset_id.is_not(None)
    )) or 0)
    summary_rows = db.execute(
        select(Asset.kind, func.count(Asset.id), func.coalesce(func.sum(Asset.bytes), 0))
        .join(Project, Project.id == Asset.project_id)
        .where(Project.owner_id == user.id, Project.lifecycle_state == "active", Project.source_asset_id.is_not(None), Asset.state != "deleted")
        .group_by(Asset.kind)
    )
    for kind, count, size in summary_rows:
        size = int(size or 0)
        summary["total_bytes"] += size
        if kind in ("source", "preview", "export_mp4"):
            summary["video_count"] += int(count or 0)
        if kind == "source":
            summary["source_bytes"] += size
        elif kind == "preview":
            summary["preview_bytes"] += size
        elif kind == "export_mp4":
            summary["export_bytes"] += size
        elif kind == "export_srt":
            summary["subtitle_bytes"] += size

    items = []
    for project in projects:
        source = db.get(Asset, project.source_asset_id)
        stats = project_stats.get(project.id, {"file_count": 0, "video_count": 0, "source_bytes": 0, "preview_bytes": 0, "export_bytes": 0, "subtitle_bytes": 0, "total_bytes": 0})
        items.append({
            "project_id": project.id,
            "project_name": project.name,
            "status": project.status,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "source_asset": asset_data(source),
            **stats,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size, "summary": summary}


@router.post("/projects", status_code=201)
def create_project(body: ProjectInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = Project(owner_id=user.id, name=body.name)
    db.add(project)
    db.commit()
    return project_data(db, project, True)


@router.get("/projects/{project_id}")
def project_detail(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return project_data(db, own_project(db, user, project_id), True)


@router.patch("/projects/{project_id}")
def rename_project(project_id: str, body: ProjectInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id, lock=True)
    project.name = body.name
    db.commit()
    return project_data(db, project, True)


@router.delete("/projects/{project_id}", status_code=202)
def delete_project(project_id: str, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id, lock=True, allow_deleting=True)
    if project.lifecycle_state == "deleted":
        completed = db.scalar(select(Job).where(Job.project_id == project.id, Job.kind == "delete_assets").order_by(Job.created_at.desc()).limit(1))
        if not completed:
            raise AppError(404, "PROJECT_NOT_FOUND", "Proyek sudah dihapus.")
        return job_data(completed)
    publications=list(db.scalars(select(Publication).where(Publication.project_id==project.id).with_for_update()))
    if any(p.status in ('uploading','processing') for p in publications):
        raise AppError(409,'PUBLICATION_BUSY','Tunggu publikasi sosial yang sedang dikirim selesai sebelum menghapus proyek.')
    for publication in publications:
        if publication.status in ('draft','scheduled'): publication.status='cancelled'; publication.version+=1
    project.lifecycle_state = "deleting"
    for job in db.scalars(select(Job).where(Job.project_id == project.id, Job.status.in_(ACTIVE), Job.kind != "delete_assets").with_for_update()):
        if job.status == "queued":
            job.status, job.finished_at = "cancelled", utcnow()
        else:
            job.status = "cancel_requested"
    job = queue_job(db, project, "delete_assets", {}, idempotency_key)
    db.commit()
    return job_data(job)


@router.post("/projects/{project_id}/source-url", status_code=202)
def import_source_url(project_id: str, body: SourceUrlInput, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id, lock=True)
    try:
        url = validate_url(body.url)
    except MediaError as exc:
        raise AppError(422, exc.code.upper(), exc.message) from exc
    params = {"url": url}
    if idempotency_key and db.scalar(select(JobRequest).where(JobRequest.project_id == project.id, JobRequest.kind == "import_url", JobRequest.idempotency_key == idempotency_key)):
        job = queue_job(db, project, "import_url", params, idempotency_key)
        db.commit()
        return job_data(job)
    source = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
    if source and source.state not in ("failed", "invalid"):
        raise AppError(409, "SOURCE_EXISTS", "Proyek ini sudah memiliki video atau upload masih berlangsung.")
    active = db.scalar(select(Job).where(Job.project_id == project.id, Job.kind == "import_url", Job.status.in_(ACTIVE)))
    if active and active.input_json != params:
        raise AppError(409, "SOURCE_IMPORT_ACTIVE", "Tunggu atau batalkan impor URL yang masih berjalan.")
    job = queue_job(db, project, "import_url", params, idempotency_key)
    if job.status in ACTIVE:
        project.status, project.error_message = "importing", None
    db.commit()
    return job_data(job)


@router.post("/projects/{project_id}/source", status_code=202)
async def upload_source(project_id: str, request: Request, x_filename: str | None = Header(None), idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    config = effective_settings(db, user.id)
    project = own_project(db, user, project_id, lock=True)
    if db.scalar(select(Job.id).where(Job.project_id == project.id, Job.kind == "import_url", Job.status.in_(ACTIVE))):
        raise AppError(409, "SOURCE_IMPORT_ACTIVE", "Tunggu atau batalkan impor URL sebelum mengunggah file.")
    source = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
    if source and source.state not in ("failed", "invalid"):
        raise AppError(409, "SOURCE_EXISTS", "Proyek ini sudah memiliki video atau upload masih berlangsung.")
    length = request.headers.get("content-length")
    if length:
        try:
            length = int(length)
        except ValueError:
            raise AppError(400, "UPLOAD_LENGTH", "Ukuran upload tidak valid.")
        if length > config.max_upload_bytes:
            raise AppError(413, "UPLOAD_TOO_LARGE", "Ukuran video melebihi batas upload.")
    storage = LocalStorage()
    if storage.free_bytes() < config.min_free_disk_bytes + (length or 0):
        raise AppError(507, "DISK_FULL", "Ruang penyimpanan tidak cukup untuk menerima video.")
    key = storage.new_key(project.id, ".mp4")
    upload_key = f"uploads/{new_id()}.part"
    temporary = storage.prepare(upload_key)
    asset = Asset(id=new_id(), project_id=project.id, kind="source", storage_key=key, mime="video/mp4", state="uploading", meta_json={"filename": Path(unquote(x_filename or "video.mp4").replace("\\", "/")).name[:200], "upload_key": upload_key})
    db.add(asset)
    db.flush()
    asset_id = asset.id
    project.source_asset_id, project.status, project.error_message = asset_id, "uploading", None
    db.commit()
    size = 0
    checksum = hashlib.sha256()
    last_lifecycle_check = time.monotonic()
    try:
        with temporary.open("xb") as output:
            async for chunk in request.stream():
                if time.monotonic() - last_lifecycle_check >= 1:
                    current_state = db.execute(select(Project.lifecycle_state, Project.source_asset_id).where(Project.id == project_id)).one_or_none()
                    db.rollback()  # Never hold a read transaction during network transfer.
                    if not current_state or current_state.lifecycle_state != "active" or current_state.source_asset_id != asset_id:
                        raise AppError(409, "UPLOAD_CANCELLED", "Upload dihentikan karena proyek dihapus atau upload kedaluwarsa.")
                    last_lifecycle_check = time.monotonic()
                size += len(chunk)
                if size > config.max_upload_bytes:
                    raise AppError(413, "UPLOAD_TOO_LARGE", "Ukuran video melebihi batas upload.")
                if storage.free_bytes() < config.min_free_disk_bytes + len(chunk):
                    raise AppError(507, "DISK_FULL", "Ruang penyimpanan habis saat upload.")
                output.write(chunk)
                checksum.update(chunk)
        if size == 0:
            raise AppError(422, "UPLOAD_EMPTY", "File video kosong.")
        db.expire_all()
        project = own_project(db, user, project_id, lock=True)
        asset = db.get(Asset, asset_id)
        if not asset or project.source_asset_id != asset_id or asset.state != "uploading":
            raise AppError(409, "UPLOAD_EXPIRED", "Upload telah kedaluwarsa. Ulangi dari awal.")
        storage.publish(temporary, key)
        asset.bytes, asset.checksum, asset.state = size, checksum.hexdigest(), "pending"
        asset.meta_json = {k: v for k, v in asset.meta_json.items() if k != "upload_key"}
        project.status = "validating"
        job = queue_job(db, project, "validate", {"source_asset_id": asset.id}, idempotency_key)
        job.limits_json = {**job.limits_json, "max_upload_bytes": config.max_upload_bytes, "max_video_seconds": config.max_video_seconds}
        db.commit()
        return job_data(job)
    except BaseException as exc:
        db.rollback()
        temporary.unlink(missing_ok=True)
        storage.remove(key)
        stored = db.get(Asset, asset_id)
        current = db.get(Project, project_id)
        if stored:
            stored.state = "failed"
        if current and current.lifecycle_state == "active" and current.source_asset_id == asset_id:
            current.status = "empty"
            current.source_asset_id = None
            current.error_message = "Upload terputus atau gagal. Pilih file dan ulangi upload dari awal."
        db.commit()
        if isinstance(exc, ClientDisconnect):
            raise AppError(400, "UPLOAD_INTERRUPTED", "Upload terputus. Ulangi dari awal.") from exc
        raise


@router.post("/projects/{project_id}/process", status_code=202)
def process_project(project_id: str, body: ProcessInput, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id, lock=True)
    source = source_for_edit(db, project)
    transcript = db.scalar(select(Transcript).where(Transcript.project_id == project.id).order_by(Transcript.version.desc()).limit(1))
    if body.analyze and body.max_duration_ms > processing_limits(db, user.id)["max_clip_ms"]:
        raise AppError(422, "CLIP_DURATION", "Rentang kandidat melebihi batas klip pada Pengaturan.")
    params = body.model_dump(exclude={"transcribe_again"})
    params["source_asset_id"] = source.id
    if transcript and not body.transcribe_again and body.analyze:
        params["transcript_id"] = transcript.id
        job = queue_job(db, project, "analyze", params, idempotency_key)
    else:
        params["transcript_version"] = (transcript.version + 1) if transcript and body.transcribe_again else 1
        job = queue_job(db, project, "transcribe", params, idempotency_key)
    db.commit()
    return job_data(job)


@router.get("/projects/{project_id}/transcripts/{version}")
def transcript_detail(project_id: str, version: str, search: str = "", page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=1000), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id)
    query = select(Transcript).where(Transcript.project_id == project.id)
    if version != "latest":
        if not version.isdigit():
            raise AppError(404, "TRANSCRIPT_NOT_FOUND", "Versi transkrip tidak ditemukan.")
        query = query.where(Transcript.version == int(version))
    transcript = db.scalar(query.order_by(Transcript.version.desc()).limit(1))
    if not transcript:
        raise AppError(404, "TRANSCRIPT_NOT_FOUND", "Transkrip belum tersedia.")
    segments = select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id)
    if search:
        segments = segments.where(TranscriptSegment.text.icontains(search, autoescape=True))
    total = db.scalar(select(func.count()).select_from(segments.subquery()))
    rows = db.scalars(segments.order_by(TranscriptSegment.order).offset((page - 1) * page_size).limit(page_size))
    return {"id": transcript.id, "version": transcript.version, "language": transcript.language, "model": transcript.model, "created_at": transcript.created_at,
            "segments": [{key: getattr(s, key) for key in ("id", "order", "start_ms", "end_ms", "text", "words_json")} for s in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/projects/{project_id}/clips")
def clips(project_id: str, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id)
    query = select(Clip).where(Clip.project_id == project.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Clip.created_at).offset((page - 1) * page_size).limit(page_size))
    return {"items": [clip_data(db, clip, project) for clip in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/projects/{project_id}/clips", status_code=201)
def create_clip(project_id: str, body: ClipInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id, lock=True)
    source = source_for_edit(db, project)
    validate_bounds(body.start_ms, body.end_ms, source.meta_json["duration_ms"], processing_limits(db, user.id)["max_clip_ms"])
    validate_video_effects(body.subtitle_style_json.model_dump(), body.end_ms - body.start_ms)
    transcript = db.get(Transcript, body.transcript_id) if body.transcript_id else db.scalar(select(Transcript).where(Transcript.project_id == project.id).order_by(Transcript.version.desc()).limit(1))
    if body.transcript_id and (not transcript or transcript.project_id != project.id):
        raise AppError(404, "TRANSCRIPT_NOT_FOUND", "Transkrip tidak ditemukan.")
    cues = [c.model_dump() for c in body.cues] if body.cues is not None else []
    if body.cues is None and transcript:
        segments = [{"start_ms": segment.start_ms, "end_ms": segment.end_ms, "text": segment.text, "words_json": segment.words_json}
                    for segment in db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id, TranscriptSegment.end_ms > body.start_ms, TranscriptSegment.start_ms < body.end_ms).order_by(TranscriptSegment.order))]
        cues = transcript_cues(segments, body.start_ms, body.end_ms)
    validate_cues(cues, body.end_ms - body.start_ms)
    clip = Clip(project_id=project.id, origin="manual")
    db.add(clip)
    db.flush()
    revision = ClipRevision(clip_id=clip.id, revision=1, transcript_id=transcript.id if transcript else None, start_ms=body.start_ms, end_ms=body.end_ms, title=body.title, crop_json=body.crop_json.model_dump(), subtitle_style_json=body.subtitle_style_json.model_dump())
    db.add(revision)
    db.flush()
    db.add_all([SubtitleCue(clip_revision_id=revision.id, **cue) for cue in cues])
    clip.active_revision_id = revision.id
    project.updated_at = utcnow()
    db.commit()
    return clip_data(db, clip, project)


@router.get("/clips/{clip_id}")
def clip_detail(clip_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    clip, project = own_clip(db, user, clip_id)
    return clip_data(db, clip, project)


@router.patch("/clips/{clip_id}")
def update_clip(clip_id: str, body: ClipPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    clip, project = own_clip(db, user, clip_id, lock=True)
    old = db.get(ClipRevision, clip.active_revision_id)
    if old.revision != body.expected_revision:
        raise AppError(409, "REVISION_CONFLICT", "Klip sudah diubah di tab lain. Muat revisi terbaru sebelum menyimpan.")
    source = source_for_edit(db, project)
    start = body.start_ms if body.start_ms is not None else old.start_ms
    end = body.end_ms if body.end_ms is not None else old.end_ms
    validate_bounds(start, end, source.meta_json["duration_ms"], max(processing_limits(db, user.id)["max_clip_ms"], old.end_ms - old.start_ms))
    subtitle_style = body.subtitle_style_json.model_dump() if body.subtitle_style_json else old.subtitle_style_json
    validate_video_effects(subtitle_style, end - start)
    old_cues = [cue_data(c) for c in db.scalars(select(SubtitleCue).where(SubtitleCue.clip_revision_id == old.id).order_by(SubtitleCue.start_ms))]
    cues = [c.model_dump() for c in body.cues] if body.cues is not None else remap_cues(old_cues, old.start_ms, start, end)
    validate_cues(cues, end - start)
    revision = ClipRevision(clip_id=clip.id, revision=old.revision + 1, transcript_id=old.transcript_id, start_ms=start, end_ms=end, title=body.title if body.title is not None else old.title, reason=old.reason, topic=old.topic,
                            crop_json=body.crop_json.model_dump() if body.crop_json else old.crop_json, subtitle_style_json=subtitle_style)
    db.add(revision)
    db.flush()
    db.add_all([SubtitleCue(clip_revision_id=revision.id, **cue) for cue in cues])
    clip.active_revision_id = revision.id
    project.updated_at = utcnow()
    db.commit()
    return clip_data(db, clip, project)


@router.get("/clips/{clip_id}/subtitle-words")
def clip_subtitle_words(clip_id: str, start_ms: int = Query(ge=0), end_ms: int = Query(gt=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    clip, project = own_clip(db, user, clip_id)
    revision = db.get(ClipRevision, clip.active_revision_id)
    source = source_for_edit(db, project)
    validate_bounds(start_ms, end_ms, source.meta_json['duration_ms'], max(processing_limits(db, user.id)['max_clip_ms'], revision.end_ms - revision.start_ms))
    return {'source_words': source_words(db, revision, start_ms, end_ms)}


@router.post("/clips/{clip_id}/subtitles/generate", status_code=202)
def generate_clip_subtitles(clip_id: str, body: SubtitleGenerateInput, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    clip, project = own_clip(db, user, clip_id, lock=True)
    revision = db.get(ClipRevision, clip.active_revision_id)
    if revision.revision != body.expected_revision:
        raise AppError(409, "REVISION_CONFLICT", "Klip sudah diubah di tab lain. Muat revisi terbaru sebelum membuat subtitle.")
    if not body.replace_existing and db.scalar(select(SubtitleCue.id).where(SubtitleCue.clip_revision_id == revision.id).limit(1)):
        raise AppError(409, "SUBTITLES_EXIST", "Klip sudah memiliki subtitle. Subtitle yang telah diedit tidak akan ditimpa.")
    source = source_for_edit(db, project)
    validate_bounds(revision.start_ms, revision.end_ms, source.meta_json["duration_ms"], max(processing_limits(db, user.id)["max_clip_ms"], revision.end_ms - revision.start_ms))
    latest = db.scalar(select(Transcript).where(Transcript.project_id == project.id).order_by(Transcript.version.desc()).limit(1))
    params = {"clip_id": clip.id, "clip_revision_id": revision.id, "source_asset_id": source.id,
              "language": body.language, "base_transcript_id": latest.id if latest else None,
              "replace_existing": body.replace_existing,
              "recovery_signature": recovery_signature(get_settings())}
    job = queue_job(db, project, "subtitle_generate", params, idempotency_key)
    db.commit()
    return job_data(job)


@router.post("/clips/{clip_id}/tracking-preview", status_code=202)
def create_tracking_preview(clip_id: str, body: TrackingPreviewInput, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    clip, project = own_clip(db, user, clip_id, lock=True)
    source = source_for_edit(db, project)
    saved = db.get(ClipRevision, clip.active_revision_id)
    validate_bounds(body.start_ms, body.end_ms, source.meta_json["duration_ms"], max(processing_limits(db, user.id)["max_clip_ms"], saved.end_ms - saved.start_ms))
    spec = make_tracking_spec(source, ready_preview(db, project), body.start_ms, body.end_ms, body.crop_json.model_dump())
    job = queue_job(db, project, "track_preview", {"tracking_spec": spec}, idempotency_key)
    db.commit()
    return job_data(job)


@router.post("/clips/{clip_id}/exports", status_code=202)
def create_export(clip_id: str, body: ExportInput, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    clip, project = own_clip(db, user, clip_id, lock=True)
    source_for_edit(db, project)
    revision = db.scalar(select(ClipRevision).where(ClipRevision.clip_id == clip.id, ClipRevision.revision == body.revision))
    if not revision:
        raise AppError(404, "REVISION_NOT_FOUND", "Revisi tersimpan tidak ditemukan.")
    validate_video_effects(revision.subtitle_style_json, revision.end_ms - revision.start_ms)
    cues = [cue_data(cue) for cue in db.scalars(select(SubtitleCue).where(SubtitleCue.clip_revision_id == revision.id))]
    try:
        validate_subtitle_layout(subtitle_events(db, revision, cues), revision.subtitle_style_json)
    except MediaError as exc:
        raise AppError(422, exc.code.upper(), exc.message) from exc
    export_id = new_id()
    config = {"resolution": body.resolution, "width": body.resolution, "height": 1920 if body.resolution == 1080 else 1280, "fps": 30, "pipeline_version": get_settings().pipeline_version}
    config["renderer"] = revision.subtitle_style_json.get("renderer", "ffmpeg")
    if config["renderer"] == "remotion":
        from app.media.remotion import REMOTION_RENDERER_VERSION
        config.update(renderer_version=REMOTION_RENDERER_VERSION,
                      remotion_template=revision.subtitle_style_json.get("remotion_template", "gaming"))
    params = {"export_id": export_id, "clip_revision_id": revision.id, "source_asset_id": project.source_asset_id, "config": config}
    if revision.crop_json.get("mode", "fill") == "fill" and revision.crop_json.get("tracking") in ("face", "speaker"):
        params["tracking_signature"] = analysis_metadata(revision.crop_json["tracking"])["algorithm_signature"]
    elif revision.crop_json.get("mode") == "gaming":
        from app.media.gaming import GAMING_LAYOUT_VERSION
        params["gaming_layout_version"] = GAMING_LAYOUT_VERSION
    job = queue_job(db, project, "render", params, idempotency_key)
    db.flush()
    existing = db.scalar(select(Export).where(Export.job_id == job.id))
    if not existing:
        db.add(Export(id=job.input_json.get("export_id", export_id), clip_revision_id=revision.id, job_id=job.id, config_json=config))
    db.commit()
    return job_data(job)


@router.get("/projects/{project_id}/exports")
def exports(project_id: str, clip_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = own_project(db, user, project_id)
    query = select(Export).join(ClipRevision, ClipRevision.id == Export.clip_revision_id).join(Clip, Clip.id == ClipRevision.clip_id).where(Clip.project_id == project.id)
    if clip_id:
        query = query.where(Clip.id == clip_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Export.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [export_data(db, export) for export in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job, _ = own_job(db, user, job_id)
    return job_data(job)


@router.post("/jobs/{job_id}/cancel", status_code=202)
def cancel_job(job_id: str, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    job, project = own_job(db, user, job_id, lock=True)
    if job.kind == "delete_assets":
        raise AppError(409, "DELETE_CANNOT_CANCEL", "Penghapusan yang sudah dimulai tidak dapat dibatalkan.")
    if action_request(db, project, job, "cancel", idempotency_key):
        return job_data(job)
    if job.status == "queued":
        job.status, job.finished_at = "cancelled", utcnow()
        if job.kind == "import_url":
            project.status = "empty"
    elif job.status == "running":
        job.status = "cancel_requested"
    export = db.scalar(select(Export).where(Export.job_id == job.id))
    if export and job.status == "cancelled":
        export.status = "cancelled"
    db.commit()
    return job_data(job)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    job, project = own_job(db, user, job_id, lock=True)
    if job.kind == "studio_montage":
        raise AppError(409, "JOB_RETIRED", "Fitur pembuat montage ini sudah tidak tersedia.")
    if action_request(db, project, job, "retry", idempotency_key):
        return job_data(job)
    if job.status not in ("failed", "cancelled"):
        if job.status in ACTIVE:
            db.commit()
            return job_data(job)
        raise AppError(409, "JOB_NOT_RETRYABLE", "Pekerjaan ini sudah selesai.")
    limits = processing_limits(db, user.id)
    if job.attempt >= get_settings().job_max_attempts and not can_retry_after_limit_increase(job, limits):
        raise AppError(409, "JOB_RETRY_LIMIT", "Batas percobaan tercapai. Periksa konfigurasi server sebelum melanjutkan.")
    if job.kind == "import_url":
        source = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
        other = db.scalar(select(Job.id).where(Job.project_id == project.id, Job.kind == "import_url", Job.id != job.id, Job.status.in_(ACTIVE)))
        if other or source and source.state not in ("failed", "invalid"):
            raise AppError(409, "SOURCE_EXISTS", "Video sumber atau impor lain sudah tersedia. Buat proyek baru untuk URL ini.")
        project.status, project.error_message = "importing", None
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    count = db.scalar(select(func.count()).select_from(Job).join(Project).where(Project.owner_id == user.id, Job.status.in_(ACTIVE)))
    if job.kind != "delete_assets" and count >= get_settings().max_active_jobs_per_user:
        raise AppError(429, "JOB_LIMIT", "Antrean pekerjaan penuh. Tunggu pekerjaan aktif selesai.")
    job.status, job.error_code, job.error_message, job.finished_at, job.progress = "queued", None, None, None, None
    job.lease_expires_at = None
    job.limits_json = limits
    db.add(OutboxEvent(job_id=job.id, payload={"job_id": job.id}))
    export = db.scalar(select(Export).where(Export.job_id == job.id))
    if export:
        export.status = "queued"
    db.commit()
    return job_data(job)


@router.head("/assets/{asset_id}/content", include_in_schema=False)
@router.get("/assets/{asset_id}/content")
def content(asset_id: str, download: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise AppError(404, "ASSET_NOT_FOUND", "File tidak ditemukan.")
    own_project(db, user, asset.project_id)
    if asset.state != "ready":
        raise AppError(409, "ASSET_NOT_READY", "File belum tersedia.")
    path = LocalStorage().path(asset.storage_key)
    if not path.is_file():
        raise AppError(404, "ASSET_MISSING", "File tidak tersedia pada penyimpanan server.")
    return FileResponse(path, media_type=asset.mime, filename=f"clipper-{asset.id}{path.suffix}" if download else None,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/settings")
def settings_view(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from redis import Redis
    config = effective_settings(db, user.id)
    limits = processing_limits(db, user.id)
    try:
        broker_ready = bool(Redis.from_url(config.redis_url, socket_connect_timeout=1, socket_timeout=1).ping())
    except Exception:
        broker_ready = False
    return {"default_language": config.default_language, "max_upload_bytes": config.max_upload_bytes, "max_video_seconds": config.max_video_seconds,
            "max_video_width": config.max_video_width, "max_video_height": config.max_video_height,
            "whisper_model": config.whisper_model, "whisper_device": config.whisper_device, "whisper_compute_type": config.whisper_compute_type,
            "deepseek_configured": bool(config.deepseek_api_key), "deepseek_model": config.deepseek_model,
            "services": {"database": True, "broker": broker_ready}, "capabilities": {"manual_clips": True, "transcription": True, "recommendations": bool(config.deepseek_api_key)},
            "limits": {"min_clip_ms": 5000, "max_clip_ms": limits["max_clip_ms"]},
            "settings_scope": "account", "max_clip_ms": limits["max_clip_ms"],
            "editable_ranges": {"max_video_seconds": [60, MAX_SOURCE_SECONDS], "max_upload_bytes": [1024**2, MAX_SOURCE_BYTES], "max_clip_ms": [5000, MAX_CLIP_MS]}}


@router.patch("/settings")
def update_processing_settings(body: ProcessingSettingsInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    row = db.get(ProcessingSettings, user.id)
    if row is None:
        row = ProcessingSettings(user_id=user.id, **body.model_dump())
        db.add(row)
    else:
        for key, value in body.model_dump().items():
            setattr(row, key, value)
    db.commit()
    return settings_view(user, db)


@router.get("/usage")
def usage(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(ProviderUsage).join(JobAttempt, JobAttempt.id == ProviderUsage.job_attempt_id).join(Job, Job.id == JobAttempt.job_id).join(Project, Project.id == Job.project_id).where(Project.owner_id == user.id)
    rows = list(db.scalars(query.order_by(ProviderUsage.created_at.desc()).limit(100)))
    totals = db.execute(query.with_only_columns(func.coalesce(func.sum(ProviderUsage.input_tokens), 0), func.coalesce(func.sum(ProviderUsage.output_tokens), 0))).one()
    storage_bytes = db.scalar(select(func.coalesce(func.sum(Asset.bytes), 0)).join(Project, Project.id == Asset.project_id).where(Project.owner_id == user.id, Asset.state == "ready"))
    return {"input_tokens": totals[0], "output_tokens": totals[1], "storage_bytes": storage_bytes,
            "scope": "Total seluruh riwayat. Daftar menampilkan 100 panggilan terakhir.", "currency_cost": None,
            "items": [{key: getattr(r, key) for key in ("id", "provider", "model", "input_tokens", "output_tokens", "latency_ms", "outcome", "created_at")} for r in rows]}
