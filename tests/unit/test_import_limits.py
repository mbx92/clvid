import json

import pytest

from app.media.import_child import enforce_import_limits, main
from app.media.process import MediaError


def config(**updates):
    return {"max_seconds": 3600, "max_bytes": 2*1024**3, **updates}


def test_duration_failure_uses_retry_contract_and_accepts_increased_limit():
    info = {"duration": 7200}
    with pytest.raises(MediaError) as error:
        enforce_import_limits(info, config())
    assert error.value.code == "duration_limit"
    assert "120.0" in error.value.message and "60" in error.value.message
    enforce_import_limits(info, config(max_seconds=10800))


def test_size_limit_accounts_for_combined_video_and_audio_without_trusting_estimates():
    info = {"requested_formats": [{"filesize": 2*1024**3}, {"filesize": 1024**2}]}
    with pytest.raises(MediaError) as error:
        enforce_import_limits(info, config())
    assert error.value.code == "file_too_large"
    enforce_import_limits(info, config(max_bytes=4*1024**3))
    enforce_import_limits({"filesize_approx": 20*1024**3}, config())


@pytest.mark.parametrize("failure", ["duration", "size", "wrapped_size", "provider", "merge", "missing_tool"])
def test_download_child_preserves_limits_but_does_not_expose_provider_secrets(tmp_path, monkeypatch, failure):
    from app.media import import_child
    monkeypatch.setattr(import_child, "install_network_guard", lambda: None)
    monkeypatch.setattr(import_child, "install_process_guard", lambda _: None)
    monkeypatch.setattr(import_child.shutil, "which", lambda _: None if failure == "missing_tool" else "/resolved/bin/ffmpeg")
    class Downloader:
        def __init__(self, options):
            assert options["ffmpeg_location"] == "/resolved/bin/ffmpeg"
            assert options["postprocessor_args"]["merger+ffmpeg_i"] == ["-protocol_whitelist", "file,pipe"]
            self.options = options
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download=False):
            if failure == "provider":
                raise RuntimeError("private provider URL?token=secret")
            return {"duration": 7200} if failure == "duration" else {"filesize": 3*1024**3} if failure == "size" else {}
        def process_info(self, info):
            if failure == "merge":
                self.options["postprocessor_hooks"][0]({"status": "started", "postprocessor": "Merger"})
                raise PermissionError("Private server path /secret and provider token")
            try:
                self.options["progress_hooks"][0]({"downloaded_bytes": 3*1024**3})
            except MediaError:
                raise RuntimeError("wrapped downloader URL?token=secret")
    monkeypatch.setattr("yt_dlp.YoutubeDL", Downloader)
    request, output = tmp_path/"request.json", tmp_path/"result.json"
    request.write_text(json.dumps({**config(), "directory": str(tmp_path), "output": str(output), "min_free": 0,
                                  "url": "https://example.com/video?token=secret", "ffmpeg": "ffmpeg"}))
    main(request)
    result = json.loads(output.read_text())["error"]
    assert result["code"] == {"duration":"duration_limit", "provider":"url_download_failed",
                              "merge":"import_merge_failed", "missing_tool":"import_tool_missing"}.get(failure, "file_too_large")
    assert "secret" not in output.read_text()


def test_probe_duration_limit_is_retryable_after_settings_increase(tmp_path, monkeypatch):
    from app.media import probe
    source = tmp_path/"source.mp4"
    source.write_bytes(b"\x00\x00\x00\x18ftypisom fixture")
    metadata = dict(format="mov,mp4", audio_stream=1, duration_ms=7200000,
                    display_width=640, display_height=360)
    monkeypatch.setattr(probe, "probe", lambda *args, **kwargs: metadata.copy())
    with pytest.raises(MediaError) as error:
        probe.validate_source(source, max_seconds=3600, validate_decode=False)
    assert error.value.code == "duration_limit"
    assert probe.validate_source(source, max_seconds=10800, validate_decode=False)["duration_ms"] == 7200000
