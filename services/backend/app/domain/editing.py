from app.api.errors import AppError


def validate_bounds(start_ms: int, end_ms: int, duration_ms: int, max_clip_ms: int = 180000):
    if not 0 <= start_ms < end_ms <= duration_ms:
        raise AppError(422, "CLIP_BOUNDS", "Batas klip harus berada di dalam durasi video.")
    if not 5000 <= end_ms - start_ms <= max_clip_ms:
        raise AppError(422, "CLIP_DURATION", f"Durasi klip harus antara 5 dan {max_clip_ms // 1000} detik.")


def validate_cues(cues: list[dict], duration_ms: int):
    for cue in cues:
        if not 0 <= cue["start_ms"] < cue["end_ms"] <= duration_ms:
            raise AppError(422, "CUE_BOUNDS", "Semua subtitle harus berada di dalam durasi klip.")


def remap_cues(cues: list[dict], old_start: int, new_start: int, new_end: int) -> list[dict]:
    """Preserve corrected text; move existing local cues through source coordinates."""
    result = []
    for cue in cues:
        start = max(new_start, old_start + cue["start_ms"])
        end = min(new_end, old_start + cue["end_ms"])
        if end > start:
            result.append({"start_ms": start - new_start, "end_ms": end - new_start, "text": cue["text"]})
    return result
