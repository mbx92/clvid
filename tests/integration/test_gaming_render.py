"""Real source-region composition, HUD visibility, audio, subtitles and orientation."""
from copy import deepcopy
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from app.media.probe import probe
from app.media.render import render_clip

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")
pytestmark = pytest.mark.skipif(not shutil.which(FFMPEG) or not shutil.which(FFPROBE), reason="Real FFmpeg required")


def command(args, *, capture=False):
    return subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True, capture_output=capture)


def frame(path, width, height):
    data = command(["-ss", "1", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture=True).stdout
    return np.frombuffer(data, dtype=np.uint8).reshape(height, width, 3)


def settings(**changes):
    layout = {"facecam": {"x": 0, "y": 0, "width": .25, "height": .5},
              "gameplay": {"x": .25, "y": 0, "width": .75, "height": 1},
              "facecam_height": .28, "facecam_fit": "fill", "gameplay_fit": "fit"}
    layout.update(changes)
    return {"mode": "gaming", "tracking": "static", "x": .5, "y": .5, "gaming": layout}


@pytest.fixture
def gaming_source(tmp_path):
    source = tmp_path / "source.mp4"
    filters = ["drawbox=x=0:y=0:w=160:h=180:color=red:t=fill",
               "drawbox=x=160:y=0:w=480:h=360:color=blue:t=fill",
               "drawbox=x=160:y=0:w=20:h=20:color=lime:t=fill",
               "drawbox=x=620:y=0:w=20:h=20:color=yellow:t=fill",
               "drawbox=x=160:y=340:w=20:h=20:color=cyan:t=fill",
               "drawbox=x=620:y=340:w=20:h=20:color=magenta:t=fill"]
    command(["-f", "lavfi", "-i", "color=0x202020:size=640x360:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
             "-t", "5.5", "-vf", ",".join(filters), "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)])
    return source


@pytest.mark.parametrize("width,top,content_top,content_height", [(720, 358, 548, 540), (1080, 538, 824, 810)])
def test_gaming_fit_keeps_four_hud_corners_and_final_subtitles_audio(gaming_source, tmp_path, monkeypatch, width, top, content_top, content_height):
    def never_track(*args, **kwargs):
        raise AssertionError("Gaming must not run face or speaker analysis")
    monkeypatch.setattr("app.media.render.track_clip", never_track)
    crop = settings()
    unchanged = deepcopy(crop)
    height = width * 16 // 9
    result = render_clip(gaming_source, tmp_path / "output", {"start_ms": 0, "end_ms": 5000, "crop_json": crop,
                         "subtitle_style_json": {"enabled": True, "safe_margin": .05},
                         "cues": [{"start_ms": 0, "end_ms": 5000, "text": "HUD tetap terlihat."}]},
                         {"width": width}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    image = frame(result["mp4"], width, height)
    assert image[top // 2, width // 2, 0] > 220 and image[top // 2, width // 2, 2] < 20
    expected = [(15, content_top + 15, (0, 255, 0)), (width - 15, content_top + 15, (255, 255, 0)),
                (15, content_top + content_height - 15, (0, 255, 255)),
                (width - 15, content_top + content_height - 15, (255, 0, 255))]
    for x, y, color in expected:
        assert np.max(np.abs(image[y, x].astype(int) - color)) < 20, (x, y, image[y, x])
    assert np.max(np.abs(image[top + 20, width // 2].astype(int) - (24, 27, 26))) < 8
    caption_area = image[round(height * .87):]
    assert np.count_nonzero(np.all(caption_area > 210, axis=2)) > 20
    assert "HUD tetap terlihat." in result["srt"].read_text(encoding="utf-8")
    meta = probe(result["mp4"], binary=FFPROBE)
    assert (meta["width"], meta["height"], meta["sample_aspect_ratio"], meta["rotation"], meta["fps"]) == (width, height, 1, 0, 30)
    assert meta["video_codec"] == "h264" and meta["audio_codec"] == "aac" and meta["audio_channels"] == 1
    assert abs(meta["duration_ms"] - 5000) <= 100
    audio = np.frombuffer(command(["-i", str(result["mp4"]), "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "pipe:1"], capture=True).stdout, dtype="<f4")
    assert .04 < float(np.sqrt(np.mean(audio * audio))) < .15
    frequency = np.argmax(np.abs(np.fft.rfft(audio))) * 8000 / len(audio)
    assert abs(frequency - 440) < 2
    framing = result["meta"]["framing"]
    assert framing["layout"] == "gaming" and framing["method"] == "gaming-layout-1" and framing["analysis_reused"] is False
    assert framing["panel_heights"]["facecam"] == top and "detected_frames" not in framing
    assert crop == unchanged and framing["gaming"] == crop["gaming"]


@pytest.mark.parametrize("split", [.15, .45])
def test_panel_ratio_limits_and_explicit_gameplay_fill(gaming_source, tmp_path, split):
    result = render_clip(gaming_source, tmp_path / "output", {"start_ms": 0, "end_ms": 5000,
                         "crop_json": settings(facecam_height=split, gameplay_fit="fill"),
                         "subtitle_style_json": {"enabled": False}}, {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    image = frame(result["mp4"], 720, 1280)
    boundary = 192 if split == .15 else 576
    assert image[boundary - 5, 360, 0] > 220
    assert image[boundary + 5, 360, 2] > 220
    assert image[1270, 360, 2] > 220
    assert result["meta"]["framing"]["panel_heights"]["facecam"] == boundary


def test_minimum_regions_at_source_corners_accept_odd_source_pixels(gaming_source, tmp_path):
    crop = settings(facecam={"x": .98, "y": 0, "width": .02, "height": .02},
                    gameplay={"x": .98, "y": .98, "width": .02, "height": .02}, gameplay_fit="fill")
    result = render_clip(gaming_source, tmp_path / "output", {"start_ms": 0, "end_ms": 5000, "crop_json": crop,
                         "subtitle_style_json": {"enabled": False}}, {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    image = frame(result["mp4"], 720, 1280)
    assert np.max(np.abs(image[180, 360].astype(int) - (255, 255, 0))) < 20
    assert np.max(np.abs(image[820, 360].astype(int) - (255, 0, 255))) < 20


def test_rotated_anamorphic_source_regions_use_upright_display_coordinates(tmp_path):
    coded, source = tmp_path / "coded.mp4", tmp_path / "rotated.mp4"
    command(["-f", "lavfi", "-i", "color=red:size=640x360:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
             "-t", "5.5", "-vf", "drawbox=x=320:y=0:w=320:h=180:color=lime:t=fill,drawbox=x=0:y=180:w=320:h=180:color=blue:t=fill,drawbox=x=320:y=180:w=320:h=180:color=yellow:t=fill,setsar=2/1",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(coded)])
    help_text = subprocess.run([FFMPEG, "-hide_banner", "-h", "full"], capture_output=True, check=True).stdout
    before = ["-display_rotation:v:0", "90"] if b"-display_rotation" in help_text else []
    after = [] if before else ["-metadata:s:v:0", "rotate=90"]
    command([*before, "-i", str(coded), "-c", "copy", *after, str(source)])
    meta = probe(source, binary=FFPROBE)
    assert (meta["display_width"], meta["display_height"], meta["sample_aspect_ratio"]) == (360, 1280, 2)
    assert meta["rotation"] in (90, 270)
    crop = settings(facecam={"x": 0, "y": 0, "width": .5, "height": .5},
                    gameplay={"x": .5, "y": .5, "width": .5, "height": .5})
    result = render_clip(source, tmp_path / "output", {"start_ms": 0, "end_ms": 5000, "crop_json": crop,
                         "subtitle_style_json": {"enabled": False}}, {"width": 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    image = frame(result["mp4"], 720, 1280)
    face_channel, game_channel = (1, 2) if meta["rotation"] == 90 else (2, 1)
    assert image[180, 360, face_channel] > 220 and image[180, 360, 0] < 20
    assert image[820, 360, game_channel] > 220 and image[820, 360, 0] < 20
    assert result["meta"]["framing"]["source_display_size"] == {"width": 360, "height": 1280}
