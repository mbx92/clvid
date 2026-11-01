"""Account preferences, separate from fixed processing safety bounds."""
from app.config import get_settings
from app.domain.models import ProcessingSettings

MIN_CLIP_MS = 5000
MAX_CLIP_MS = 600000
MAX_SOURCE_SECONDS = 43200
MAX_SOURCE_BYTES = 64 * 1024**3


def processing_limits(db, user_id: str) -> dict:
    row = db.get(ProcessingSettings, user_id)
    config = get_settings()
    return {"max_video_seconds": row.max_video_seconds if row else config.max_video_seconds,
            "max_upload_bytes": row.max_upload_bytes if row else config.max_upload_bytes,
            "max_clip_ms": row.max_clip_ms if row else 180000}


def effective_settings(db, user_id: str):
    limits = processing_limits(db, user_id)
    return get_settings().model_copy(update={key: limits[key] for key in ("max_video_seconds", "max_upload_bytes")})


def can_retry_after_limit_increase(job, limits: dict) -> bool:
    """Grant one manual retry for a corrected limit, preserving attempt history.

    Queueing replaces the snapshot, so unchanged settings cannot repeatedly
    bypass the attempt cap. Legacy jobs used server defaults before snapshots.
    """
    if job.status != "failed" or job.kind not in ("import_url", "validate"):
        return False
    key = {"duration_limit": "max_video_seconds", "file_too_large": "max_upload_bytes",
           "upload_too_large": "max_upload_bytes"}.get(job.error_code)
    if key is None:
        return False
    previous = (job.limits_json or {}).get(key, getattr(get_settings(), key))
    return limits[key] > previous
