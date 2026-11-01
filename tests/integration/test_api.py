from datetime import timedelta

from sqlalchemy import func, select

from app.domain.models import Asset, ClipRevision, Export, Job, OutboxEvent, Session, SubtitleCue, utcnow


def make_clip(client, project_id):
    response = client.post(f"/api/v1/projects/{project_id}/clips", json={
        "title": "Klip pertama", "start_ms": 1000, "end_ms": 9000,
        "cues": [{"start_ms": 500, "end_ms": 3500, "text": "Teks koreksi pengguna."}],
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_sessions_csrf_logout_and_expiry(clients, database):
    client, _ = clients
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/projects", json={"name": "X"}, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    assert client.post("/api/v1/projects", json={"name": "X"}, headers={"Origin": "https://untrusted.test"}).status_code == 403
    token = client.cookies.get("clipper_session")
    from app.api.auth import digest
    with database() as db:
        row = db.get(Session, digest(token))
        assert row.id != token
        assert row.csrf_hash != client.headers["X-CSRF-Token"]
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.set("clipper_session", token)
    assert client.get("/api/v1/projects").status_code == 401
    with database() as db:
        for row in db.scalars(select(Session)):
            row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert clients[1].get("/api/v1/auth/me").status_code == 401


def test_login_rate_limit_and_safe_errors(clients):
    client, _ = clients
    for _ in range(8):
        result = client.post("/api/v1/auth/login", json={"email": "missing@example.test", "password": "private-secret"})
        assert result.status_code == 401
        assert "private-secret" not in result.text
    result = client.post("/api/v1/auth/login", json={"email": "missing@example.test", "password": "private-secret"})
    assert result.status_code == 429
    assert set(result.json()) == {"code", "message", "correlation_id"}


def test_ownership_for_project_clip_job_transcript_asset_and_exports(clients, ready_project):
    owner, other = clients
    pid, aid = ready_project["project_id"], ready_project["asset_id"]
    clip = make_clip(owner, pid)
    result = owner.post(f"/api/v1/clips/{clip['id']}/exports", json={"revision": 1, "resolution": 720}, headers={"Idempotency-Key": "export-owner"})
    assert result.status_code == 202, result.text
    jid = result.json()["id"]
    for url in (f"projects/{pid}", f"projects/{pid}/clips", f"projects/{pid}/exports", f"projects/{pid}/transcripts/latest", f"clips/{clip['id']}", f"jobs/{jid}", f"assets/{aid}/content"):
        assert other.get(f"/api/v1/{url}").status_code == 404, url
    assert other.patch(f"/api/v1/projects/{pid}", json={"name": "Hijack"}).status_code == 404
    assert other.patch(f"/api/v1/clips/{clip['id']}", json={"expected_revision": 1, "title": "Hijack"}).status_code == 404
    assert other.post(f"/api/v1/jobs/{jid}/cancel").status_code == 404
    assert other.delete(f"/api/v1/projects/{pid}").status_code == 404
    assert other.get("/api/v1/projects").json()["total"] == 0
    assert other.get("/api/v1/usage").json()["storage_bytes"] == 0


def test_private_range_and_head(clients, ready_project):
    client = clients[0]
    url = f"/api/v1/assets/{ready_project['asset_id']}/content"
    response = client.get(url, headers={"Range": "bytes=3-7"})
    assert response.status_code == 206
    assert response.content == b"34567"
    assert response.headers["content-range"] == "bytes 3-7/16"
    assert response.headers["cache-control"] == "private, no-store"
    assert client.head(url).headers["content-length"] == "16"
    assert client.get(url, headers={"Range": "bytes=999-"}).status_code == 416


def test_immutable_revisions_trim_and_export_snapshot(clients, ready_project, database):
    client = clients[0]
    clip = make_clip(client, ready_project["project_id"])
    url = f"/api/v1/clips/{clip['id']}"
    rendered = client.post(url + "/exports", json={"revision": 1, "resolution": 720}, headers={"Idempotency-Key": "snapshot"})
    assert rendered.status_code == 202
    revised = client.patch(url, json={"expected_revision": 1, "start_ms": 2000, "end_ms": 8000, "title": "Disunting"})
    assert revised.status_code == 200, revised.text
    assert revised.json()["revision"]["revision"] == 2
    assert revised.json()["revision"]["cues"] == [{"start_ms": 0, "end_ms": 2500, "text": "Teks koreksi pengguna."}]
    assert client.patch(url, json={"expected_revision": 1, "title": "Tab usang"}).status_code == 409
    with database() as db:
        export = db.scalar(select(Export).where(Export.job_id == rendered.json()["id"]))
        old = db.get(ClipRevision, export.clip_revision_id)
        assert (old.revision, old.title, old.start_ms, old.end_ms) == (1, "Klip pertama", 1000, 9000)
        cue = db.scalar(select(SubtitleCue).where(SubtitleCue.clip_revision_id == old.id))
        assert cue.start_ms == 500


def test_export_idempotency_and_outbox(clients, ready_project, database):
    client = clients[0]
    clip = make_clip(client, ready_project["project_id"])
    url = f"/api/v1/clips/{clip['id']}/exports"
    first = client.post(url, json={"revision": 1, "resolution": 720}, headers={"Idempotency-Key": "same"})
    second = client.post(url, json={"revision": 1, "resolution": 720}, headers={"Idempotency-Key": "same"})
    third = client.post(url, json={"revision": 1, "resolution": 720}, headers={"Idempotency-Key": "different"})
    assert first.status_code == second.status_code == third.status_code == 202
    assert first.json()["id"] == second.json()["id"] == third.json()["id"]
    assert client.post(url, json={"revision": 1, "resolution": 1080}, headers={"Idempotency-Key": "same"}).status_code == 409
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Export)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_upload_size_empty_and_atomic_pending(clients, database, monkeypatch):
    from app.config import get_settings
    from app.storage.local import LocalStorage
    client = clients[0]
    pid = client.post("/api/v1/projects", json={"name": "Upload"}).json()["id"]
    url = f"/api/v1/projects/{pid}/source"
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 32)
    assert client.post(url, content=b"x" * 33).status_code == 413
    assert client.post(url, content=b"").status_code == 422
    result = client.post(url, content=b"not-an-mp4", headers={"X-Filename": "../../example.mp4"})
    assert result.status_code == 202, result.text
    with database() as db:
        source = db.scalar(select(Asset).where(Asset.project_id == pid, Asset.state == "pending"))
        assert source.meta_json["filename"] == "example.mp4"
        assert LocalStorage().path(source.storage_key).read_bytes() == b"not-an-mp4"
        assert not list(get_settings().media_root.glob("uploads/*.part"))
    project = client.get(f"/api/v1/projects/{pid}").json()
    assert project["source_asset"]["content_url"] is None


def test_deletion_revokes_access_immediately(clients, ready_project):
    client = clients[0]
    pid = ready_project["project_id"]
    clip = make_clip(client, pid)
    job = client.post(f"/api/v1/clips/{clip['id']}/exports", json={"revision": 1, "resolution": 720}).json()
    deletion = client.delete(f"/api/v1/projects/{pid}")
    assert deletion.status_code == 202, deletion.text
    assert client.get(f"/api/v1/projects/{pid}").status_code == 404
    assert client.get(f"/api/v1/assets/{ready_project['asset_id']}/content").status_code == 404
    assert client.get(f"/api/v1/clips/{clip['id']}").status_code == 404
    assert client.post(f"/api/v1/jobs/{job['id']}/retry").status_code == 404
    assert client.get(f"/api/v1/jobs/{deletion.json()['id']}").status_code == 200


def test_clip_validation_rejects_outside_bounds_and_bad_cues(clients, ready_project):
    url = f"/api/v1/projects/{ready_project['project_id']}/clips"
    for payload in ({"start_ms": 0, "end_ms": 4999}, {"start_ms": 8000, "end_ms": 14000}, {"start_ms": 0, "end_ms": 6000, "cues": [{"start_ms": 0, "end_ms": 6001, "text": "Invalid"}]}, {"start_ms": 0, "end_ms": 6000, "crop_json": {"x": 2}}):
        assert clients[0].post(url, json=payload).status_code == 422


def test_paginated_export_history_filters_clip_without_cross_owner_access(clients, ready_project):
    client, other = clients
    pid = ready_project["project_id"]
    clips = [make_clip(client, pid) for _ in range(3)]
    for clip in clips:
        assert client.post(f"/api/v1/clips/{clip['id']}/exports", json={"revision": 1, "resolution": 720}).status_code == 202
    endpoint = f"/api/v1/projects/{pid}/exports"
    first = client.get(endpoint, params={"page_size": 1, "page": 1}).json()
    second = client.get(endpoint, params={"page_size": 1, "page": 2}).json()
    assert first["total"] == second["total"] == 3
    assert first["items"][0]["id"] != second["items"][0]["id"]
    filtered = client.get(endpoint, params={"clip_id": clips[0]["id"]}).json()
    assert filtered["total"] == 1 and filtered["items"][0]["clip_id"] == clips[0]["id"]
    assert other.get(endpoint, params={"clip_id": clips[0]["id"]}).status_code == 404
    assert client.get(endpoint, params={"clip_id": "unknown"}).json()["total"] == 0
