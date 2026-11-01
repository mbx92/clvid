"""Tracking selection/revision contract against the isolated test database."""
from sqlalchemy import select

from app.domain.models import Asset, ClipRevision, Export, Job, Project
from app.jobs.tasks import run_job
from app.storage.local import LocalStorage


def create_tracked(client, project_id):
    response = client.post(f"/api/v1/projects/{project_id}/clips", json={"start_ms": 0, "end_ms": 8000,
                           "crop_json": {"mode": "fill", "tracking": "face", "x": .25, "y": .7}})
    assert response.status_code == 201, response.text
    return response.json()


def test_tracking_mode_is_saved_in_immutable_export_revision(clients, ready_project, database):
    client = clients[0]
    clip = create_tracked(client, ready_project["project_id"])
    endpoint = f"/api/v1/clips/{clip['id']}"
    original = client.post(endpoint + "/exports", json={"revision": 1, "resolution": 720})
    assert original.status_code == 202
    revised = client.patch(endpoint, json={"expected_revision": 1,
                           "crop_json": {"mode": "fill", "tracking": "speaker", "x": .25, "y": .7}})
    assert revised.status_code == 200, revised.text
    assert revised.json()["revision"]["revision"] == 2
    second = client.post(endpoint + "/exports", json={"revision": 2, "resolution": 720})
    assert second.status_code == 202 and second.json()["id"] != original.json()["id"]
    with database() as db:
        export = db.scalar(select(Export).where(Export.job_id == original.json()["id"]))
        saved = db.get(ClipRevision, export.clip_revision_id)
        assert saved.crop_json == {"mode": "fill", "tracking": "face", "x": .25, "y": .7}
    invalid = client.patch(endpoint, json={"expected_revision": 2, "crop_json": {"tracking": "guaranteed-speaker"}})
    assert invalid.status_code == 422


def test_legacy_crop_without_tracking_remains_unchanged_on_read_and_title_edit(clients, ready_project, database):
    client = clients[0]
    clip = create_tracked(client, ready_project["project_id"])
    with database() as db:
        revision = db.get(ClipRevision, clip["revision"]["id"])
        revision.crop_json = {"mode": "fill", "x": .25, "y": .7}
        db.commit()
    endpoint = f"/api/v1/clips/{clip['id']}"
    read = client.get(endpoint)
    assert "tracking" not in read.json()["revision"]["crop_json"]
    updated = client.patch(endpoint, json={"expected_revision": 1, "title": "Judul tersimpan"})
    assert updated.status_code == 200 and updated.json()["revision"]["crop_json"] == {"mode": "fill", "x": .25, "y": .7}


def test_job_passes_preview_and_persists_tracking_metadata_with_controlled_render_adapter(clients, ready_project, database, monkeypatch):
    """Controlled media adapter tests DB plumbing; real detector/render tested separately."""
    client = clients[0]
    project_id = ready_project["project_id"]
    storage = LocalStorage()
    preview_key = storage.new_key(project_id, ".mp4")
    preview_path = storage.prepare(preview_key)
    preview_path.write_bytes(b"controlled preview test content")
    with database() as db:
        preview = Asset(project_id=project_id, storage_key=preview_key, kind="preview", state="ready", bytes=30, mime="video/mp4")
        db.add(preview)
        db.flush()
        db.get(Project, project_id).preview_asset_id = preview.id
        db.commit()
    clip = create_tracked(client, project_id)
    job = client.post(f"/api/v1/clips/{clip['id']}/exports", json={"revision": 1, "resolution": 720}).json()
    captured = {}
    framing = {"mode": "face", "method": "controlled-test-only", "fallback_reason": None,
               "detected_frames": 2, "total_frames": 2, "keyframes": [{"t_ms": 0, "x": .6, "y": .5}]}
    def controlled_render(source, directory, snapshot, config, **options):
        captured.update({"snapshot": snapshot, "tracking_source": options["tracking_source"]})
        options["stage"]("track_faces")
        with database() as db:
            assert db.get(Job, job["id"]).stage == "track_faces"
        options["stage"]("render")
        mp4, srt = directory / "render.mp4", directory / "captions.srt"
        mp4.write_bytes(b"controlled media adapter, not a real MP4")
        srt.write_text("", encoding="utf-8")
        return {"mp4": mp4, "srt": srt, "meta": {"duration_ms": 8000, "framing": framing}}
    monkeypatch.setattr("app.jobs.tasks.render_clip", controlled_render)
    run_job(job["id"])
    with database() as db:
        status = db.get(Job, job["id"])
        assert status.status == "succeeded", (status.error_code, status.error_message)
    assert captured["tracking_source"] == preview_path
    assert captured["snapshot"]["crop_json"]["tracking"] == "face"
    exports = client.get(f"/api/v1/projects/{project_id}/exports").json()["items"]
    assert exports[0]["mp4_asset"]["metadata"]["framing"] == framing
