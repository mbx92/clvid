"""Opt-in Remotion captions and video effects over the framed FFmpeg clip."""
from copy import deepcopy
import json
import logging
from pathlib import Path

from .probe import browser_compatible, probe
from .process import Cancelled, MediaError, ffmpeg, run_process


# This version is part of the queued export fingerprint. Bump it whenever the
# composition or its contract changes, so an old job cannot use new visuals.
REMOTION_RENDERER_VERSION = "3"
logger = logging.getLogger(__name__)


def render_remotion(source, directory, snapshot, config, *, prepare, node_path="node",
                    script_path="/opt/remotion/render.mjs", ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe",
                    fonts_dir=None, tracking_model_path=None, tracking_source=None, speaker_model_path=None,
                    tracking_result=None, stage=None, timeout=14400, cancelled=None, progress=None):
    from .render import check_disk

    if config.get("renderer_version") != REMOTION_RENDERER_VERSION:
        raise MediaError("remotion_version_changed", "Versi template Remotion berubah. Buat ekspor baru untuk revisi ini.")
    if not Path(script_path).is_file():
        raise MediaError("remotion_unavailable", "Remotion belum terpasang pada worker. Perbarui layanan worker, lalu coba ekspor lagi.")
    duration = snapshot["end_ms"] - snapshot["start_ms"]
    width = config.get("width", config.get("resolution", 1080))
    if width not in (720, 1080) or duration <= 0:
        raise MediaError("invalid_render", "Resolusi atau durasi ekspor tidak valid.")
    height = width * 16 // 9
    directory = Path(directory).resolve()
    check_disk(directory, duration * 4000)
    prepared_directory = directory / "prepared"
    manifest_path = directory / "remotion.json"
    rendered = directory / "remotion.partial.mp4"
    partial, output = directory / "clip.partial.mp4", directory / "clip.mp4"
    prepared_snapshot = deepcopy(snapshot)
    prepared_snapshot.setdefault("subtitle_style_json", {})["enabled"] = False
    try:
        prepared = prepare(source, prepared_directory, prepared_snapshot, config,
                           ffmpeg_bin=ffmpeg_bin, ffprobe_bin=ffprobe_bin, fonts_dir=fonts_dir,
                           tracking_model_path=tracking_model_path, tracking_source=tracking_source,
                           speaker_model_path=speaker_model_path, tracking_result=tracking_result,
                           stage=stage, timeout=timeout, cancelled=cancelled, progress=progress)
        style = snapshot.get("subtitle_style_json", {})
        # Hidden captions still belong in the downloadable SRT, but the visual
        # renderer does not need their text or any word-level render events.
        events = snapshot.get("subtitle_events", snapshot.get("cues", [])) if style.get("enabled", True) else []
        manifest = dict(version=1, videoPath=str(prepared["mp4"].resolve()), outputPath=str(rendered),
                        durationMs=duration, width=width, height=height, fps=30,
                        cues=events, style=style)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        if stage:
            stage("render_remotion")
        try:
            result = run_process([node_path, str(Path(script_path).resolve()), str(manifest_path)],
                                 timeout=timeout, cancelled=cancelled, progress=progress, duration_ms=duration)
        except OSError as exc:
            raise MediaError("remotion_unavailable", "Remotion tidak dapat dijalankan. Periksa instalasi Node dan browser pada worker.") from exc
        if result.returncode or not rendered.is_file():
            # Browser diagnostics can contain serialized props or caption text.
            # Log process status only; keep user media metadata out of logs.
            logger.error("Remotion render failed (exit=%s, output_present=%s)", result.returncode, rendered.is_file())
            raise MediaError("remotion_render_failed", "Remotion gagal merender template. Coba ekspor ulang; jika tetap gagal, periksa log worker Remotion.")
        if stage:
            stage("finalize_render")
        # Explicit maps select only Remotion's picture and the prepared clip's
        # audio. No browser audio is mixed or encoded for a second time.
        ffmpeg(["-protocol_whitelist", "file,pipe", "-i", str(rendered),
                "-protocol_whitelist", "file,pipe", "-i", str(prepared["mp4"]),
                "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-t", str(duration / 1000),
                "-map_metadata", "-1", "-movflags", "+faststart", str(partial)],
               binary=ffmpeg_bin, timeout=timeout, cancelled=cancelled, progress=progress, duration_ms=duration)
        meta = probe(partial, binary=ffprobe_bin, cancelled=cancelled)
        if (not browser_compatible(meta) or abs(meta["duration_ms"] - duration) > 150 or
                (meta["width"], meta["height"]) != (width, height) or abs(meta.get("fps", 0) - 30) > .01):
            raise MediaError("invalid_render", "Hasil Remotion tidak sesuai durasi, resolusi, atau format ekspor yang diminta.")
        meta.update(framing=prepared["meta"]["framing"], renderer="remotion",
                    renderer_version=REMOTION_RENDERER_VERSION,
                    remotion_template=snapshot.get("subtitle_style_json", {}).get("remotion_template", "gaming"))
        if cancelled and cancelled():
            raise Cancelled()
        partial.replace(output)
        return dict(mp4=output, srt=prepared["srt"], meta=meta)
    finally:
        # Keep small manifests/captions for normal scratch TTL cleanup, but do
        # not retain two additional video copies after success or cancellation.
        rendered.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
        (prepared_directory / "clip.mp4").unlink(missing_ok=True)
