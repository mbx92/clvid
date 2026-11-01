from sqlalchemy import func, select

from app.domain.models import Asset, Clip, ClipRevision, Export, Job, SubtitleCue, Transcript
from app.jobs.tracking_cache import tracking_signatures
from app.domain.limits import processing_limits
from app.domain.subtitle_timing import source_words


ACTIVE = ("queued", "running", "cancel_requested")


def asset_data(asset):
    if not asset:
        return None
    return {"id": asset.id, "kind": asset.kind, "bytes": asset.bytes, "mime": asset.mime,
            "state": asset.state, "metadata": {k: v for k, v in asset.meta_json.items() if k != "upload_key"},
            "content_url": f"/api/v1/assets/{asset.id}/content" if asset.state == "ready" else None}


def job_data(job):
    return {key: getattr(job, key) for key in ("id", "project_id", "kind", "status", "stage", "attempt", "progress", "error_code", "error_message", "created_at", "started_at", "finished_at", "result_json")}


def project_data(db, project, detail=False):
    data = {key: getattr(project, key) for key in ("id", "name", "status", "lifecycle_state", "error_message", "created_at", "updated_at")}
    data["limits"] = {"min_clip_ms": 5000, "max_clip_ms": processing_limits(db, project.owner_id)["max_clip_ms"]}
    data["source_asset"] = asset_data(db.get(Asset, project.source_asset_id)) if project.source_asset_id else None
    data["preview_asset"] = asset_data(db.get(Asset, project.preview_asset_id)) if project.preview_asset_id else None
    data["latest_transcript_version"] = db.scalar(select(func.max(Transcript.version)).where(Transcript.project_id == project.id))
    data["clip_count"] = db.scalar(select(func.count()).select_from(Clip).where(Clip.project_id == project.id))
    jobs = list(db.scalars(select(Job).where(Job.project_id == project.id).order_by(Job.created_at.desc())))
    data["active_jobs"] = [job_data(j) for j in jobs if j.status in ACTIVE]
    if detail:
        data["jobs"] = [job_data(j) for j in jobs[:100]]
    return data


def cue_data(cue):
    return {"start_ms": cue.start_ms, "end_ms": cue.end_ms, "text": cue.text}


def revision_data(db, revision):
    data = {key: getattr(revision, key) for key in ("id", "revision", "transcript_id", "start_ms", "end_ms", "title", "reason", "topic", "crop_json", "subtitle_style_json", "created_at")}
    data["cues"] = [cue_data(cue) for cue in db.scalars(select(SubtitleCue).where(SubtitleCue.clip_revision_id == revision.id).order_by(SubtitleCue.start_ms, SubtitleCue.id))]
    data["source_words"] = source_words(db, revision)
    return data


def clip_data(db, clip, project):
    source = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
    preview = db.get(Asset, project.preview_asset_id) if project.preview_asset_id else None
    revision = db.get(ClipRevision, clip.active_revision_id)
    return {"id": clip.id, "project_id": clip.project_id, "origin": clip.origin, "created_at": clip.created_at,
            "revision": revision_data(db, revision), "source_asset": asset_data(source), "preview_asset": asset_data(preview),
            "tracking_signatures": tracking_signatures(),
            "limits": {"min_clip_ms": 5000, "max_clip_ms": max(processing_limits(db, project.owner_id)["max_clip_ms"], revision.end_ms - revision.start_ms)},
            "media_duration_ms": (source.meta_json or {}).get("duration_ms", 0) if source else 0}


def export_data(db, export):
    revision = db.get(ClipRevision, export.clip_revision_id)
    return {"id": export.id, "clip_id": revision.clip_id, "clip_title": revision.title, "revision": revision.revision,
            "config": export.config_json, "status": export.status, "created_at": export.created_at,
            "job": job_data(db.get(Job, export.job_id)),
            "mp4_asset": asset_data(db.get(Asset, export.mp4_asset_id)) if export.mp4_asset_id else None,
            "srt_asset": asset_data(db.get(Asset, export.srt_asset_id)) if export.srt_asset_id else None}
