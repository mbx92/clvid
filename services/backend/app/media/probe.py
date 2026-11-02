import json
from fractions import Fraction
from pathlib import Path

from .process import MediaError, ffmpeg, run_process


def ratio(value, default=1):
    try:
        return float(Fraction(str(value).replace(":", "/")))
    except (ValueError, ZeroDivisionError):
        return default


def browser_compatible(meta):
    return (meta.get("video_codec") == "h264" and meta.get("pixel_format") == "yuv420p"
            and meta.get("audio_codec") == "aac" and meta.get("sample_aspect_ratio", 1) == 1
            and meta.get("rotation", 0) == 0)


def probe(path, *, binary="ffprobe", timeout=120, cancelled=None):
    result = run_process([binary, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams",
                          "-show_format", "-of", "json", str(Path(path).resolve())], timeout=timeout, cancelled=cancelled)
    try:
        if result.returncode:
            raise ValueError()
        data = json.loads(result.stdout)
        video = next(s for s in data["streams"] if s.get("codec_type") == "video")
        audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
        fmt = data["format"]
        rotation = int(float(video.get("tags", {}).get("rotate", 0)))
        for side in video.get("side_data_list", []):
            rotation = int(side.get("rotation", rotation))
        rotation %= 360
        w, h = int(video["width"]), int(video["height"])
        sar = ratio(video.get("sample_aspect_ratio", "1:1"))
        dw, dh = round(w * sar), h
        if rotation in (90, 270):
            dw, dh = dh, dw
        meta = dict(duration_ms=round(float(fmt.get("duration", video.get("duration", 0))) * 1000),
                    width=w, height=h, display_width=dw, display_height=dh, sample_aspect_ratio=sar,
                    rotation=rotation, fps=ratio(video.get("avg_frame_rate", "0"), 0),
                    video_codec=video.get("codec_name"), pixel_format=video.get("pix_fmt"),
                    audio_codec=audio.get("codec_name") if audio else None,
                    audio_channels=audio.get("channels") if audio else None,
                    audio_stream=audio["index"] if audio else None,
                    format=fmt.get("format_name", ""), major_brand=fmt.get("tags", {}).get("major_brand", ""))
        meta["browser_compatible"] = browser_compatible(meta)
        return meta
    except (ValueError, KeyError, StopIteration, TypeError) as exc:
        raise MediaError("invalid_video", "Berkas video tidak valid atau tidak dapat dibaca.") from exc


def validate_source(path, *, ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe", max_bytes=2147483648,
                    max_seconds=3600, max_width=3840, max_height=2160, validate_decode=True,
                    timeout=14400, cancelled=None, progress=None):
    path = Path(path)
    with path.open("rb") as stream:
        header = stream.read(32)
    if len(header) < 12 or header[4:8] != b"ftyp":
        raise MediaError("invalid_video", "Sumber harus berupa berkas MP4.")
    if path.stat().st_size > max_bytes:
        raise MediaError("file_too_large", "Ukuran video melebihi batas unggahan.")
    meta = probe(path, binary=ffprobe_bin, cancelled=cancelled)
    if "mp4" not in meta["format"]:
        raise MediaError("invalid_video", "Sumber harus berupa berkas MP4.")
    if meta.get("audio_stream") is None:
        raise MediaError("no_audio", "Video harus memiliki audio.")
    if meta["duration_ms"] <= 0:
        raise MediaError("invalid_duration", "Durasi video tidak valid.")
    if meta["duration_ms"] > max_seconds * 1000:
        raise MediaError("duration_limit", f"Durasi video {meta['duration_ms']/60000:.1f} menit melebihi batas {max_seconds/60:g} menit. Naikkan batas durasi di Pengaturan lalu coba lagi.")
    dimensions = sorted((meta["display_width"], meta["display_height"]))
    if any(v > limit for v, limit in zip(dimensions, sorted((max_width, max_height)))):
        raise MediaError("invalid_resolution", "Resolusi video melebihi batas.")
    meta["browser_compatible"] = browser_compatible(meta)
    if validate_decode:
        ffmpeg(["-xerror", "-err_detect", "explode", "-protocol_whitelist", "file,pipe", "-i", str(path),
                "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], binary=ffmpeg_bin,
               timeout=timeout, cancelled=cancelled, progress=progress, duration_ms=meta["duration_ms"])
    return meta
