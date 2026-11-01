import asyncio

import httpx
from sqlalchemy import func, select

from app.config import get_settings
from app.domain.models import Asset, Job, OutboxEvent, Project, User


def test_missing_csrf_cookie_can_recover_without_losing_session(clients):
    client = clients[0]
    session_before = client.cookies.get("clipper_session")
    client.cookies.delete("clipper_csrf")
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    client.headers["X-CSRF-Token"] = token
    assert client.post("/api/v1/projects", json={"name": "Sesi pulih"}).status_code == 201
    assert client.cookies.get("clipper_session") == session_before
    assert client.get("/api/v1/auth/csrf", headers={"Origin": "https://untrusted.test"}).status_code == 403


def test_password_whitespace_is_preserved(clients, database):
    from app.api.auth import hasher
    client = clients[0]
    with database() as db:
        user = db.scalar(select(User).where(User.email == "a@example.test"))
        user.password_hash = hasher.hash("  space is intentional  ")
        db.commit()
    assert client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": "space is intentional"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": "  space is intentional  "}).status_code == 200


def test_deduplicated_alias_is_remembered_and_queue_full_repeat_succeeds(clients, ready_project, monkeypatch):
    client = clients[0]
    pid = ready_project["project_id"]
    clip = client.post(f"/api/v1/projects/{pid}/clips", json={"title": "Alias", "start_ms": 0, "end_ms": 6000}).json()
    endpoint = f"/api/v1/clips/{clip['id']}/exports"
    body = {"revision": 1, "resolution": 720}
    first = client.post(endpoint, json=body, headers={"Idempotency-Key": "original"})
    alias = client.post(endpoint, json=body, headers={"Idempotency-Key": "alias"})
    assert first.status_code == alias.status_code == 202
    assert first.json()["id"] == alias.json()["id"]
    assert client.post(endpoint, json={"revision": 1, "resolution": 1080}, headers={"Idempotency-Key": "alias"}).status_code == 409
    monkeypatch.setattr(get_settings(), "max_active_jobs_per_user", 1)
    assert client.post(endpoint, json=body, headers={"Idempotency-Key": "new-alias"}).status_code == 202
    assert client.post(endpoint, json={"revision": 1, "resolution": 1080}, headers={"Idempotency-Key": "new-output"}).status_code == 429


def test_retry_request_key_does_not_repeat_after_another_failure(clients, ready_project, database):
    client = clients[0]
    pid = ready_project["project_id"]
    clip = client.post(f"/api/v1/projects/{pid}/clips", json={"title": "Retry", "start_ms": 0, "end_ms": 6000}).json()
    job_id = client.post(f"/api/v1/clips/{clip['id']}/exports", json={"revision": 1, "resolution": 720}).json()["id"]
    with database() as db:
        db.get(Job, job_id).status = "failed"
        db.commit()
    endpoint = f"/api/v1/jobs/{job_id}/retry"
    assert client.post(endpoint, headers={"Idempotency-Key": "retry-once"}).status_code == 202
    with database() as db:
        db.get(Job, job_id).status = "failed"
        db.commit()
    replay = client.post(endpoint, headers={"Idempotency-Key": "retry-once"})
    assert replay.status_code == 202 and replay.json()["status"] == "failed"
    with database() as db:
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.job_id == job_id)) == 2
    assert client.post(endpoint, headers={"Idempotency-Key": "retry-again"}).json()["status"] == "queued"


def test_upload_stops_after_project_tombstone(clients, database):
    from app.main import app
    client = clients[0]
    pid = client.post("/api/v1/projects", json={"name": "Transfer dibatalkan"}).json()["id"]

    async def transfer():
        async def chunks():
            yield b"first bytes"
            await asyncio.sleep(1.05)
            with database() as db:
                db.get(Project, pid).lifecycle_state = "deleting"
                db.commit()
            yield b"remaining bytes"

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", cookies=dict(client.cookies), headers={"X-CSRF-Token": client.headers["X-CSRF-Token"]}) as stream_client:
            return await stream_client.post(f"/api/v1/projects/{pid}/source", content=chunks())

    result = asyncio.run(transfer())
    assert result.status_code == 409 and result.json()["code"] == "UPLOAD_CANCELLED"
    with database() as db:
        assert db.get(Project, pid).lifecycle_state == "deleting"
        assert db.scalar(select(Asset).where(Asset.project_id == pid)).state == "failed"
    assert not list(get_settings().media_root.glob("uploads/*.part"))


def test_long_caption_draft_is_preserved_but_burn_in_requires_readable_layout(clients, ready_project):
    client = clients[0]
    pid = ready_project["project_id"]
    text = "Koreksi panjang yang tetap harus dapat diedit. " * 25
    created = client.post(f"/api/v1/projects/{pid}/clips", json={"title": "Draft panjang", "start_ms": 0, "end_ms": 6000, "cues": [{"start_ms": 0, "end_ms": 6000, "text": text}]})
    assert created.status_code == 201
    clip = created.json()
    endpoint = f"/api/v1/clips/{clip['id']}"
    refused = client.post(endpoint + "/exports", json={"revision": 1, "resolution": 720})
    assert refused.status_code == 422 and refused.json()["code"] == "SUBTITLE_TOO_LONG"
    assert client.get(endpoint).json()["revision"]["cues"][0]["text"] == text.strip()
    update = client.patch(endpoint, json={"expected_revision": 1, "subtitle_style_json": {"enabled": False}})
    assert update.status_code == 200
    assert client.post(endpoint + "/exports", json={"revision": 2, "resolution": 720}).status_code == 202
