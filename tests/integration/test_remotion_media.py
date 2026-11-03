"""Real bundled Remotion render, caption motion, word gaps, framing and audio."""
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from app.media.render import render_clip
from app.media.remotion import REMOTION_RENDERER_VERSION

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")
SCRIPT = os.environ.get("REMOTION_SCRIPT_PATH", "/opt/remotion/render.mjs")
pytestmark = pytest.mark.skipif(
    not (Path(SCRIPT).is_file() and os.environ.get("REMOTION_BROWSER_EXECUTABLE")
         and shutil.which(FFMPEG) and shutil.which(FFPROBE)),
    reason="Built Remotion composition, installed browser and FFmpeg required",
)


def command(args):
    return subprocess.run([FFMPEG, "-v", "error", "-y", *args], check=True, capture_output=True).stdout


def frame(path, time):
    raw = command(["-ss", str(time), "-i", str(path), "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    return np.frombuffer(raw, np.uint8).reshape(1280, 720, 3)


def assert_audio(result):
    meta = result["meta"]
    assert (meta["width"], meta["height"], meta["fps"]) == (720, 1280, 30)
    assert meta["video_codec"] == "h264" and meta["audio_codec"] == "aac"
    assert abs(meta["duration_ms"] - 2000) <= 100
    audio = np.frombuffer(command(["-i", str(result["mp4"]), "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"]), "<f4")
    assert .04 < float(np.sqrt(np.mean(audio * audio))) < .15
    peak = np.argmax(np.abs(np.fft.rfft(audio))) * 8000 / len(audio)
    assert abs(peak - 440) < 2


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.mp4"
    command(["-f", "lavfi", "-i", "color=black:s=640x360:r=30",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "3",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)])
    return path


def render(source, output, style, cues, **snapshot):
    return render_clip(source, output, {
        "start_ms": 500, "end_ms": 2500, "crop_json": {"mode": "fill"},
        "subtitle_style_json": {"renderer": "remotion", "font_size": 80, "background": False,
                                "animation_ms": 300, "safe_margin": .1, **style},
        "cues": cues, **snapshot,
    }, {"width": 720, "renderer": "remotion", "renderer_version": REMOTION_RENDERER_VERSION},
        ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE, remotion_script_path=SCRIPT)


@pytest.mark.parametrize("template", ["minimal", "gaming", "cinematic"])
def test_actual_template_animation_and_audio(source, tmp_path, template):
    result = render(source, tmp_path / template, {"remotion_template": template, "animation": "fade"},
                    [{"start_ms": 0, "end_ms": 2000, "text": "MOMEN SERU"}])
    first, entering, settled, ending = (frame(result["mp4"], time) for time in (0, .1, .6, 1.966))
    assert first.max() < 20
    assert settled.sum() > 100000
    assert ending.sum() < settled.sum() * .6
    assert not np.array_equal(entering, settled)
    assert "MOMEN SERU" in result["srt"].read_text()
    assert result["meta"]["remotion_template"] == template
    assert_audio(result)


def test_word_gaps_use_events_and_keep_gaming_layout(source, tmp_path):
    colored = tmp_path / "gaming.mp4"
    command(["-i", str(source), "-vf", "drawbox=x=0:y=0:w=160:h=180:color=red:t=fill,drawbox=x=160:y=0:w=480:h=360:color=blue:t=fill",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy", str(colored)])
    crop = {"mode": "gaming", "gaming": {
        "facecam": {"x": 0, "y": 0, "width": .25, "height": .5},
        "gameplay": {"x": .25, "y": 0, "width": .75, "height": 1},
        "facecam_height": .28, "facecam_fit": "fill", "gameplay_fit": "fit",
    }}
    result = render(colored, tmp_path / "words", {"remotion_template": "minimal", "display_mode": "words"},
                    [{"start_ms": 0, "end_ms": 2000, "text": "SATU DUA"}], crop_json=crop,
                    subtitle_events=[{"start_ms": 0, "end_ms": 500, "text": "SATU"},
                                     {"start_ms": 1200, "end_ms": 2000, "text": "DUA"}])
    # White glyphs must disappear in the real speech gap, including at its exact boundary.
    white = lambda time: np.count_nonzero(np.all(frame(result["mp4"], time) > 210, axis=2))
    assert white(.2) > 100 and white(1.4) > 100
    assert white(.5) == 0 and white(.8) == 0
    picture = frame(result["mp4"], .8)
    assert np.max(np.abs(picture[180, 360].astype(int) - (255, 0, 0))) < 20
    assert np.max(np.abs(picture[800, 360].astype(int) - (0, 0, 255))) < 20
    assert result["meta"]["framing"]["layout"] == "gaming"
    assert result["meta"]["framing"]["gaming"] == crop["gaming"]
    assert "SATU DUA" in result["srt"].read_text()
    assert_audio(result)


def test_intro_outro_render_without_subtitles_and_keep_audio_duration(source, tmp_path):
    result = render(source, tmp_path / "titles", {"enabled": False, "remotion_effects": {
        "intro": {"enabled": True, "text": "PERTARUNGAN DIMULAI", "duration_ms": 500},
        "outro": {"enabled": True, "text": "SAMPAI JUMPA", "duration_ms": 500},
    }}, [{"start_ms": 0, "end_ms": 2000, "text": "Subtitle disembunyikan"}])
    white = lambda time: np.count_nonzero(np.all(frame(result["mp4"], time) > 210, axis=2))
    assert white(.3) > 100 and white(1.7) > 100
    assert white(1) == 0
    assert "Subtitle disembunyikan" in result["srt"].read_text()
    assert_audio(result)


def test_zoom_and_video_fades_change_picture_without_affecting_audio(source, tmp_path):
    portrait = tmp_path / "portrait.mp4"
    command(["-f", "lavfi", "-i", "color=black:s=360x640:r=30",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "3",
             "-vf", "drawbox=x=100:y=300:w=50:h=50:color=red:t=fill",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(portrait)])
    result = render(portrait, tmp_path / "zoom", {"enabled": False, "remotion_effects": {
        "transition_in": "fade", "transition_out": "fade", "transition_ms": 300,
        "zooms": [{"start_ms": 500, "end_ms": 1500, "scale": 1.5, "x": .5, "y": .5}],
    }}, [])
    def red_area(time):
        image = frame(result["mp4"], time)
        return np.count_nonzero((image[:, :, 0] > 180) & (image[:, :, 1] < 40) & (image[:, :, 2] < 40))
    assert red_area(0) == 0
    assert red_area(1) > red_area(.4) * 1.9
    assert abs(red_area(1.6) - red_area(.4)) < red_area(.4) * .1
    assert frame(result["mp4"], 1.966).sum() < frame(result["mp4"], 1.6).sum() * .4
    assert_audio(result)
