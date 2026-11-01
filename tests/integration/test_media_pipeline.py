"""Real FFmpeg tests; synthetic distributable fixtures generated in tmp_path."""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from app.media.probe import probe, validate_source
from app.media.process import Cancelled, MediaError, run_process
from app.media.render import render_clip

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")
pytestmark = pytest.mark.skipif(not shutil.which(FFMPEG) or not shutil.which(FFPROBE), reason="FFmpeg and FFprobe required for actual media tests")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "8.5", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def test_real_render_precise_trim_subtitles_and_portrait(source, tmp_path):
    meta = validate_source(source, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    assert meta["duration_ms"] == 8500 and meta["browser_compatible"]
    revision = {"start_ms": 1100, "end_ms": 6223, "crop_json": {"mode": "fill", "x": .75, "y": .5},
                "subtitle_style_json": {"enabled": True}, "cues": [{"start_ms": 0, "end_ms": 6000, "text": "Koreksi subtitle nyata."}]}
    output = render_clip(source, tmp_path / "output", revision, {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    assert abs(output["meta"]["duration_ms"] - 5123) <= 100
    assert (output["meta"]["width"], output["meta"]["height"]) == (720, 1280)
    assert "00:00:05,123" in output["srt"].read_text(encoding="utf-8")
    assert "Koreksi subtitle nyata." in output["srt"].read_text(encoding="utf-8")


def test_srt_only_export_preserves_long_text_without_ass_layout(source, tmp_path):
    text = "Koreksi panjang yang disimpan sebagai SRT. " * 25
    output = render_clip(source, tmp_path / "srt-only", {
        "start_ms": 0, "end_ms": 5000,
        "subtitle_style_json": {"enabled": False},
        "cues": [{"start_ms": 0, "end_ms": 5000, "text": text}],
    }, {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    assert text.strip() in output["srt"].read_text(encoding="utf-8")
    assert output["mp4"].exists()
    assert not (tmp_path / "srt-only/captions.ass").exists()


def test_rotated_video_and_fit(source, tmp_path):
    rotated = tmp_path / "rotated.mp4"
    # Rotation fixture syntax changed between Debian FFmpeg 5 and modern builds.
    help_text = subprocess.run([FFMPEG, "-h", "full"], capture_output=True, text=True, check=True).stdout
    before = ["-display_rotation:v:0", "90"] if "-display_rotation" in help_text else []
    after = [] if before else ["-metadata:s:v:0", "rotate=90"]
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *before, "-i", str(source), "-c", "copy", *after, str(rotated)], check=True)
    meta = probe(rotated, binary=FFPROBE)
    assert meta["rotation"] in (90, 270)
    assert meta["display_width"] == 360 and meta["display_height"] == 640
    output = render_clip(rotated, tmp_path / "rotated-output", {"start_ms": 500, "end_ms": 5500, "crop_json": {"mode": "fit"}, "subtitle_style_json": {"enabled": False}}, {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    assert output["meta"]["rotation"] == 0
    assert output["meta"]["sample_aspect_ratio"] == 1
    assert output["meta"]["fps"] == 30


def test_vfr_non_square_pixels_produce_square_pixel_constant_fps(source, tmp_path):
    variable = tmp_path / "variable.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                    "-vf", "select='if(lt(n,60),1,not(mod(n,2)))',setsar=2", "-fps_mode", "vfr",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy", str(variable)], check=True)
    meta = validate_source(variable, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    assert meta["sample_aspect_ratio"] == 2 and meta["display_width"] == 1280
    assert not meta["browser_compatible"]  # A square-pixel proxy avoids browser SAR differences.
    assert meta["fps"] != 30
    output = render_clip(variable, tmp_path / "variable-output", {"start_ms": 1300, "end_ms": 6300,
                         "crop_json": {"mode": "fit"}, "subtitle_style_json": {"enabled": False}},
                         {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    assert output["meta"]["sample_aspect_ratio"] == 1 and output["meta"]["fps"] == 30
    assert abs(output["meta"]["duration_ms"] - 5000) <= 100


def test_actual_crop_alignment_selects_matching_source_side(tmp_path):
    source = tmp_path / "crop-colors.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=red:size=320x360:rate=30",
                    "-f", "lavfi", "-i", "color=green:size=320x360:rate=30",
                    "-f", "lavfi", "-i", "color=blue:size=320x360:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                    "-filter_complex", "[0:v][1:v][2:v]hstack=inputs=3[v]", "-map", "[v]", "-map", "3:a",
                    "-t", "5.5", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)], check=True)
    colors = []
    for x in (0, 1):
        output = render_clip(source, tmp_path / f"side-{x}", {"start_ms": 0, "end_ms": 5000,
                             "crop_json": {"mode": "fill", "x": x, "y": .5}, "subtitle_style_json": {"enabled": False}},
                             {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
        sample = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", "1", "-i", str(output["mp4"]),
                                 "-vf", "crop=2:2:360:300,scale=1:1", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                capture_output=True, check=True).stdout
        colors.append(tuple(sample))
    assert colors[0][0] > 180 and colors[0][2] < 40, colors
    assert colors[1][2] > 180 and colors[1][0] < 40, colors


def test_corrupt_and_no_audio_are_rejected(source, tmp_path):
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not an MP4")
    with pytest.raises(MediaError):
        validate_source(corrupt, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    silent = tmp_path / "no-audio.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-an", "-c:v", "copy", str(silent)], check=True)
    with pytest.raises(MediaError) as failure:
        validate_source(silent, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    assert failure.value.code == "no_audio"


def test_disguised_playlist_cannot_fetch_external_content(tmp_path):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(404)
            self.end_headers()
        def log_message(self, *_):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        playlist = tmp_path / "looks-like-video.mp4"
        playlist.write_text(f"#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nhttp://127.0.0.1:{server.server_port}/private.ts\n#EXT-X-ENDLIST\n", encoding="utf-8")
        with pytest.raises(MediaError):
            probe(playlist, binary=FFPROBE)
        assert requests == []
    finally:
        server.shutdown()
        server.server_close()


def test_cancellation_waits_until_subprocess_stops(tmp_path):
    started = time.monotonic()
    with pytest.raises(Cancelled):
        run_process([FFMPEG, "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30", "-t", "30", "-f", "null", "-"], cancelled=lambda: time.monotonic() - started > .6)
    assert time.monotonic() - started < 6
