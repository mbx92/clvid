"""Metadata only; no cookies, files, external executables or private networking."""
import itertools
import json
from pathlib import Path
import sys

from app.media.remote_guard import install_network_guard
from .search import normalize_entries
from .schemas import SearchInput


class Quiet:
    def debug(self, *_): pass
    def info(self, *_): pass
    def warning(self, *_): pass
    def error(self, *_): pass


def forbid_external_processes(event, args):
    if event in ("subprocess.Popen", "os.system", "os.posix_spawn", "os.posix_spawnp"):
        raise PermissionError("External processes are not allowed during metadata search")


def main(request_file):
    from yt_dlp import YoutubeDL
    config = json.loads(Path(request_file).read_text(encoding="utf-8"))
    request = SearchInput(query=config["query"], count=config["count"])
    output = Path(config["output"])
    install_network_guard()
    sys.addaudithook(forbid_external_processes)
    try:
        # Flat results avoid visiting or downloading individual source videos.
        # Oversampling is bounded so live/too-long results can be omitted.
        sample_count = request.count * 2
        with YoutubeDL(dict(quiet=True, no_warnings=True, logger=Quiet(), proxy="",
                            enable_file_urls=False, cachedir=False, js_runtimes={},
                            extract_flat=True, skip_download=True, lazy_playlist=True,
                            socket_timeout=10, retries=0, extractor_retries=0,
                            playlistend=sample_count, ignoreerrors=False)) as downloader:
            result = downloader.extract_info(f"ytsearch{sample_count}:{request.query}", download=False)
            if not isinstance(result, dict) or "entries" not in result:
                raise ValueError("Missing search entries")
            entries = itertools.islice(result["entries"], sample_count)
            items = normalize_entries(entries, count=request.count, max_seconds=config["max_seconds"])
        output.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # Never return provider diagnostics, signed URLs, cookies or raw response bodies.
        output.write_text(json.dumps({"error": "unavailable"}), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
