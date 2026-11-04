import json
from pathlib import Path
from app.media.process import MediaError, run_process, ffmpeg
from app.media.probe import probe
from .captions import story_captions

def normalize_upload(path, suffix, settings):
    result = run_process([settings.ffprobe_path, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-show_format", "-of", "json", str(path)], timeout=30)
    try:
        data = json.loads(result.stdout)
        if result.returncode:
            raise ValueError()
        streams = data["streams"]
        image = suffix in (".png", ".jpg", ".jpeg")
        kind = "image" if image else "video" if suffix == ".mp4" else "audio"
        stream = next(s for s in streams if s["codec_type"] == ("audio" if kind == "audio" else "video"))
        duration = round(float(data["format"].get("duration", 0)) * 1000)
        if not image and not 0 < duration <= 180000:
            raise ValueError()
        if kind != "audio" and not (0 < stream["width"] <= 4096 and 0 < stream["height"] <= 4096):
            raise ValueError()
        if image and stream.get("codec_name") not in ("png", "mjpeg"):
            raise ValueError()
    except (ValueError, KeyError, StopIteration, TypeError):
        raise MediaError("story_media_invalid", "Aset tidak valid. Maksimal durasi 3 menit dan ukuran gambar/video 4096 piksel per sisi.")
    output = path.with_suffix({"image": ".png", "video": ".mp4", "audio": ".m4a"}[kind])
    args = ["-protocol_whitelist", "file,pipe", "-i", str(path), "-map_metadata", "-1"]
    if image:
        args += ["-frames:v", "1", "-vf", "scale=1920:1920:force_original_aspect_ratio=decrease", "-update", "1"]
    elif kind == "video":
        args += ["-map", "0:v:0", "-an", "-vf", "scale=1920:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1", "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    else:
        args += ["-map", "0:a:0", "-vn", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart"]
    try:
        ffmpeg([*args, str(output)], binary=settings.ffmpeg_path, timeout=300)
        if kind == "video":
            duration = probe(output, binary=settings.ffprobe_path)["duration_ms"]
        return output, {"image": "image/png", "video": "video/mp4", "audio": "audio/mp4"}[kind], {"story_kind": kind, "duration_ms": duration}
    except Exception:
        output.unlink(missing_ok=True)
        raise

def render_story(document, assets, directory, settings, ctx):
    import shutil
    from app.storage.local import LocalStorage
    from app.media.render import check_disk
    from app.media.subtitles import to_srt
    duration = sum(s["duration_ms"] for s in document["scenes"])
    check_disk(directory, duration * 4000)
    media = {}
    for asset in assets:
        path = LocalStorage().path(asset.storage_key)
        target = directory / (asset.id + path.suffix)
        shutil.copyfile(path, target)
        media[asset.id] = {"path": str(target.resolve()), "kind": asset.meta_json["story_kind"], "mime": asset.mime}
    width, height = {"portrait": (720, 1280), "landscape": (1280, 720), "square": (1080, 1080)}[document["aspect"]]
    output = directory / "story.partial.mp4"
    manifest = directory / "story.json"
    manifest.write_text(json.dumps({"version": 1, "document": document, "assets": media,
                                   "width": width, "height": height, "fps": 30,
                                   "outputPath": str(output.resolve())}), encoding="utf-8")
    script = Path(settings.remotion_script_path).with_name("story-render.mjs")
    ctx.stage("story_render")
    result = run_process([settings.remotion_node_path, str(script), str(manifest)], timeout=settings.media_timeout_seconds, cancelled=ctx.cancelled, progress=ctx.progress, duration_ms=duration)
    if result.returncode or not output.is_file():
        raise MediaError("story_render_failed", "Render storyboard gagal. Periksa aset, lalu coba kembali.")
    final = directory / "story.mp4"
    # Give silent stories an AAC track, too, for reliable browser playback.
    meta = probe(output, binary=settings.ffprobe_path)
    if not meta.get("audio_codec"):
        ffmpeg(["-i", str(output), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-t", str(duration / 1000), "-movflags", "+faststart", str(final)], binary=settings.ffmpeg_path, timeout=settings.media_timeout_seconds, cancelled=ctx.cancelled)
    else:
        output.replace(final)
    meta = probe(final, binary=settings.ffprobe_path)
    if abs(meta["duration_ms"] - duration) > 150 or (meta["width"], meta["height"]) != (width, height):
        raise MediaError("story_render_invalid", "Hasil render tidak sesuai durasi atau ukuran storyboard.")
    srt = directory / "story.srt"
    srt.write_text(to_srt(story_captions(document), duration), encoding="utf-8")
    return final, srt, {**meta, "renderer": "remotion", "storyboard": True}
