from copy import deepcopy
import math
from pathlib import Path
import shutil

from .gaming import finite, gaming_filter
from .probe import probe, browser_compatible
from .process import MediaError, ffmpeg
from .subtitles import to_ass, to_srt
from .tracking import track_clip, write_tracking_commands
from .tracking_versions import TRACKING_METHODS, SAMPLE_FPS


def check_disk(path, estimated_bytes=0, min_free_bytes=1073741824):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(path).free < estimated_bytes + min_free_bytes:
        raise MediaError("insufficient_disk", "Ruang penyimpanan tidak cukup untuk memproses video.")


def framing_filter(crop, width, height):
    x, y = crop.get("x", .5), crop.get("y", .5)
    if not finite(x, 0, 1) or not finite(y, 0, 1) or crop.get("mode", "fill") not in ("fit", "fill"):
        raise MediaError("invalid_crop", "Posisi crop tidak valid.")
    if crop.get("mode") == "fit":
        return f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x181b1a,setsar=1"
    return f"scale={width}:{height}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={width}:{height}:(iw-ow)*{x:.6f}:(ih-oh)*{y:.6f},setsar=1"


def reusable_tracking_result(value, crop, duration_ms):
    if not isinstance(value, dict) or crop.get("mode", "fill") != "fill" or crop.get("tracking") not in TRACKING_METHODS:
        return None
    mode = crop["tracking"]
    if value.get("mode") != mode or value.get("method") != TRACKING_METHODS[mode]:
        return None
    total, detected = value.get("total_frames"), value.get("detected_frames")
    limit = math.ceil(duration_ms*SAMPLE_FPS/1000)+2
    if type(total) is not int or type(detected) is not int or not 0 <= detected <= total or not 0 < total <= limit:
        return None
    reason = value.get("fallback_reason")
    if reason and not (detected == 0 and reason == "Wajah tidak terdeteksi; posisi manual digunakan."):
        return None
    frames = value.get("keyframes")
    if not isinstance(frames, list) or not 0 < len(frames) <= limit:
        return None
    previous = -1
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict):
            return None
        t = frame.get("t_ms")
        if type(t) is not int or not previous < t <= duration_ms or (i == 0 and t != 0):
            return None
        if not all(finite(frame.get(axis), 0, 1) for axis in ("x", "y")) or type(frame.get("cut", False)) is not bool:
            return None
        previous = t
    return deepcopy(value)


def filter_path(path):
    # These paths are server-generated, but quoting also supports user-chosen
    # storage roots containing punctuation. Filter escaping is separate from argv.
    return str(Path(path).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"'\''")


def prepare_preview(source, directory, *, duration_ms, ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe",
                    validate_decode=True, max_width=1280, threads=4, timeout=14400, cancelled=None, progress=None):
    directory = Path(directory)
    check_disk(directory, duration_ms*1000)
    partial, output = directory/"preview.partial.mp4", directory/"preview.mp4"
    try:
        strict = ["-xerror", "-err_detect", "explode"] if validate_decode else []
        # First normalize display geometry (including SAR) and cap dimensions.
        vf = f"scale=iw*sar:ih,setsar=1,scale='min({max_width},iw)':-2,fps=30,format=yuv420p"
        ffmpeg([*strict, "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0",
                "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-threads", str(threads),
                "-c:a", "aac", "-b:a", "128k", "-map_metadata", "-1", "-movflags", "+faststart", str(partial)],
               binary=ffmpeg_bin, timeout=timeout, cancelled=cancelled, progress=progress, duration_ms=duration_ms)
        meta = probe(partial, binary=ffprobe_bin)
        if not browser_compatible(meta) or abs(meta["duration_ms"]-duration_ms) > 150:
            raise MediaError("invalid_preview", "Pratinjau tidak sesuai durasi atau format sumber.")
        partial.replace(output)
        return dict(path=output, meta=meta)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def render_clip(source, directory, snapshot, config, *, ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe",
                fonts_dir=None, tracking_model_path=None, tracking_source=None, speaker_model_path=None,
                tracking_result=None, stage=None, timeout=14400, cancelled=None, progress=None):
    directory = Path(directory)
    start, end = snapshot["start_ms"], snapshot["end_ms"]
    duration = end-start
    width = config.get("width", config.get("resolution", 1080))
    if width not in (720, 1080) or duration <= 0:
        raise MediaError("invalid_render", "Resolusi atau durasi ekspor tidak valid.")
    height = width*16//9
    check_disk(directory, duration*2000)
    source_meta = probe(source, binary=ffprobe_bin)
    crop, style = snapshot.get("crop_json", {}), snapshot.get("subtitle_style_json", {})
    cues = snapshot.get("cues", [])
    srt = directory/"captions.srt"
    srt.write_text(to_srt(cues, duration), encoding="utf-8")
    final = "fps=30,format=yuv420p"
    if style.get("enabled", True) and cues:
        ass = directory/"captions.ass"
        ass.write_text(to_ass(snapshot.get("subtitle_events", cues), duration, style, width, height), encoding="utf-8")
        final = f"ass=filename='{filter_path(ass)}'" + (f":fontsdir='{filter_path(fonts_dir)}'" if fonts_dir else "") + "," + final
    framing = dict(mode="static", method="manual", keyframes=[dict(t_ms=0, x=crop.get("x", .5), y=crop.get("y", .5))])
    if crop.get("mode") == "gaming":
        graph, framing = gaming_filter(crop, source_meta, width, height, final_filters=final)
    else:
        dynamic = ""
        if crop.get("mode", "fill") == "fill" and crop.get("tracking") in TRACKING_METHODS:
            framing = reusable_tracking_result(tracking_result, crop, duration)
            reused = framing is not None
            if not reused:
                if stage:
                    stage("track_faces")
                framing = track_clip(tracking_source or source, directory, start_ms=start, end_ms=end, crop=crop,
                                     ffmpeg_bin=ffmpeg_bin, model_path=tracking_model_path, speaker_model_path=speaker_model_path,
                                     timeout=timeout, cancelled=cancelled, progress=progress)
            framing["analysis_reused"] = reused
            commands = directory/"tracking.cmd"
            write_tracking_commands(commands, framing["keyframes"])
            dynamic = f"sendcmd=f='{filter_path(commands)}',"
        sw, sh = source_meta.get("display_width", source_meta["width"]), source_meta.get("display_height", source_meta["height"])
        # sendcmd precedes crop; its expressions are then evaluated by crop at
        # every frame, interpolating between observations without frame jumps.
        graph = f"[0:v:0]setpts=PTS-STARTPTS,scale={sw}:{sh},setsar=1,{dynamic}{framing_filter(crop, width, height)},{final}[v]"
    script = directory/"render.filter"
    script.write_text(graph, encoding="utf-8")
    partial, output = directory/"clip.partial.mp4", directory/"clip.mp4"
    if stage:
        stage("render")
    try:
        ffmpeg(["-xerror", "-err_detect", "explode", "-protocol_whitelist", "file,pipe", "-ss", str(start/1000), "-i", str(source),
                "-t", str(duration/1000), "-filter_complex_threads", "2", "-filter_complex_script", str(script), "-map", "[v]", "-map", "0:a:0",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-threads", "4", "-c:a", "aac", "-b:a", "192k",
                "-map_metadata", "-1", "-movflags", "+faststart", str(partial)], binary=ffmpeg_bin,
               timeout=timeout, cancelled=cancelled, progress=progress, duration_ms=duration)
        meta = probe(partial, binary=ffprobe_bin)
        if abs(meta["duration_ms"]-duration) > 150 or (meta["width"], meta["height"]) != (width, height):
            raise MediaError("invalid_render", "Hasil ekspor tidak sesuai durasi atau resolusi yang diminta.")
        framing.setdefault("analysis_reused", False)
        meta["framing"] = framing
        partial.replace(output)
        return dict(mp4=output, srt=srt, meta=meta)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
