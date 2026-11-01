"""Real FFmpeg render from a trusted cached path with actual subtitle burn-in."""
from copy import deepcopy
import os
import shutil
import subprocess

import pytest

from app.media.render import render_clip

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")
pytestmark = pytest.mark.skipif(not shutil.which(FFMPEG) or not shutil.which(FFPROBE), reason="Real FFmpeg required")


@pytest.mark.parametrize("cut", [False, True])
def test_reused_dynamic_path_keeps_crop_subtitles_and_skips_tracker(tmp_path, monkeypatch, cut):
    source = tmp_path / "colors.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=red:size=320x360:rate=30",
                    "-f", "lavfi", "-i", "color=blue:size=320x360:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                    "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]", "-map", "[v]", "-map", "2:a", "-t", "5.5",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)], check=True)
    frames = [{"t_ms": 0, "x": 0., "y": .5, "cut": True}, {"t_ms": 5000, "x": 1., "y": .5}]
    if cut:
        frames.insert(1, {"t_ms": 2500, "x": 1., "y": .5, "cut": True})
    cached = {"mode": "face", "method": "yunet-face-v1", "fallback_reason": None, "warnings": [],
              "detected_frames": 30, "total_frames": 30, "keyframes": frames}
    unchanged = deepcopy(cached)
    def never_analyze(*args, **kwargs):
        raise AssertionError("Cached render must not invoke the tracker")
    monkeypatch.setattr("app.media.render.track_clip", never_analyze)
    stages = []
    result = render_clip(source, tmp_path / "output", {"start_ms": 0, "end_ms": 5000,
                         "crop_json": {"mode": "fill", "tracking": "face", "x": .5, "y": .5},
                         "subtitle_style_json": {"enabled": True},
                         "cues": [{"start_ms": 0, "end_ms": 5000, "text": "Teks cache teruji."}]},
                         {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE,
                         tracking_result=cached, stage=stages.append)
    colors = []
    for second in (1, 4):
        pixel = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(second), "-i", str(result["mp4"]),
                                "-vf", "crop=2:2:360:300,scale=1:1", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                               capture_output=True, check=True).stdout
        colors.append(tuple(pixel))
    assert colors[0][0] > 180 and colors[0][2] < 40
    assert colors[1][2] > 180 and colors[1][0] < 40
    # A cut must hold the old crop until its timestamp; a smooth path must
    # already span both source colors before the midpoint.
    checks = [(2.4, 600, "red"), (2.6, 100, "blue")] if cut else [(2, 100, "red"), (2, 600, "blue")]
    for second, x, expected in checks:
        pixel = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(second), "-i", str(result["mp4"]),
                                "-vf", f"crop=2:2:{x}:300,scale=1:1", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                               capture_output=True, check=True).stdout
        r, _, b = pixel
        assert (r > 180 and b < 40) if expected == "red" else (b > 180 and r < 40)
    caption_pixels = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", "1", "-i", str(result["mp4"]),
                                    "-vf", "crop=720:420:0:860", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                   capture_output=True, check=True).stdout
    white_pixels = sum(1 for r, g, b in zip(caption_pixels[0::3], caption_pixels[1::3], caption_pixels[2::3]) if min(r, g, b) > 210)
    assert white_pixels > 20  # Colored fixture has no white pixels without subtitles.
    assert "Teks cache teruji." in result["srt"].read_text(encoding="utf-8")
    assert result["meta"]["framing"]["analysis_reused"] is True
    assert result["meta"]["framing"]["keyframes"] == unchanged["keyframes"]
    assert cached == unchanged and stages == ["render"]
    assert abs(result["meta"]["duration_ms"] - 5000) <= 100
