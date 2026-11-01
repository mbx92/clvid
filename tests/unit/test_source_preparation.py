from pathlib import Path
from types import SimpleNamespace

import pytest

from app.media import probe as probe_module
from app.media import render as render_module
from app.media.process import MediaError
from app.media.source_preparation import prepare_source


@pytest.fixture
def preparation(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"\x00\x00\x00\x18ftypisom synthetic metadata fixture")
    metadata = {"format": "mov,mp4", "major_brand": "isom", "audio_stream": 1,
                "duration_ms": 10000, "width": 1920, "height": 1080,
                "display_width": 1920, "display_height": 1080, "sample_aspect_ratio": 1,
                "video_codec": "h264", "pixel_format": "yuv420p", "audio_codec": "aac"}
    commands = []
    def decode(args, **kwargs):
        commands.append(("validation", args, kwargs))
    def preview(args, **kwargs):
        commands.append(("preview", args, kwargs))
        Path(args[-1]).write_bytes(b"proxy")
    monkeypatch.setattr(probe_module, "probe", lambda *a, **kw: metadata.copy())
    monkeypatch.setattr(probe_module, "ffmpeg", decode)
    monkeypatch.setattr(render_module, "ffmpeg", preview)
    monkeypatch.setattr(render_module, "probe", lambda *a, **kw: {**metadata, "video_codec": "h264", "width": 1280, "height": 720, "rotation": 0, "fps": 30})
    monkeypatch.setattr(render_module, "check_disk", lambda *a, **kw: None)
    settings = SimpleNamespace(max_upload_bytes=100000, max_video_seconds=60, max_video_width=3840,
                               max_video_height=2160, ffprobe_path="ffprobe", ffmpeg_path="ffmpeg",
                               media_timeout_seconds=120, preview_max_width=1280, preview_threads=4)
    return source, tmp_path, metadata, commands, settings


def test_compatible_source_is_fully_decoded_once_and_never_transcoded(preparation):
    source, scratch, metadata, commands, settings = preparation
    before = source.read_bytes()
    stages = []
    result, preview = prepare_source(source, scratch, settings=settings, stage=stages.append)
    assert result["browser_compatible"] and preview is None and not stages
    assert [kind for kind, *_ in commands] == ["validation"]
    assert "-xerror" in commands[0][1] and commands[0][1][-2:] == ["null", "-"]
    assert source.read_bytes() == before


def test_incompatible_source_decodes_once_while_creating_strict_capped_preview(preparation):
    source, scratch, metadata, commands, settings = preparation
    metadata["video_codec"] = "av1"
    before = source.read_bytes()
    stages = []
    result, preview = prepare_source(source, scratch, settings=settings, stage=stages.append)
    assert not result["browser_compatible"] and preview["path"].is_file()
    assert stages == ["prepare_preview"]
    assert [kind for kind, *_ in commands] == ["preview"]
    args = commands[0][1]
    assert args[:3] == ["-xerror", "-err_detect", "explode"]
    assert "min(1280,iw)" in args[args.index("-vf") + 1]
    assert args[args.index("-threads") + 1] == "4"
    assert source.read_bytes() == before


def test_failed_full_decode_is_not_promoted_to_ready_metadata(preparation, monkeypatch):
    source, scratch, metadata, commands, settings = preparation
    metadata["video_codec"] = "av1"
    def corrupt(*args, **kwargs):
        raise MediaError("media_decode_failed", "Corrupt fixture")
    monkeypatch.setattr(render_module, "ffmpeg", corrupt)
    with pytest.raises(MediaError, match="Corrupt fixture"):
        prepare_source(source, scratch, settings=settings, stage=lambda _: None)
    assert not (scratch / "preview.mp4").exists()


def test_metadata_rejection_happens_before_any_expensive_decode(preparation):
    source, scratch, metadata, commands, settings = preparation
    metadata["audio_stream"] = None
    with pytest.raises(MediaError) as error:
        prepare_source(source, scratch, settings=settings, stage=lambda _: None)
    assert error.value.code == "no_audio" and not commands
