"""Real libass frame checks for fade, pop and rise effects; no external assets."""
import os
import shutil
import subprocess

import numpy as np
import pytest

from app.media.render import render_clip

FFMPEG = os.environ.get('FFMPEG_PATH', 'ffmpeg')
FFPROBE = os.environ.get('FFPROBE_PATH', 'ffprobe')
pytestmark = pytest.mark.skipif(not shutil.which(FFMPEG) or not shutil.which(FFPROBE), reason='FFmpeg required')


def frame(path, time):
    raw = subprocess.check_output([FFMPEG, '-v', 'error', '-ss', str(time), '-i', str(path), '-frames:v', '1', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'])
    return np.frombuffer(raw, dtype=np.uint8).reshape(1280, 720)


@pytest.mark.parametrize('effect', ['fade', 'pop', 'rise'])
def test_actual_mp4_contains_subtitle_motion(tmp_path, effect):
    source = tmp_path / 'black.mp4'
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=black:s=360x640:r=30', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(source)], check=True)
    result = render_clip(source, tmp_path / 'render', {
        'start_ms': 0, 'end_ms': 2000, 'crop_json': {'mode': 'fit'},
        'subtitle_style_json': {'font_size': 80, 'background': False, 'text_color': '#FFFFFF', 'animation': effect, 'animation_ms': 300},
        'cues': [{'start_ms': 0, 'end_ms': 2000, 'text': 'MOMEN SERU'}],
    }, {'width': 720}, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE)
    first, entering, settled, ending = (frame(result['mp4'], t) for t in (0, .1, .6, 1.966))
    assert first.max() < 20  # Fade begins transparent.
    assert settled.sum() > 10000
    assert ending.sum() < settled.sum() * .6
    if effect == 'fade':
        assert entering.sum() < settled.sum() * .7
    elif effect == 'pop':
        early = np.where(entering > 30)
        final = np.where(settled > 30)
        assert np.ptp(early[1]) < np.ptp(final[1])  # Glyphs grow to full width.
    else:
        assert np.where(entering > 30)[0].mean() > np.where(settled > 30)[0].mean() + 5
    assert 'MOMEN SERU' in result['srt'].read_text()
