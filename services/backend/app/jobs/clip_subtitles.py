"""Recover speech for a saved clip without overwriting edits or old transcripts."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from sqlalchemy import select

from app.ai.clip_transcribe import transcribe_clip
from app.ai.subtitle_recovery_config import settings_for_recovery
from app.db import session_scope
from app.domain.models import Asset, Clip, ClipRevision, SubtitleCue, Transcript, TranscriptSegment, utcnow
from app.media.process import MediaError
from app.media.subtitles import transcript_cues
from app.storage.local import LocalStorage


def _inputs(db, ctx):
    job, project = ctx.check(db)
    clip = db.scalar(select(Clip).where(Clip.id == job.input_json["clip_id"]).with_for_update())
    revision = db.get(ClipRevision, job.input_json["clip_revision_id"])
    if not clip or clip.project_id != project.id or not revision or revision.clip_id != clip.id:
        raise MediaError("clip_missing", "Klip tidak tersedia untuk pembuatan subtitle.")
    if clip.active_revision_id != revision.id:
        raise MediaError("revision_conflict", "Klip berubah selama pembuatan subtitle. Muat revisi terbaru lalu coba kembali.")
    if job.input_json.get("replace_existing") is not True and db.scalar(select(SubtitleCue.id).where(SubtitleCue.clip_revision_id == revision.id).limit(1)):
        raise MediaError("subtitles_exist", "Klip sudah memiliki subtitle. Subtitle yang telah diedit tidak akan ditimpa.")
    source = db.get(Asset, project.source_asset_id) if project.source_asset_id else None
    if (not source or source.id != job.input_json["source_asset_id"] or source.project_id != project.id
            or source.state != "ready" or not 0 <= revision.start_ms < revision.end_ms <= source.meta_json.get("duration_ms", 0)):
        raise MediaError("source_not_ready", "Video sumber berubah atau belum tersedia untuk pembuatan subtitle.")
    return job, project, clip, revision, source


def _slice_segment(segment, start_ms, end_ms):
    """Keep only the part of a previous segment outside the recovered interval."""
    pieces = transcript_cues([segment], start_ms, end_ms)
    words = [word for word in segment.get("words_json") or []
             if isinstance(word, dict) and isinstance(word.get("word"), str)
             and type(word.get("start_ms")) is int and type(word.get("end_ms")) is int
             and word["end_ms"] > word["start_ms"]]
    for piece in pieces:
        piece["start_ms"] += start_ms
        piece["end_ms"] += start_ms
        piece["words_json"] = ([{**word, "start_ms": max(piece["start_ms"], word["start_ms"]),
                                 "end_ms": min(piece["end_ms"], word["end_ms"])}
                                for word in words if word["end_ms"] > piece["start_ms"] and word["start_ms"] < piece["end_ms"]]
                               if words else None)
    return pieces


def merged_segments(previous, recovered, start_ms, end_ms):
    merged = []
    for segment in previous:
        if segment["end_ms"] <= start_ms or segment["start_ms"] >= end_ms:
            merged.append(deepcopy(segment))
        else:
            if segment["start_ms"] < start_ms:
                merged.extend(_slice_segment(segment, segment["start_ms"], start_ms))
            if segment["end_ms"] > end_ms:
                merged.extend(_slice_segment(segment, end_ms, segment["end_ms"]))
    merged.extend(deepcopy(recovered))
    return sorted(merged, key=lambda item: (item["start_ms"], item["end_ms"]))


def generate_subtitles(ctx, scratch: Path):
    # Lazy import keeps the worker's handler registry free of an import cycle.
    from app.jobs.tasks import _complete

    with session_scope() as db:
        job, project, _, saved, source = _inputs(db, ctx)
        recovery_settings, signature = settings_for_recovery(ctx.settings, job.input_json.get("recovery_signature"))
        language = job.input_json.get("language", "auto")
        if language == "auto":
            # A short noisy battle can be misidentified as another language.
            # Reuse the full video's detected language unless explicitly changed.
            base = db.scalar(select(Transcript).where(Transcript.project_id == project.id).order_by(Transcript.version.desc()).limit(1))
            if base and base.language:
                language = base.language
    ctx.stage("subtitle_generate")
    result = transcribe_clip(LocalStorage().path(source.storage_key), scratch,
                             start_ms=saved.start_ms, end_ms=saved.end_ms,
                             language=language, settings=recovery_settings,
                             cancelled=ctx.cancelled, progress=ctx.progress)
    recovered = result["segments"]
    cues = transcript_cues(recovered, saved.start_ms, saved.end_ms)
    with session_scope() as db:
        job, project, clip, saved, _ = _inputs(db, ctx)
        if not cues:
            preserved = bool(db.scalar(select(SubtitleCue.id).where(SubtitleCue.clip_revision_id == saved.id).limit(1)))
            message = "Ucapan belum berhasil dikenali pada audio klip ini. Coba bahasa yang sesuai atau tambahkan subtitle secara manual."
            if preserved:
                message += " Subtitle sebelumnya tetap dipertahankan."
            _complete(db, ctx, {"clip_id": clip.id, "revision": saved.revision, "cues": 0,
                                "preserved_existing": preserved,
                                "recovery_signature": signature, "runtime": result.get("runtime", {}),
                                "message": message})
            return
        # Merge into the newest full project transcript under the project lock.
        # Old revisions keep their original immutable transcript and timings.
        base = db.scalar(select(Transcript).where(Transcript.project_id == project.id).order_by(Transcript.version.desc()).limit(1))
        previous = [{key: getattr(row, key) for key in ("start_ms", "end_ms", "text", "words_json")}
                    for row in db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == base.id).order_by(TranscriptSegment.order))] if base else []
        transcript = Transcript(project_id=project.id, version=base.version + 1 if base else 1,
                                language=base.language if base else result["language"],
                                model=result.get("runtime", {}).get("model") or recovery_settings.whisper_model,
                                config_json={"origin": "clip_subtitles", "base_transcript_id": base.id if base else None,
                                             "clip_id": clip.id, "range_ms": [saved.start_ms, saved.end_ms],
                                             "replace_existing": job.input_json.get("replace_existing") is True,
                                             "recovery_signature": signature,
                                             "language": result["language"], "runtime": result.get("runtime", {})})
        db.add(transcript)
        db.flush()
        for order, segment in enumerate(merged_segments(previous, recovered, saved.start_ms, saved.end_ms)):
            db.add(TranscriptSegment(transcript_id=transcript.id, order=order,
                                     **{key: segment.get(key) for key in ("start_ms", "end_ms", "text", "words_json")}))
        revision = ClipRevision(clip_id=clip.id, revision=saved.revision + 1, transcript_id=transcript.id,
                                start_ms=saved.start_ms, end_ms=saved.end_ms, title=saved.title,
                                reason=saved.reason, topic=saved.topic, crop_json=deepcopy(saved.crop_json),
                                subtitle_style_json=deepcopy(saved.subtitle_style_json))
        db.add(revision)
        db.flush()
        db.add_all(SubtitleCue(clip_revision_id=revision.id, **cue) for cue in cues)
        clip.active_revision_id = revision.id
        project.updated_at = utcnow()
        if project.status == "no_speech":
            project.status, project.error_message = "ready", None
        _complete(db, ctx, {"clip_id": clip.id, "revision": revision.revision, "cues": len(cues),
                            "recovery_signature": signature, "runtime": result.get("runtime", {}),
                            "transcript_id": transcript.id, "message": f"{len(cues)} subtitle berhasil dibuat dari audio klip."})
