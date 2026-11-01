"""Real FFmpeg movement test with a controlled tracking path; no detector mocks in live smoke."""
import os
import shutil
import subprocess

import pytest

from app.media.render import render_clip

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")
pytestmark = pytest.mark.skipif(not shutil.which(FFMPEG) or not shutil.which(FFPROBE), reason="Real FFmpeg required")


def test_render_executes_dynamic_crop_path_and_records_snapshot(tmp_path, monkeypatch):
    source = tmp_path / "colors.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=red:size=320x360:rate=30",
                    "-f", "lavfi", "-i", "color=blue:size=320x360:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                    "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]", "-map", "[v]", "-map", "2:a", "-t", "5.5",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)], check=True)
    controlled = {"mode": "face", "method": "controlled-test-path", "detected_frames": 30, "total_frames": 30,
                  "fallback_reason": None, "warnings": [], "keyframes": [{"t_ms": 0, "x": 0., "y": .5, "cut": True},
                  {"t_ms": 5000, "x": 1., "y": .5}]}
    monkeypatch.setattr("app.media.render.track_clip", lambda *args, **kwargs: controlled)
    result = render_clip(source, tmp_path / "output", {"start_ms": 0, "end_ms": 5000,
                         "crop_json": {"mode": "fill", "tracking": "face", "x": .5, "y": .5},
                         "subtitle_style_json": {"enabled": False}}, {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    colors = []
    for second in (1, 4):
        pixel = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(second), "-i", str(result["mp4"]),
                                "-vf", "crop=2:2:360:300,scale=1:1", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                               capture_output=True, check=True).stdout
        colors.append(tuple(pixel))
    assert colors[0][0] > 180 and colors[0][2] < 40
    assert colors[1][2] > 180 and colors[1][0] < 40
    assert result["meta"]["framing"]["method"] == "controlled-test-path"
    assert abs(result["meta"]["duration_ms"] - 5000) <= 100
