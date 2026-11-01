"""Gaming layout validation and immutable revision/export plumbing, isolated DB."""
import copy
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.schemas import Crop, SourceRegion, TrackingCrop
from app.domain.models import ClipRevision, Export, Job, Project
from app.jobs.tasks import run_job


def gaming_crop(**changes):
    crop = {"mode": "gaming", "tracking": "static", "x": .5, "y": .5, "gaming": {
        "facecam": {"x": .72, "y": .04, "width": .25, "height": .3},
        "gameplay": {"x": 0, "y": 0, "width": 1, "height": 1},
        "facecam_height": .28, "facecam_fit": "fill", "gameplay_fit": "fit"}}
    crop.update(changes)
    return crop


def create_clip(client, project_id, crop=None):
    return client.post(f"/api/v1/projects/{project_id}/clips", json={"start_ms": 1000, "end_ms": 8000,
                       "crop_json": crop if crop is not None else gaming_crop()})


def test_legacy_crop_serialization_stays_identical():
    assert Crop().model_dump() == {"mode": "fill", "tracking": "static", "x": .5, "y": .5}
    assert Crop(mode="fit", gaming=None).model_dump() == {"mode": "fit", "tracking": "static", "x": .5, "y": .5}
    assert TrackingCrop(tracking="face").model_dump() == {"mode": "fill", "tracking": "face", "x": .5, "y": .5}
    assert "gaming" not in json.loads(Crop().model_dump_json())


def test_gaming_defaults_and_overlapping_regions_are_preserved(clients, ready_project):
    crop = gaming_crop()
    minimal = {"mode": "gaming", "gaming": {"facecam": crop["gaming"]["facecam"], "gameplay": crop["gaming"]["gameplay"]}}
    response = create_clip(clients[0], ready_project["project_id"], minimal)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["revision"]["crop_json"] == crop
    assert clients[0].get(f"/api/v1/clips/{saved['id']}").json()["revision"]["crop_json"] == crop


@pytest.mark.parametrize("field,value", [("x", -.01), ("x", 1.01), ("y", -.01), ("y", 1.01),
    ("width", 0), ("width", .019), ("width", 1.01), ("height", 0), ("height", .019), ("height", 1.01),
    ("width", .3), ("height", .97)])
def test_invalid_region_geometry_rejected(clients, ready_project, field, value):
    crop = gaming_crop()
    crop["gaming"]["facecam"][field] = value
    response = create_clip(clients[0], ready_project["project_id"], crop)
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["x", "y", "width", "height"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_region_requires_finite_numbers(field, value):
    region = {"x": 0, "y": 0, "width": .5, "height": .5, field: value}
    with pytest.raises(ValidationError):
        SourceRegion.model_validate(region)


def test_non_finite_json_returns_safe_api_validation_error(clients, ready_project):
    crop = gaming_crop()
    crop["gaming"]["facecam"]["x"] = float("nan")
    response = clients[0].post(f"/api/v1/projects/{ready_project['project_id']}/clips",
                              content=json.dumps({"start_ms": 0, "end_ms": 6000, "crop_json": crop}),
                              headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert set(response.json()) == {"code", "message", "correlation_id"}


@pytest.mark.parametrize("change", ["missing_layout", "missing_facecam", "missing_gameplay", "fill_with_layout", "fit_with_layout",
    "face_tracking", "speaker_tracking", "small_panel", "large_panel", "bad_facecam_fit", "bad_gameplay_fit", "unknown_field"])
def test_gaming_layout_requires_valid_static_configuration(clients, ready_project, change):
    crop = gaming_crop()
    if change == "missing_layout":
        crop.pop("gaming")
    elif change.startswith("missing_"):
        crop["gaming"].pop(change.removeprefix("missing_"))
    elif change in ("fill_with_layout", "fit_with_layout"):
        crop["mode"] = change.split("_", 1)[0]
    elif change in ("face_tracking", "speaker_tracking"):
        crop["tracking"] = change.split("_", 1)[0]
    elif change in ("small_panel", "large_panel"):
        crop["gaming"]["facecam_height"] = .149 if change == "small_panel" else .451
    elif change in ("bad_facecam_fit", "bad_gameplay_fit"):
        crop["gaming"][change.removeprefix("bad_")] = "stretch"
    else:
        crop["gaming"]["detect_intensity"] = True
    assert create_clip(clients[0], ready_project["project_id"], crop).status_code == 422


def test_valid_edge_regions_and_panel_limits(clients, ready_project):
    for height in (.15, .45):
        crop = gaming_crop()
        crop["gaming"].update(facecam={"x": .98, "y": .98, "width": .02, "height": .02},
                              facecam_height=height, facecam_fit="fit", gameplay_fit="fill")
        assert create_clip(clients[0], ready_project["project_id"], crop).status_code == 201
    # Normalized coordinates from browser arithmetic can exceed one by epsilon.
    assert SourceRegion(x=.7, y=0, width=.3000000005, height=1).width > .3


def test_gaming_ownership_csrf_and_tracking_preview_rejection(clients, ready_project):
    owner, other = clients
    project_id = ready_project["project_id"]
    assert create_clip(other, project_id).status_code == 404
    assert owner.post(f"/api/v1/projects/{project_id}/clips", json={"start_ms": 0, "end_ms": 6000, "crop_json": gaming_crop()},
                      headers={"X-CSRF-Token": "invalid"}).status_code == 403
    clip = create_clip(owner, project_id).json()
    endpoint = f"/api/v1/clips/{clip['id']}"
    assert other.patch(endpoint, json={"expected_revision": 1, "crop_json": gaming_crop()}).status_code == 404
    assert other.post(endpoint + "/exports", json={"revision": 1}).status_code == 404
    assert owner.post(endpoint + "/tracking-preview", json={"start_ms": 1000, "end_ms": 8000,
                                                            "crop_json": gaming_crop()}).status_code == 422


def test_title_edits_preserve_gaming_and_mode_switch_removes_inactive_layout(clients, ready_project, database):
    owner = clients[0]
    clip = create_clip(owner, ready_project["project_id"]).json()
    endpoint = f"/api/v1/clips/{clip['id']}"
    title = owner.patch(endpoint, json={"expected_revision": 1, "title": "Changed title"})
    assert title.status_code == 200
    assert title.json()["revision"]["crop_json"] == gaming_crop()
    switched = owner.patch(endpoint, json={"expected_revision": 2, "crop_json": {"mode": "fill", "tracking": "face", "x": .4, "y": .6}})
    assert switched.status_code == 200
    assert switched.json()["revision"]["crop_json"] == {"mode": "fill", "tracking": "face", "x": .4, "y": .6}
    with database() as db:
        assert db.get(ClipRevision, clip["revision"]["id"]).crop_json == gaming_crop()


def test_exports_use_saved_gaming_snapshot_and_skip_tracking_cache(clients, ready_project, database, monkeypatch):
    from app.media.gaming import GAMING_LAYOUT_VERSION
    owner = clients[0]
    clip = create_clip(owner, ready_project["project_id"]).json()
    endpoint = f"/api/v1/clips/{clip['id']}"
    first = owner.post(endpoint + "/exports", json={"revision": 1, "resolution": 720}).json()
    assert owner.post(endpoint + "/exports", json={"revision": 1, "resolution": 720}).json()["id"] == first["id"]
    changed = gaming_crop()
    changed["gaming"]["facecam_height"] = .4
    saved = owner.patch(endpoint, json={"expected_revision": 1, "crop_json": changed})
    assert saved.status_code == 200
    second = owner.post(endpoint + "/exports", json={"revision": 2, "resolution": 720}).json()
    assert second["id"] != first["id"]
    snapshots = []
    def controlled_render(source, directory, snapshot, config, **options):
        snapshots.append(copy.deepcopy(snapshot))
        assert options["tracking_result"] is None
        mp4, srt = directory / "result.mp4", directory / "captions.srt"
        mp4.write_bytes(b"controlled adapter, not an actual MP4")
        srt.write_text("", encoding="utf-8")
        return {"mp4": mp4, "srt": srt, "meta": {"framing": {"mode": "static", "layout": "gaming", "method": GAMING_LAYOUT_VERSION}}}
    def unexpected_cache(*args, **kwargs):
        pytest.fail("Gaming must not analyze or reuse speaker tracking")
    monkeypatch.setattr("app.jobs.tasks.render_clip", controlled_render)
    monkeypatch.setattr("app.jobs.tasks.find_tracking_result", unexpected_cache)
    monkeypatch.setattr("app.jobs.tasks.track_clip", unexpected_cache)
    run_job(first["id"])
    run_job(second["id"])
    assert [snapshot["crop_json"] for snapshot in snapshots] == [gaming_crop(), changed]
    with database() as db:
        for job_id in (first["id"], second["id"]):
            job = db.get(Job, job_id)
            assert job.status == "succeeded", (job.error_code, job.error_message)
            assert job.input_json["gaming_layout_version"] == GAMING_LAYOUT_VERSION
            assert "tracking_signature" not in job.input_json


def test_layout_version_changes_export_fingerprint_and_fences_old_queued_render(clients, ready_project, database, monkeypatch):
    owner = clients[0]
    clip = create_clip(owner, ready_project["project_id"]).json()
    endpoint = f"/api/v1/clips/{clip['id']}/exports"
    first = owner.post(endpoint, json={"revision": 1, "resolution": 720}).json()
    monkeypatch.setattr("app.media.gaming.GAMING_LAYOUT_VERSION", "gaming-layout-next-test")
    second = owner.post(endpoint, json={"revision": 1, "resolution": 720}).json()
    assert second["id"] != first["id"]
    def unexpected_render(*args, **kwargs):
        pytest.fail("Stale layout request must be rejected before rendering")
    monkeypatch.setattr("app.jobs.tasks.render_clip", unexpected_render)
    run_job(first["id"])
    with database() as db:
        old = db.get(Job, first["id"])
        assert old.status == "failed" and old.error_code == "gaming_layout_changed"
        assert db.get(Project, ready_project["project_id"]).status == "ready"
        assert db.scalar(select(func.count()).select_from(Export)) == 2
