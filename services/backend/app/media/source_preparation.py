from .probe import validate_source
from .render import prepare_preview


def prepare_source(source, directory, *, settings, stage=None, cancelled=None, progress=None):
    kwargs = dict(ffmpeg_bin=settings.ffmpeg_path, ffprobe_bin=settings.ffprobe_path,
                  max_bytes=settings.max_upload_bytes, max_seconds=settings.max_video_seconds,
                  max_width=settings.max_video_width, max_height=settings.max_video_height,
                  timeout=settings.media_timeout_seconds, cancelled=cancelled, progress=progress)
    meta = validate_source(source, validate_decode=False, **kwargs)
    if meta["browser_compatible"]:
        return validate_source(source, **kwargs), None
    if stage:
        stage("prepare_preview")
    preview = prepare_preview(source, directory, duration_ms=meta["duration_ms"],
                              ffmpeg_bin=settings.ffmpeg_path, ffprobe_bin=settings.ffprobe_path,
                              max_width=settings.preview_max_width, threads=settings.preview_threads,
                              validate_decode=True, timeout=settings.media_timeout_seconds,
                              cancelled=cancelled, progress=progress)
    return meta, preview
