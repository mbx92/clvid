"""Actual full-decode preview validation and failed-output publication guards."""
import os
import shutil
import subprocess

import pytest

from app.media.probe import probe
from app.media.process import MediaError
from app.media.render import prepare_preview

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")
pytestmark = pytest.mark.skipif(not shutil.which(FFMPEG) or not shutil.which(FFPROBE), reason="Real FFmpeg required")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "non-browser.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "5.2", "-c:v", "mpeg4", "-q:v", "4",
                    "-c:a", "aac", "-movflags", "+faststart", str(path)], check=True)
    return path


def test_preview_validates_full_decode_and_publishes_browser_compatible_output(source, tmp_path):
    meta = probe(source, binary=FFPROBE)
    result = prepare_preview(source, tmp_path / "output", duration_ms=meta["duration_ms"],
                             ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE, validate_decode=True, max_width=480, threads=2)
    assert result["path"].name == "preview.mp4" and result["path"].exists()
    assert result["meta"]["video_codec"] == "h264" and result["meta"]["audio_codec"] == "aac"
    assert result["meta"]["width"] == 480 and result["meta"]["sample_aspect_ratio"] == 1
    assert result["meta"]["rotation"] == 0 and result["meta"]["fps"] == 30
    assert abs(result["meta"]["duration_ms"] - meta["duration_ms"]) <= 150


def test_readable_header_with_corrupted_late_packets_is_rejected_and_cleaned(source, tmp_path):
    contents = bytearray(source.read_bytes())
    start = len(contents) // 2
    contents[start:start + len(contents) // 8] = b"\x00" * (len(contents) // 8)
    source.write_bytes(contents)
    meta = probe(source, binary=FFPROBE)  # Metadata alone still passes.
    output = tmp_path / "corrupt-output"
    with pytest.raises(MediaError):
        prepare_preview(source, output, duration_ms=meta["duration_ms"], ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE,
                        validate_decode=True, max_width=480, threads=2)
    assert not (output / "preview.mp4").exists()
    assert not (output / "preview.partial.mp4").exists()


def test_preview_duration_mismatch_never_publishes(source, tmp_path, monkeypatch):
    real_probe = probe
    def wrong_duration(path, **kwargs):
        metadata = real_probe(path, **kwargs)
        metadata["duration_ms"] += 1000
        return metadata
    monkeypatch.setattr("app.media.render.probe", wrong_duration)
    output = tmp_path / "mismatch-output"
    with pytest.raises(MediaError) as failure:
        prepare_preview(source, output, duration_ms=5200, ffmpeg_bin=FFMPEG, ffprobe_bin=FFPROBE,
                        validate_decode=True, max_width=480, threads=2)
    assert failure.value.code == "invalid_preview"
    assert not (output / "preview.mp4").exists()
    assert not (output / "preview.partial.mp4").exists()
