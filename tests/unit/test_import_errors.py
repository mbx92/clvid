import errno
import json
from types import SimpleNamespace

import pytest

from app.media.import_errors import public_import_error
from app.media.import_url import download_video
from app.media.process import Cancelled, MediaError


@pytest.mark.parametrize("diagnostic,phase,expected", [
    ("ffmpeg is not installed. Aborting", "download", "import_tool_missing"),
    ("ffmpeg-location /private/server does not exist", "download", "import_tool_missing"),
    ("External networking blocked", "merge", "import_merge_failed"),
    ("Unsupported codec in local source", "convert", "import_conversion_failed"),
    ("Sign in to confirm you're not a bot", "download", "source_verification_required"),
    ("Private video. Sign in", "download", "source_login_required"),
    ("Video is age-restricted", "download", "source_login_required"),
    ("HTTP Error 403: Forbidden", "download", "source_access_denied"),
    ("HTTP Error 429: Too Many Requests", "download", "source_rate_limited"),
    ("HTTP Error 404: Not Found", "download", "source_unavailable"),
    ("Video unavailable", "download", "source_unavailable"),
    ("Requested format is not available", "download", "source_format_unavailable"),
    ("Unsupported URL: https://example.com/?token=secret", "download", "source_url_unsupported"),
    ("Connection reset by peer", "download", "source_network_error"),
    ("Temporary failure in name resolution", "download", "source_network_error"),
    ("Unrecognized engine error", "download", "url_download_failed"),
])
def test_known_causes_have_actionable_messages_without_provider_diagnostics(diagnostic, phase, expected):
    error = public_import_error(RuntimeError(diagnostic+" https://example.com/?token=private-token /private/server/path"), phase=phase)
    assert error.code == expected
    assert not any(value in error.message for value in ("private-token", "https://", "/private/server", "Pengaturan", "batas ukuran"))
    assert len(error.message.split(". ")) >= 2


def test_query_string_does_not_classify_unknown_error_as_limit_or_access_failure():
    error = public_import_error(RuntimeError("Unexpected response https://example.com/?reason=private video"))
    assert error.code == "url_download_failed"


def test_os_failures_and_app_owned_limit_messages():
    assert public_import_error(OSError(errno.ENOSPC, "private path")).code == "insufficient_disk"
    assert public_import_error(PermissionError("private target")).code == "source_address_blocked"
    assert public_import_error(TimeoutError("private target")).code == "source_network_error"
    limit = MediaError("duration_limit", "Durasi video 120 menit melebihi batas 60 menit.")
    assert public_import_error(limit, phase="merge") is limit


@pytest.mark.parametrize("outcome,expected", [
    ("crash", "import_worker_failed"), ("malformed", "import_worker_failed"),
    ("missing", "import_worker_failed"), ("timeout", "import_timeout"), ("cancel", "cancelled"),
])
def test_parent_handles_failed_child_without_losing_cancel_or_leaking_details(tmp_path, monkeypatch, outcome, expected):
    def child(*args, **kwargs):
        if outcome == "timeout":
            raise MediaError("process_timeout", "private process arguments")
        if outcome == "cancel":
            raise Cancelled()
        if outcome == "malformed":
            (tmp_path/"download-output.json").write_text('["private internal data"]')
        return SimpleNamespace(returncode=1 if outcome == "crash" else 0)
    monkeypatch.setattr("app.media.import_url.run_process", child)
    settings = SimpleNamespace(max_upload_bytes=1000, max_video_seconds=60, max_video_width=1920,
                               max_video_height=1080, min_free_disk_bytes=0, ffmpeg_path="ffmpeg", media_timeout_seconds=10)
    with pytest.raises(MediaError) as caught:
        download_video("https://example.com/video?token=secret", tmp_path, settings=settings)
    assert caught.value.code == expected
    assert "private" not in caught.value.message and "secret" not in caught.value.message
    assert not (tmp_path/"download-input.json").exists()
