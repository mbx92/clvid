"""Bounded metadata discovery, isolated from the API's credentials and network."""
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import unicodedata

from pydantic import ValidationError

from app.media.process import MediaError, run_process
from .schemas import SearchInput, VideoResult

SEARCH_TIMEOUT_SECONDS = 35
MAX_OUTPUT_BYTES = 64_000
_slots = threading.BoundedSemaphore(2)


def _text(value, limit):
    if not isinstance(value, str):
        return ""
    # The UI renders these as text, never HTML; remove terminal/bidi controls too.
    return " ".join("".join(c for c in value[:limit * 4] if not unicodedata.category(c).startswith("C")).split())[:limit]


def normalize_entries(entries, *, count, max_seconds):
    """Only stable public YouTube video IDs become links in the UI."""
    items, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", identifier) or identifier in seen:
            continue
        if entry.get("_type") in ("playlist", "multi_video") or entry.get("is_live") or entry.get("live_status") in ("is_live", "is_upcoming", "post_live"):
            continue
        duration = entry.get("duration")
        duration = duration if type(duration) in (int, float) and math.isfinite(duration) and duration > 0 else None
        if duration is not None and (duration > max_seconds or duration > 86400):
            continue
        views = entry.get("view_count")
        views = int(views) if type(views) in (int, float) and math.isfinite(views) and 0 <= views <= 10**15 else None
        item = VideoResult(id=identifier,
                           url=f"https://www.youtube.com/watch?v={identifier}",
                           thumbnail_url=f"https://i.ytimg.com/vi/{identifier}/hqdefault.jpg",
                           title=_text(entry.get("title"), 200) or "Video YouTube",
                           channel=_text(entry.get("channel") or entry.get("uploader"), 120),
                           description=_text(entry.get("description"), 600),
                           duration_ms=max(1, round(duration * 1000)) if duration is not None else None,
                           view_count=views)
        items.append(item.model_dump())
        seen.add(identifier)
        if len(items) >= count:
            break
    return items


def search_videos(query, *, count=6, max_seconds=3600):
    request = SearchInput(query=query, count=count)
    if not _slots.acquire(blocking=False):
        raise MediaError("research_busy", "Pencarian lain masih berjalan. Tunggu sebentar lalu coba lagi.")
    try:
        with tempfile.TemporaryDirectory(prefix="clipper-research-") as scratch:
            directory = Path(scratch)
            input_file, output_file = directory / "request.json", directory / "result.json"
            input_file.write_text(json.dumps({"query": request.query, "count": request.count,
                                             "max_seconds": max_seconds, "output": str(output_file)}), encoding="utf-8")
            environment = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "SSL_CERT_FILE", "SSL_CERT_DIR")}
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
            try:
                result = run_process([sys.executable, "-m", "app.research.search_child", str(input_file)],
                                     timeout=SEARCH_TIMEOUT_SECONDS, env=environment, cwd=directory)
            except MediaError as exc:
                if exc.code == "process_timeout":
                    raise MediaError("research_timeout", "Pencarian YouTube melewati batas waktu. Coba topik yang lebih singkat atau ulangi nanti.") from None
                raise MediaError("research_unavailable", "Pencarian YouTube belum berhasil. Coba lagi nanti atau impor URL video secara langsung.") from None
            if result.returncode or not output_file.is_file() or output_file.stat().st_size > MAX_OUTPUT_BYTES:
                raise ValueError("Invalid search worker output")
            payload = json.loads(output_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("error") or not isinstance(payload.get("items"), list) or len(payload["items"]) > count:
                raise ValueError("Invalid search worker result")
            items = [VideoResult.model_validate(item).model_dump() for item in payload["items"]]
            # Check the child boundary too; a malformed worker cannot add unlimited/foreign results.
            if len({item["id"] for item in items}) != len(items) or any(item["duration_ms"] and item["duration_ms"] > max_seconds * 1000 for item in items):
                raise ValueError("Invalid search result limits")
            return items
    except (OSError, ValueError, ValidationError):
        raise MediaError("research_unavailable", "Pencarian YouTube belum berhasil atau aksesnya dibatasi. Coba lagi nanti atau impor URL video secara langsung.") from None
    finally:
        _slots.release()
