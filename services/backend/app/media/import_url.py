import json
import os
from pathlib import Path
import sys
from .process import MediaError, run_process
from .remote_guard import validate_url
from .import_errors import import_error


def download_video(url, directory, *, settings, cancelled=None, progress=None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    request, output = directory/"download-input.json", directory/"download-output.json"
    config = dict(url=validate_url(url), directory=str(directory), output=str(output),
                  max_bytes=settings.max_upload_bytes, max_seconds=settings.max_video_seconds,
                  max_width=settings.max_video_width, max_height=settings.max_video_height,
                  target_height=getattr(settings, "import_max_height", 1080), ffmpeg=settings.ffmpeg_path,
                  min_free=settings.min_free_disk_bytes)
    environment = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "SSL_CERT_FILE", "SSL_CERT_DIR")}
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    try:
        request.write_text(json.dumps(config), encoding="utf-8")
        try:
            result = run_process([sys.executable, "-m", "app.media.import_child", str(request)], env=environment,
                                 timeout=settings.media_timeout_seconds, cancelled=cancelled, progress=progress,
                                 duration_ms=1000)
        except MediaError as exc:
            if exc.code == "process_timeout":
                raise import_error("import_timeout") from None
            raise
        if result.returncode or not output.exists():
            raise import_error("import_worker_failed")
        try:
            data = json.loads(output.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError()
            if "error" in data:
                if not isinstance(data["error"], dict) or not all(isinstance(data["error"].get(k), str) for k in ("code", "message")):
                    raise ValueError()
            elif not isinstance(data.get("path"), str):
                raise ValueError()
        except (OSError, ValueError):
            raise import_error("import_worker_failed") from None
        if "error" in data:
            raise MediaError(data["error"]["code"], data["error"]["message"])
        path = Path(data["path"]).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise import_error("import_incomplete")
        return {**data, "path": path}
    finally:
        request.unlink(missing_ok=True)
