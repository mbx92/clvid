import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.media.process import MediaError
from app.research import routes, search
from app.research.schemas import SearchInput


def entry(identifier="AbcDefGh123", **fields):
    return {"id": identifier, "title": "Percakapan kopi", "channel": "Kanal contoh", "duration": 180,
            "view_count": 1234, "description": "Tentang cara menyeduh kopi.", **fields}


def result(identifier="AbcDefGh123"):
    return search.normalize_entries([entry(identifier)], count=1, max_seconds=3600)[0]


def test_normalize_filters_live_playlists_invalid_ids_duplicates_and_limits():
    items = search.normalize_entries([
        entry("LiveVideo12", is_live=True),
        entry("SoonVideo12", live_status="is_upcoming"),
        entry("PostVideo12", live_status="post_live"),
        entry("PlayList123", _type="playlist"),
        entry("not-a-video-id"),
        entry("TooLong1234", duration=3601),
        entry(), entry(), entry("OtherVid123", duration=3600), entry("ThirdVid123"),
    ], count=2, max_seconds=3600)
    assert [item["id"] for item in items] == ["AbcDefGh123", "OtherVid123"]
    assert items[1]["duration_ms"] == 3600000


def test_normalize_rebuilds_links_and_bounds_untrusted_metadata():
    items = search.normalize_entries([entry(url="http://127.0.0.1/secret", webpage_url="javascript:alert(1)",
                                           thumbnail="http://internal/secret", title="\x1b\u202e" + "A" * 300,
                                           channel="x" * 180, description="y" * 800,
                                           duration=float("nan"), view_count=True)], count=6, max_seconds=3600)
    item = items[0]
    assert item["url"] == "https://www.youtube.com/watch?v=AbcDefGh123"
    assert item["thumbnail_url"] == "https://i.ytimg.com/vi/AbcDefGh123/hqdefault.jpg"
    assert len(item["title"]) == 200 and "\x1b" not in item["title"] and "\u202e" not in item["title"]
    assert len(item["channel"]) == 120 and len(item["description"]) == 600
    assert item["duration_ms"] is None and item["view_count"] is None


@pytest.mark.parametrize("body", [{"query": "a"}, {"query": "x" * 201}, {"query": "ab\ncd"},
                                  {"query": "kopi", "count": 11}, {"query": "kopi", "count": True},
                                  {"query": "kopi", "count": "3"}, {"query": "kopi", "url": "file:///etc/passwd"}])
def test_search_input_rejects_bad_limits(body):
    with pytest.raises(ValidationError):
        SearchInput(**body)


def fake_worker(monkeypatch, payload):
    seen = {}
    def run(args, **kwargs):
        request_file = Path(args[-1])
        seen.update(args=args, kwargs=kwargs, directory=request_file.parent)
        config = json.loads(request_file.read_text(encoding="utf-8"))
        seen["config"] = config
        Path(config["output"]).write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(search, "run_process", run)
    return seen


def test_worker_boundary_strips_credentials_bounds_time_and_cleans_files(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-test-key")
    monkeypatch.setenv("HTTP_PROXY", "http://private-proxy")
    seen = fake_worker(monkeypatch, {"items": [result()]})
    assert search.search_videos(" kopi ", count=1, max_seconds=600) == [result()]
    assert seen["config"]["query"] == "kopi"
    assert seen["config"]["max_seconds"] == 600
    assert seen["kwargs"]["timeout"] == 35
    assert "DEEPSEEK_API_KEY" not in seen["kwargs"]["env"]
    assert "HTTP_PROXY" not in seen["kwargs"]["env"]
    assert not seen["directory"].exists()


@pytest.mark.parametrize("payload", [
    {"error": "private provider details"},
    {"items": [{**result(), "url": "http://127.0.0.1/secret"}]},
    {"items": [result(), result()]},
    {"items": "malformed"},
])
def test_worker_boundary_rejects_malformed_output_without_exposing_details(monkeypatch, payload):
    seen = fake_worker(monkeypatch, payload)
    with pytest.raises(MediaError) as failure:
        search.search_videos("kopi", count=2)
    assert failure.value.code == "research_unavailable"
    assert "private" not in failure.value.message and "127.0.0.1" not in failure.value.message
    assert not seen["directory"].exists()


def test_worker_timeout_releases_slot_and_cleans_files(monkeypatch):
    seen = {}
    def timeout(args, **kwargs):
        seen["directory"] = Path(args[-1]).parent
        raise MediaError("process_timeout", "Private URL and token")
    monkeypatch.setattr(search, "run_process", timeout)
    for _ in range(3):
        with pytest.raises(MediaError) as failure:
            search.search_videos("kopi")
        assert failure.value.code == "research_timeout"
        assert not seen["directory"].exists()
    seen = fake_worker(monkeypatch, {"items": []})
    assert search.search_videos("kopi") == []


def test_search_concurrency_limit_does_not_launch_worker(monkeypatch):
    monkeypatch.setattr(search, "run_process", lambda *a, **kw: pytest.fail("worker must not start"))
    assert search._slots.acquire(blocking=False)
    assert search._slots.acquire(blocking=False)
    try:
        with pytest.raises(MediaError, match="Pencarian lain") as failure:
            search.search_videos("kopi")
        assert failure.value.code == "research_busy"
    finally:
        search._slots.release()
        search._slots.release()


def test_search_api_auth_csrf_and_validation(clients, monkeypatch):
    from app.main import app
    monkeypatch.setattr(routes, "search_videos", lambda *a, **kw: pytest.fail("provider must not run"))
    with TestClient(app) as anon:
        assert anon.post("/api/v1/research/search", json={"query": "kopi"}).status_code == 401
    client = clients[0]
    assert client.post("/api/v1/research/search", json={"query": "kopi"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/api/v1/research/search", json={"query": "a"}).status_code == 422


def test_search_api_passes_account_limits_and_returns_metadata(clients, database, monkeypatch):
    from sqlalchemy import select
    from app.domain.models import ProcessingSettings, User
    with database() as db:
        user = db.scalar(select(User).where(User.email == "a@example.test"))
        db.add(ProcessingSettings(user_id=user.id, max_video_seconds=600, max_upload_bytes=100000000, max_clip_ms=60000))
        db.commit()
    seen = {}
    def provider(query, **kwargs):
        seen.update(query=query, **kwargs)
        return [result()]
    monkeypatch.setattr(routes, "search_videos", provider)
    response = clients[0].post("/api/v1/research/search", json={"query": "  kopi  ", "count": 3})
    assert response.status_code == 200, response.text
    assert seen == {"query": "kopi", "count": 3, "max_seconds": 600}
    assert response.json() == {"query": "kopi", "items": [result()], "message": None}


def test_search_api_empty_and_provider_failure(clients, monkeypatch):
    monkeypatch.setattr(routes, "search_videos", lambda *a, **kw: [])
    response = clients[0].post("/api/v1/research/search", json={"query": "kopi"})
    assert response.status_code == 200 and response.json()["items"] == [] and response.json()["message"]
    def timeout(*args, **kwargs):
        raise MediaError("research_timeout", "Pencarian melewati batas waktu.")
    monkeypatch.setattr(routes, "search_videos", timeout)
    response = clients[0].post("/api/v1/research/search", json={"query": "kopi"})
    assert response.status_code == 504 and response.json()["code"] == "RESEARCH_TIMEOUT"
