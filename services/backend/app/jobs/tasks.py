from __future__ import annotations

from app.domain.limits import MAX_CLIP_MS

import hashlib
import shutil
import time
from pathlib import Path

from sqlalchemy import delete, func, select

from app.ai.selector import select_clips
from app.ai.transcribe import transcribe
from app.config import get_settings
from app.db import session_scope
from app.domain.models import (Asset, Clip, ClipRevision, Export, Job, JobAttempt, Project,
                               ProviderUsage, SubtitleCue, Transcript, TranscriptSegment, new_id, utcnow)
from app.media.import_url import download_video
from app.media.source_preparation import prepare_source
from app.media.process import Cancelled, MediaError
from app.media.render import check_disk, render_clip
from app.media.subtitles import transcript_cues
from app.domain.subtitle_timing import subtitle_events
from app.domain.models import Publication
from app.media.tracking import track_clip
from app.storage.local import LocalStorage

from .celery_app import celery_app
from .runtime import JobContext, claim
from .service import ACTIVE, create_job
from .tracking_cache import find_tracking_result, make_tracking_spec, ready_preview, valid_framing


def _snapshot(ctx: JobContext):
    with session_scope() as db:
        job, project = ctx.check(db)
        asset = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
        return job, project, asset


def _complete(db, ctx: JobContext, result: dict):
    job, _ = ctx.check(db)
    job.result_json, job.status, job.progress = result, "succeeded", 1
    job.finished_at, job.lease_expires_at = utcnow(), None
    attempt = db.get(JobAttempt, ctx.attempt_id)
    attempt.outcome, attempt.finished_at = "succeeded", utcnow()


def _asset(db, ctx: JobContext, project: Project, path: Path, kind: str, mime: str, meta: dict) -> Asset:
    storage = LocalStorage()
    suffix = path.suffix
    key = f"projects/{project.id}/results/{ctx.job_id}/{kind}{suffix}"
    final = storage.publish(path, key)
    checksum = hashlib.sha256()
    with final.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            checksum.update(block)
    asset = Asset(project_id=project.id, kind=kind, storage_key=key, bytes=final.stat().st_size,
                  mime=mime, checksum=checksum.hexdigest(), meta_json=meta, state="ready")
    db.add(asset)
    db.flush()
    return asset


def _validate(ctx: JobContext, scratch: Path):
    job, project, source = _snapshot(ctx)
    if not source or source.id != job.input_json.get("source_asset_id", source.id):
        raise MediaError("source_missing", "File sumber tidak ditemukan. Unggah kembali video.")
    ctx.stage("validate")
    settings = ctx.settings
    path = LocalStorage().path(source.storage_key)
    check_disk(scratch, source.bytes, settings.min_free_disk_bytes)
    meta, preview = prepare_source(path, scratch, settings=settings, stage=ctx.stage,
                                   cancelled=ctx.cancelled, progress=ctx.progress)
    with session_scope() as db:
        job, project = ctx.check(db)
        source = db.get(Asset, source.id)
        source.state, source.meta_json = "ready", {**source.meta_json, **meta}
        if preview:
            proxy = _asset(db, ctx, project, preview["path"], "preview", "video/mp4", preview["meta"])
            project.preview_asset_id = proxy.id
        else:
            project.preview_asset_id = source.id
        project.status, project.error_message = "ready", None
        _complete(db, ctx, {"source_asset_id": source.id, "preview_asset_id": project.preview_asset_id})


def _import_url(ctx: JobContext, scratch: Path):
    job, _, source = _snapshot(ctx)
    if source and source.state not in ("failed", "invalid"):
        raise MediaError("source_exists", "Video sumber sudah tersedia. Buat proyek baru untuk URL berbeda.")
    ctx.stage("import_url")
    settings = ctx.settings
    try:
        result = download_video(job.input_json["url"], scratch, settings=settings,
                                cancelled=ctx.cancelled, progress=ctx.progress)
        ctx.stage("validate")
        path = result["path"]
        meta, preview = prepare_source(path, scratch, settings=settings, stage=ctx.stage,
                                       cancelled=ctx.cancelled, progress=ctx.progress)
        with session_scope() as db:
            _, project = ctx.check(db)
            current = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
            if current and current.state not in ("failed", "invalid"):
                raise MediaError("source_exists", "Video sumber sudah tersedia.")
            source = _asset(db, ctx, project, path, "source", "video/mp4", {**meta, "filename": result["title"], "imported_from_url": True})
            project.source_asset_id = source.id
            if preview:
                proxy = _asset(db, ctx, project, preview["path"], "preview", "video/mp4", preview["meta"])
                project.preview_asset_id = proxy.id
            else:
                project.preview_asset_id = source.id
            project.status, project.error_message = "ready", None
            _complete(db, ctx, {"source_asset_id": source.id, "preview_asset_id": project.preview_asset_id})
    finally:
        # Drop partial downloads immediately; they can be large or contain signed URLs.
        shutil.rmtree(scratch, ignore_errors=True)


def _transcribe(ctx: JobContext, scratch: Path):
    job, project, source = _snapshot(ctx)
    if not source or source.state != "ready":
        raise MediaError("source_not_ready", "Video belum lolos validasi.")
    ctx.stage("transcribe")
    settings = ctx.settings
    check_disk(scratch, max(source.bytes, 64 * 1024**2), settings.min_free_disk_bytes)
    result = transcribe(LocalStorage().path(source.storage_key), scratch, model=settings.whisper_model,
                        device=settings.whisper_device, compute_type=settings.whisper_compute_type,
                        language=job.input_json.get("language", "auto"), cache_dir=settings.whisper_download_root,
                        cpu_threads=settings.whisper_cpu_threads, batch_size=settings.whisper_batch_size,
                        beam_size=settings.whisper_beam_size, duration_ms=source.meta_json["duration_ms"],
                        timeout=settings.job_timeout_seconds, cancelled=ctx.cancelled, progress=ctx.progress)
    duration_ms = source.meta_json["duration_ms"]
    segments = [{**segment, "start_ms": max(0, int(segment["start_ms"])),
                 "end_ms": min(duration_ms, int(segment["end_ms"]))} for segment in result["segments"]]
    segments = [s for s in segments if s["end_ms"] > s["start_ms"] and s["text"].strip()]
    with session_scope() as db:
        job, project = ctx.check(db)
        version = (db.scalar(select(func.max(Transcript.version)).where(Transcript.project_id == project.id)) or 0) + 1
        transcript = Transcript(project_id=project.id, version=version, language=result["language"], model=settings.whisper_model,
                                config_json={"device": settings.whisper_device, "compute_type": settings.whisper_compute_type,
                                             "runtime": result.get("runtime", {}),
                                             "vad_filter": True, "word_timestamps": True})
        db.add(transcript)
        db.flush()
        for order, segment in enumerate(segments):
            db.add(TranscriptSegment(transcript_id=transcript.id, order=order, start_ms=segment["start_ms"],
                                     end_ms=segment["end_ms"], text=segment["text"], words_json=segment.get("words_json")))
        project.status, project.error_message = ("ready" if segments else "no_speech"), None
        _complete(db, ctx, {"transcript_id": transcript.id, "version": version, "segments": len(segments), "runtime": result.get("runtime", {})})
        if segments and job.input_json.get("analyze", True):
            create_job(db, project, "analyze", {"transcript_id": transcript.id,
                        "content_profile": job.input_json.get("content_profile", "general"),
                        "count": job.input_json.get("count", 5),
                        "min_duration_ms": job.input_json.get("min_duration_ms", 30000),
                        "max_duration_ms": job.input_json.get("max_duration_ms", 60000)}, f"transcript-{transcript.id}")


def _analyze(ctx: JobContext, scratch: Path):
    job, project, source = _snapshot(ctx)
    ctx.stage("analyze")
    with session_scope() as db:
        transcript = db.get(Transcript, job.input_json.get("transcript_id"))
        if not transcript or transcript.project_id != project.id:
            raise MediaError("transcript_missing", "Transkrip belum tersedia untuk analisis.")
        rows = db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id)
                           .order_by(TranscriptSegment.order)).all()
        segments = [{"id": row.id, "start_ms": row.start_ms, "end_ms": row.end_ms, "text": row.text, "words_json": row.words_json} for row in rows]

    def record_usage(report):
        # Usage remains auditable even if a cancellation or response error follows.
        with session_scope() as db:
            db.add(ProviderUsage(job_attempt_id=ctx.attempt_id, **report))

    settings = ctx.settings
    selection_segments = [{key: value for key, value in segment.items() if key != "words_json"} for segment in segments]
    result = select_clips(selection_segments, duration_ms=source.meta_json["duration_ms"],
                          content_profile=job.input_json.get("content_profile", "general"),
                          count=job.input_json.get("count", 5), min_duration_ms=job.input_json.get("min_duration_ms", 30000),
                          max_duration_ms=job.input_json.get("max_duration_ms", 60000), api_key=settings.deepseek_api_key,
                          base_url=settings.deepseek_base_url, model=settings.deepseek_model,
                          token_budget=settings.deepseek_chunk_tokens, timeout=settings.deepseek_timeout_seconds,
                          max_retries=settings.deepseek_max_retries, cancelled=ctx.cancelled, usage=record_usage)
    with session_scope() as db:
        _, project = ctx.check(db)
        clip_ids = []
        for candidate in result.candidates:
            clip = Clip(project_id=project.id, origin="ai")
            db.add(clip)
            db.flush()
            revision = ClipRevision(clip_id=clip.id, revision=1, transcript_id=transcript.id,
                                    start_ms=candidate["start_ms"], end_ms=candidate["end_ms"],
                                    title=candidate["title"], reason=candidate["reason"], topic=candidate["topic"],
                                    crop_json={"mode": "fill", "x": .5, "y": .5},
                                    subtitle_style_json={"enabled": True, "font_size": 52, "position": "bottom", "background": True, "safe_margin": .15})
            db.add(revision)
            db.flush()
            clip.active_revision_id = revision.id
            for cue in transcript_cues(segments, revision.start_ms, revision.end_ms):
                db.add(SubtitleCue(clip_revision_id=revision.id, **cue))
            clip_ids.append(clip.id)
        project.status, project.error_message = "ready", None
        _complete(db, ctx, {"clip_ids": clip_ids, "count": len(clip_ids), "requested": result.requested,
                            "message": f"{len(clip_ids)} kandidat valid tersedia dari {result.requested} yang diminta."})


def _preview_inputs(db, ctx: JobContext):
    job, project = ctx.check(db)
    source = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
    if not source or source.project_id != project.id or source.state != "ready":
        raise MediaError("source_not_ready", "Video sumber tidak tersedia untuk preview tracking.")
    spec = job.input_json.get("tracking_spec", {})
    start, end = spec.get("start_ms"), spec.get("end_ms")
    if (type(start) is not int or type(end) is not int or
            not 0 <= start < end <= source.meta_json.get("duration_ms", 0) or not 5000 <= end - start <= MAX_CLIP_MS):
        raise MediaError("invalid_clip", "Batas preview tracking tidak valid.")
    crop = spec.get("crop_json", {})
    if crop.get("mode") != "fill" or crop.get("tracking") not in ("face", "speaker"):
        raise MediaError("invalid_crop", "Preview tracking memerlukan mode wajah atau pembicara.")
    preview = ready_preview(db, project)
    if spec != make_tracking_spec(source, preview, start, end, crop, settings=ctx.settings):
        raise MediaError("tracking_input_changed", "Video atau versi pelacak berubah. Minta preview tracking baru.")
    return source, preview, spec


def _track_preview(ctx: JobContext, scratch: Path):
    with session_scope() as db:
        source, preview, spec = _preview_inputs(db, ctx)
    ctx.stage("track_faces")
    framing = track_clip(LocalStorage().path((preview or source).storage_key), scratch,
                         start_ms=spec["start_ms"], end_ms=spec["end_ms"], crop=spec["crop_json"],
                         ffmpeg_bin=ctx.settings.ffmpeg_path, model_path=Path(ctx.settings.tracking_model_path),
                         speaker_model_path=Path(ctx.settings.speaker_model_path),
                         sample_fps=spec["sample_fps"], timeout=ctx.settings.media_timeout_seconds,
                         cancelled=ctx.cancelled, progress=ctx.progress)
    validated = valid_framing(framing, spec)
    if validated is None:
        raise MediaError("tracking_unavailable", "Analisis pelacakan tidak dapat diselesaikan. Periksa model dan worker, lalu coba kembali.")
    with session_scope() as db:
        # Recheck identity and attempt fencing before publishing; deletion,
        # cancellation or a changed source/model cannot publish a stale path.
        _preview_inputs(db, ctx)
        _complete(db, ctx, {"tracking_spec": spec, "framing": validated})


def _render(ctx: JobContext, scratch: Path):
    job, project, source = _snapshot(ctx)
    if not source or source.state != "ready":
        raise MediaError("source_not_ready", "Video sumber tidak tersedia untuk ekspor.")
    ctx.stage("render")
    with session_scope() as db:
        export = db.scalar(select(Export).where(Export.job_id == job.id))
        if not export:
            raise MediaError("export_missing", "Permintaan ekspor tidak ditemukan.")
        revision = db.get(ClipRevision, export.clip_revision_id)
        clip = db.get(Clip, revision.clip_id)
        if clip.project_id != project.id:
            raise MediaError("export_invalid", "Klip tidak berada dalam proyek ini.")
        cues = db.scalars(select(SubtitleCue).where(SubtitleCue.clip_revision_id == revision.id).order_by(SubtitleCue.start_ms)).all()
        snapshot = {"start_ms": revision.start_ms, "end_ms": revision.end_ms, "crop_json": revision.crop_json,
                    "subtitle_style_json": revision.subtitle_style_json,
                    "cues": [{"start_ms": cue.start_ms, "end_ms": cue.end_ms, "text": cue.text} for cue in cues]}
        snapshot['subtitle_events'] = subtitle_events(db, revision, snapshot['cues'])
        export.status = "running"
        export_id, config = export.id, export.config_json
        preview = ready_preview(db, project)
        tracking_source = LocalStorage().path(preview.storage_key) if preview else None
        tracking_result = None
        if revision.crop_json.get("mode", "fill") == "fill" and revision.crop_json.get("tracking") in ("face", "speaker"):
            spec = make_tracking_spec(source, preview, revision.start_ms, revision.end_ms, revision.crop_json, settings=ctx.settings)
            requested_signature = job.input_json.get("tracking_signature")
            if requested_signature and requested_signature != spec["algorithm_signature"]:
                raise MediaError("tracking_input_changed", "Versi pelacak berubah. Minta ekspor baru untuk revisi ini.")
            tracking_result = find_tracking_result(db, project.id, spec)
        elif revision.crop_json.get("mode") == "gaming":
            from app.media.gaming import GAMING_LAYOUT_VERSION
            if job.input_json.get("gaming_layout_version") != GAMING_LAYOUT_VERSION:
                raise MediaError("gaming_layout_changed", "Versi tata letak gaming berubah. Minta ekspor baru untuk revisi ini.")
    settings = ctx.settings
    result = render_clip(LocalStorage().path(source.storage_key), scratch, snapshot, config,
                         ffmpeg_bin=settings.ffmpeg_path, ffprobe_bin=settings.ffprobe_path,
                         fonts_dir=Path(settings.subtitle_font_path).parent,
                         tracking_model_path=Path(settings.tracking_model_path), tracking_source=tracking_source,
                         speaker_model_path=Path(settings.speaker_model_path),
                         tracking_result=tracking_result,
                         stage=ctx.stage,
                         timeout=settings.media_timeout_seconds, cancelled=ctx.cancelled, progress=ctx.progress)
    with session_scope() as db:
        _, project = ctx.check(db)
        video = _asset(db, ctx, project, result["mp4"], "export_mp4", "video/mp4", result["meta"])
        subtitle = _asset(db, ctx, project, result["srt"], "export_srt", "application/x-subrip", {})
        export = db.get(Export, export_id)
        export.mp4_asset_id, export.srt_asset_id, export.status = video.id, subtitle.id, "ready"
        _complete(db, ctx, {"export_id": export.id, "mp4_asset_id": video.id, "srt_asset_id": subtitle.id})


def _delete_assets(ctx: JobContext, scratch: Path):
    job, project, _ = _snapshot(ctx)
    ctx.stage("delete_assets")
    while True:
        ctx.check()
        with session_scope() as db:
            other_jobs = db.scalars(select(Job).where(Job.project_id == project.id, Job.id != job.id, Job.status.in_(ACTIVE))).all()
            waiting = False
            for other in other_jobs:
                if other.status == "queued":
                    other.status, other.finished_at = "cancelled", utcnow()
                else:
                    other.status = "cancel_requested"
                    waiting = True
            if not waiting:
                break
        time.sleep(.5)
    storage = LocalStorage()
    with session_scope() as db:
        _, project = ctx.check(db)
        assets = db.scalars(select(Asset).where(Asset.project_id == project.id)).all()
        for asset in assets:
            storage.remove(asset.storage_key)
            if asset.meta_json.get("upload_key"):
                storage.remove(asset.meta_json["upload_key"])
            asset.state = "deleted"
        directory = storage.path(f"projects/{project.id}")
        if directory.exists():
            shutil.rmtree(directory)
        # Transcript JSON, ASS and failed renders can remain in attempt scratch.
        # Project deletion removes them immediately once their processes stop.
        for previous_job_id in db.scalars(select(Job.id).where(Job.project_id == project.id, Job.id != ctx.job_id)):
            previous_scratch = storage.path(f"scratch/{previous_job_id}")
            if previous_scratch.exists():
                shutil.rmtree(previous_scratch)
        project.source_asset_id, project.preview_asset_id = None, None
        clips = list(db.scalars(select(Clip.id).where(Clip.project_id == project.id)))
        revisions = list(db.scalars(select(ClipRevision.id).where(ClipRevision.clip_id.in_(clips))))
        for clip in db.scalars(select(Clip).where(Clip.project_id == project.id)):
            clip.active_revision_id = None
        db.flush()
        db.execute(delete(SubtitleCue).where(SubtitleCue.clip_revision_id.in_(revisions)))
        for publication_id in db.scalars(select(Publication.id).where(Publication.project_id==project.id)):
            social_path=storage.path(f'social/{publication_id}')
            if social_path.is_dir(): shutil.rmtree(social_path)
        db.execute(delete(Publication).where(Publication.project_id==project.id))
        db.execute(delete(Export).where(Export.clip_revision_id.in_(revisions)))
        db.execute(delete(ClipRevision).where(ClipRevision.id.in_(revisions)))
        db.execute(delete(Clip).where(Clip.id.in_(clips)))
        transcripts = list(db.scalars(select(Transcript.id).where(Transcript.project_id == project.id)))
        db.execute(delete(TranscriptSegment).where(TranscriptSegment.transcript_id.in_(transcripts)))
        db.execute(delete(Transcript).where(Transcript.id.in_(transcripts)))
        db.flush()
        db.execute(delete(Asset).where(Asset.project_id == project.id))
        project.lifecycle_state, project.status, project.error_message = "deleted", "deleted", None
        project.name = "Proyek dihapus"
        for imported in db.scalars(select(Job).where(Job.project_id == project.id, Job.kind == "import_url")):
            imported.input_json = {}  # Drop source URLs and their query tokens on deletion.
        for analysis in db.scalars(select(Job).where(Job.project_id == project.id, Job.kind == "track_preview")):
            analysis.input_json, analysis.result_json = {}, {}
        # Completion is allowed for this tombstone because kind is delete_assets.
        _complete(db, ctx, {"deleted": True})


HANDLERS = {"import_url": _import_url, "validate": _validate, "prepare_preview": _validate, "transcribe": _transcribe,
            "analyze": _analyze, "track_preview": _track_preview, "render": _render,
            "delete_assets": _delete_assets}


@celery_app.task(name="clipper.run_job")
def run_job(job_id: str):
    claimed = claim(job_id)
    if not claimed:
        return
    attempt, attempt_id = claimed
    storage = LocalStorage()
    scratch = storage.path(f"scratch/{job_id}/{attempt}")
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        with JobContext(job_id, attempt, attempt_id) as ctx:
            job, _, _ = _snapshot(ctx)
            HANDLERS[job.kind](ctx, scratch)
    except Exception as exc:
        code = exc.code if isinstance(exc, MediaError) else "processing_failed"
        message = exc.message if isinstance(exc, MediaError) else "Pemrosesan gagal. Periksa layanan worker lalu coba tahap ini kembali."
        with session_scope() as db:
            initial = db.get(Job, job_id)
            if initial:
                db.scalar(select(Project).where(Project.id == initial.project_id).with_for_update())
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
            if job and job.attempt == attempt and job.status in ("running", "cancel_requested"):
                job.status = "cancelled" if isinstance(exc, Cancelled) or job.status == "cancel_requested" else "failed"
                job.error_code, job.error_message = code, message
                job.finished_at, job.lease_expires_at = utcnow(), None
                record = db.get(JobAttempt, attempt_id)
                record.outcome, record.finished_at = job.status, utcnow()
                export = db.scalar(select(Export).where(Export.job_id == job.id))
                if export:
                    export.status = job.status
                project = db.get(Project, job.project_id)
                if job.kind not in ("render", "track_preview") and project.lifecycle_state == "active":
                    # Keep transcript accessible after AI failure.
                    project.status = "ready" if job.kind == "analyze" else "failed"
                    project.error_message = message
                if job.kind == "validate":
                    source = db.get(Asset, project.source_asset_id)
                    if source:
                        source.state = "failed"
    finally:
        # Mark attempt scratch terminal for TTL cleanup; successful files have moved.
        try:
            (scratch / ".terminal").touch()
        except OSError:
            pass
