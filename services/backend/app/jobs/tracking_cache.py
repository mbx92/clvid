"""Project-private identities and validation for reusable crop analyses.

An analysis belongs to immutable source bytes and a draft's crop/time bounds,
not to a clip revision. Caption/title edits therefore keep the same identity.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.domain.models import Asset, Job
from app.media.render import reusable_tracking_result
from app.media.tracking_versions import ANALYSIS_VERSION, SAMPLE_FPS, TRACKING_METHODS

from .service import fingerprint

SIGNATURE_FIELDS = ("analysis_version", "pipeline_version", "method", "sample_fps", "model_sha256", "speaker_model_sha256")


def ready_preview(db, project) -> Asset | None:
    preview = db.get(Asset, project.preview_asset_id) if project.preview_asset_id else None
    return preview if preview and preview.project_id == project.id and preview.state == "ready" else None


@lru_cache(maxsize=16)
def _model_digest(path: str, size: int, modified_ns: int, changed_ns: int, inode: int) -> str:
    # Listing many clips must not reread model weights once per clip. File
    # identity/stat changes invalidate this digest when models are replaced.
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_signature(path: str | Path) -> str | None:
    try:
        resolved = Path(path).resolve()
        stat = resolved.stat()
        return _model_digest(str(resolved), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
    except OSError:
        # Missing models must be an explicit retryable job failure, not a cache
        # entry pretending a detector ran. No server paths leave this module.
        return None


def algorithm_signature(metadata: dict) -> str:
    canonical = json.dumps({key: metadata.get(key) for key in SIGNATURE_FIELDS}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def analysis_metadata(mode: str, *, settings=None) -> dict:
    settings = settings or get_settings()
    metadata = {"analysis_version": ANALYSIS_VERSION, "pipeline_version": settings.pipeline_version,
                "method": TRACKING_METHODS.get(mode), "sample_fps": SAMPLE_FPS,
                "model_sha256": model_signature(settings.tracking_model_path),
                "speaker_model_sha256": model_signature(settings.speaker_model_path) if mode == "speaker" else None}
    return {**metadata, "algorithm_signature": algorithm_signature(metadata)}


def tracking_signatures(*, settings=None) -> dict[str, str]:
    return {mode: analysis_metadata(mode, settings=settings)["algorithm_signature"] for mode in TRACKING_METHODS}


def make_tracking_spec(source: Asset, preview: Asset | None, start_ms: int, end_ms: int,
                       crop: dict, *, settings=None) -> dict:
    settings = settings or get_settings()
    normalized = {"mode": crop.get("mode", "fill"), "tracking": crop.get("tracking", "static"),
                  "x": float(crop.get("x", .5)) or 0.0, "y": float(crop.get("y", .5)) or 0.0}
    return {**analysis_metadata(normalized["tracking"], settings=settings),
            "source_asset_id": source.id, "source_checksum": source.checksum,
            "preview_asset_id": preview.id if preview else None,
            "preview_checksum": preview.checksum if preview else None,
            "start_ms": start_ms, "end_ms": end_ms, "crop_json": normalized}


def valid_framing(value: dict | None, spec: dict) -> dict | None:
    if (not isinstance(value, dict) or not spec.get("model_sha256") or
            spec.get("analysis_version") != ANALYSIS_VERSION or spec.get("sample_fps") != SAMPLE_FPS or
            spec.get("algorithm_signature") != algorithm_signature(spec)):
        return None
    mode = spec.get("crop_json", {}).get("tracking")
    if mode not in TRACKING_METHODS or spec.get("method") != TRACKING_METHODS[mode]:
        return None
    if mode == "speaker" and (not spec.get("speaker_model_sha256") or
                               value.get("speaker_model_sha256") != spec["speaker_model_sha256"]):
        return None
    if (value.get("model_sha256") != spec["model_sha256"] or value.get("method") != spec["method"] or
            value.get("sample_fps") != spec["sample_fps"]):
        return None
    total, detected = value.get("total_frames"), value.get("detected_frames")
    duration = spec["end_ms"] - spec["start_ms"]
    if (type(total) is not int or type(detected) is not int or not 0 <= detected <= total or
            not 0 < total <= (duration * spec["sample_fps"] + 999) // 1000 + 2):
        return None
    return reusable_tracking_result(value, spec["crop_json"], duration)


def find_tracking_result(db, project_id: str, spec: dict) -> dict | None:
    if spec["crop_json"]["mode"] != "fill" or spec["crop_json"]["tracking"] not in TRACKING_METHODS:
        return None
    inputs = {"tracking_spec": spec}
    job = db.scalar(select(Job).where(Job.project_id == project_id, Job.kind == "track_preview",
                                      Job.input_fingerprint == fingerprint("track_preview", inputs),
                                      Job.status == "succeeded"))
    if (not job or job.input_json != inputs or not isinstance(job.result_json, dict) or
            job.result_json.get("tracking_spec") != spec):
        return None
    return valid_framing(job.result_json.get("framing"), spec)
