"""Recover speech in a bounded clip, keeping all timings in source coordinates."""
from __future__ import annotations

import math
import time
from pathlib import Path

from app.ai.transcribe import transcribe
from app.media.process import Cancelled, MediaError, ffmpeg


SPEECH_FILTER = "highpass=f=100,lowpass=f=6000,speechnorm=p=0.85:e=4:c=2:r=0.001:f=0.001"


def _credible(segment):
    # no_speech_prob belongs to a whole decoder window and is shared by its
    # phrases. It must not veto otherwise well recognized speech on its own.
    silence = segment.get("no_speech_prob")
    if isinstance(silence, (int, float)) and not math.isfinite(silence):
        return False
    likelihood = segment.get("avg_logprob")
    if isinstance(likelihood, (int, float)) and (not math.isfinite(likelihood) or likelihood < -1):
        return False
    words = segment.get("words_json") or []
    probabilities = [w["probability"] for w in words if w.get("end_ms", 0) > w.get("start_ms", 0)
                     and isinstance(w.get("probability"), (int, float))]
    return not probabilities or all(math.isfinite(p) for p in probabilities) and sum(probabilities) / len(probabilities) >= .5


def _unaligned_words_in_clip(segment, offset, start_ms, end_ms):
    # A zero-duration spoken word has not been aligned to audio. Silently
    # dropping it can turn a hallucinated sentence into a plausible fragment.
    # Words outside the requested cut and punctuation-only tokens are harmless.
    for word in segment.get("words_json") or []:
        if not any(char.isalnum() for char in word["word"]):
            continue
        a, b = offset + word["start_ms"], offset + word["end_ms"]
        if b <= a:
            left, right = sorted((a, b))
            if (left == right and start_ms <= left < end_ms or
                    left < right and left < end_ms and right > start_ms):
                return True
    return False


def _clip_segments(result, offset, start_ms, end_ms):
    segments = []
    for segment in result["segments"]:
        if not _credible(segment) or _unaligned_words_in_clip(segment, offset, start_ms, end_ms):
            continue
        words = []
        for word in segment.get("words_json") or []:
            a, b = max(start_ms, offset + word["start_ms"]), min(end_ms, offset + word["end_ms"])
            if b > a and word["word"].strip():
                words.append({**word, "start_ms": a, "end_ms": b})
        if not words:
            continue
        segments.append({"start_ms": words[0]["start_ms"], "end_ms": words[-1]["end_ms"],
                         "text": "".join(w["word"] for w in words).strip(), "words_json": words})
    return segments


def combine_passes(raw, normalized):
    """Prefer the pass with more aligned speech, then fill disjoint gaps only."""
    count = lambda rows: sum(sum(any(c.isalnum() for c in w["word"]) for w in s["words_json"]) for s in rows)
    prefer_normalized = count(normalized) > count(raw)
    primary, extra = (normalized, raw) if prefer_normalized else (raw, normalized)
    combined = list(primary)
    for segment in extra:
        # Small ASR timestamp shifts must not duplicate the same spoken phrase.
        if not any(segment["start_ms"] < item["end_ms"] + 150 and
                   segment["end_ms"] > item["start_ms"] - 150 for item in combined):
            combined.append(segment)
    return sorted(combined, key=lambda s: (s["start_ms"], s["end_ms"])), "speech_normalized" if prefer_normalized else "original"


def transcribe_clip(source: Path, scratch: Path, *, start_ms: int, end_ms: int,
                    language: str, settings, cancelled=None, progress=None) -> dict:
    if not 0 <= start_ms < end_ms:
        raise MediaError("invalid_clip", "Batas klip tidak valid untuk pembuatan subtitle.")
    scratch.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    # Context on both sides helps ASR finish words near either cut. Output is
    # still clamped to the requested clip; EOF simply shortens the extraction.
    offset = max(0, start_ms - 2000)
    duration = end_ms - offset + 2000
    audio = scratch / "clip-speech.wav"
    normalized_audio = scratch / "clip-speech-normalized.wav"
    try:
        ffmpeg(["-ss", f"{offset / 1000:.3f}", "-i", source, "-t", f"{duration / 1000:.3f}",
                "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", audio],
               binary=settings.ffmpeg_path, timeout=settings.media_timeout_seconds, cancelled=cancelled)
        def decode(path, directory, base_progress):
            return transcribe(path, directory, model=getattr(settings, "whisper_subtitle_model", None) or settings.whisper_model,
                            device=settings.whisper_device, compute_type=settings.whisper_compute_type,
                            language=language, cache_dir=settings.whisper_download_root,
                            # Batched inference can collapse 30 seconds into one
                            # segment. A single invalid word then rejects that
                            # whole window. Sequential GPU decoding returns
                            # phrase boundaries and more reliable word alignment.
                            cpu_threads=settings.whisper_cpu_threads, batch_size=1,
                            beam_size=settings.whisper_beam_size, duration_ms=duration,
                            timeout=settings.job_timeout_seconds, cancelled=cancelled,
                            progress=(lambda value: progress(base_progress + (value or 0) * .5)) if progress else None,
                            vad_parameters={"threshold": .35, "min_silence_duration_ms": 300,
                                            "speech_pad_ms": 200})
        result = decode(audio, scratch / "asr", 0)
        raw = _clip_segments(result, offset, start_ms, end_ms)
        if cancelled and cancelled():
            raise Cancelled()
        passes = [{"preprocessing": "original", "recognized_segments": len(result["segments"]),
                   "accepted_segments": len(raw), "runtime": result.get("runtime", {})}]
        # Preserve the source audio. Only this temporary ASR copy boosts quiet
        # speech; the exported video and its sound are never filtered.
        try:
            ffmpeg(["-i", audio, "-af", SPEECH_FILTER, "-c:a", "pcm_s16le", normalized_audio],
                   binary=settings.ffmpeg_path, timeout=settings.media_timeout_seconds, cancelled=cancelled)
            normalized_result = decode(normalized_audio, scratch / "asr-normalized", .5)
            normalized = _clip_segments(normalized_result, offset, start_ms, end_ms)
            passes.append({"preprocessing": "speech_normalized", "recognized_segments": len(normalized_result["segments"]),
                           "accepted_segments": len(normalized), "runtime": normalized_result.get("runtime", {})})
            segments, chosen = combine_passes(raw, normalized)
        except Cancelled:
            raise
        except MediaError as exc:
            if not raw:
                raise
            segments, chosen = raw, "original"
            passes.append({"preprocessing": "speech_normalized", "error_code": exc.code})
        return {**result, "segments": segments, "runtime": {**result.get("runtime", {}),
                "total_ms": round((time.monotonic() - started) * 1000),
                "subtitle_recovery": {"passes": passes, "preferred_pass": chosen,
                                      "recognized_segments": sum(p.get("recognized_segments", 0) for p in passes),
                                      "accepted_segments": len(segments),
                                      "filtered_segments": sum(p.get("recognized_segments", 0) - p.get("accepted_segments", 0) for p in passes)}}}
    finally:
        audio.unlink(missing_ok=True)
        normalized_audio.unlink(missing_ok=True)
