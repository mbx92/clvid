import json
import shutil
import subprocess

import pytest

from app.ai.game_vision import extract_frames
from app.media.process import Cancelled, MediaError


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_actual_ffmpeg_samples_timestamped_jpegs_and_preserves_portrait_bounds(tmp_path):
    source = tmp_path / 'portrait.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'testsrc2=size=1080x1920:rate=10', '-t', '11', '-an',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '2', str(source)], check=True)
    sampled, interval = extract_frames(source, tmp_path / 'frames', duration_ms=11000)
    assert interval == 5000
    assert [f.id for f in sampled] == ['f0000', 'f0001', 'f0002']
    assert [f.timestamp_ms for f in sampled] == [0, 5000, 10000]
    for frame in sampled:
        assert frame.path.read_bytes().startswith(b'\xff\xd8\xff')
    data = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(sampled[0].path)],
                          capture_output=True, text=True, check=True)
    stream = json.loads(data.stdout)['streams'][0]
    assert (stream['width'], stream['height']) == (540, 960)


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_invalid_video_error_is_sanitized_and_cancellation_precedes_decode(tmp_path):
    source = tmp_path / 'private-source-name.mp4'
    source.write_bytes(b'not a movie')
    with pytest.raises(MediaError) as exc:
        extract_frames(source, tmp_path / 'frames', duration_ms=1000)
    assert exc.value.code == 'game_vision_decode_failed'
    assert source.name not in str(exc.value)
    with pytest.raises(Cancelled):
        extract_frames(source, tmp_path / 'cancelled', duration_ms=1000, cancelled=lambda: True)


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_actual_long_video_sampling_covers_full_timeline_with_bounded_frames(tmp_path):
    source = tmp_path / 'long.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'color=blue:size=64x36:rate=10', '-t', '1801', '-an',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '2', str(source)], check=True)
    sampled, interval = extract_frames(source, tmp_path / 'frames', duration_ms=1801000)
    assert interval > 5000
    assert 1 < len(sampled) <= 360
    assert sampled[0].timestamp_ms == 0
    assert sampled[-1].timestamp_ms > 1801000 - interval * 2
    assert all(b.timestamp_ms - a.timestamp_ms >= interval for a, b in zip(sampled, sampled[1:]))


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_anamorphic_source_is_normalized_to_square_pixels(tmp_path):
    source = tmp_path / 'anamorphic.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'color=blue:size=320x240:rate=1', '-vf', 'setsar=2', '-t', '1',
                    '-c:v', 'libx264', str(source)], check=True)
    sampled, _ = extract_frames(source, tmp_path / 'frames', duration_ms=1000)
    data = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(sampled[0].path)],
                          capture_output=True, text=True, check=True)
    stream = json.loads(data.stdout)['streams'][0]
    assert (stream['width'], stream['height']) == (640, 240)
    assert stream['sample_aspect_ratio'] == '1:1'
