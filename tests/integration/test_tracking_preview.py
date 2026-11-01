"""Draft tracking analyses use isolated DB/storage and controlled local media adapters."""
import copy
import hashlib
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.domain.models import Asset, ClipRevision, Export, Job, OutboxEvent, Project, utcnow
from app.jobs.reconciler import reconcile_once
from app.jobs.tasks import run_job
from app.jobs.tracking_cache import find_tracking_result
from app.media.process import MediaError
from app.media.tracking_versions import ANALYSIS_VERSION, FACE_METHOD, SPEAKER_METHOD
from app.storage.local import LocalStorage

SPEAKER_MODEL_BYTES = b"controlled audiovisual model; no real inference"
SPEAKER_MODEL_HASH = hashlib.sha256(SPEAKER_MODEL_BYTES).hexdigest()


@pytest.fixture(autouse=True)
def tracking_model(tmp_path, monkeypatch):
    path = tmp_path / "controlled-model.onnx"
    path.write_bytes(b"controlled detector signature; no real model inference")
    monkeypatch.setattr(get_settings(), "tracking_model_path", str(path))
    speaker_path = tmp_path / "controlled-speaker.onnx"
    speaker_path.write_bytes(SPEAKER_MODEL_BYTES)
    monkeypatch.setattr(get_settings(), "speaker_model_path", str(speaker_path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clip_for(client, project_id):
    response = client.post(f"/api/v1/projects/{project_id}/clips", json={"start_ms": 0, "end_ms": 8000})
    assert response.status_code == 201, response.text
    return response.json()


def draft(**changes):
    value = {"start_ms": 1000, "end_ms": 7000,
             "crop_json": {"mode": "fill", "tracking": "speaker", "x": .7, "y": .4}}
    value.update(changes)
    return value


def request_preview(client, clip, body=None, key=None):
    return client.post(f"/api/v1/clips/{clip['id']}/tracking-preview", json=body or draft(),
                       headers={"Idempotency-Key": key} if key else {})


def framing(model_hash, **changes):
    result = {"mode": "speaker", "method": SPEAKER_METHOD, "model_sha256": model_hash,
              "speaker_model_sha256": SPEAKER_MODEL_HASH,
              "sample_fps": 6, "total_frames": 36, "detected_frames": 36, "fallback_reason": None,
              "keyframes": [{"t_ms": 0, "x": .2, "y": .4, "cut": True},
                            {"t_ms": 6000, "x": .8, "y": .4, "cut": False}]}
    result.update(changes)
    return result


def test_unsaved_draft_dedupes_across_clips_revisions_and_keys(clients, ready_project, database):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    before = owner.get(f"/api/v1/clips/{clip['id']}").json()["revision"]
    first = request_preview(owner, clip, key="first")
    assert first.status_code == 202, first.text
    assert first.json()["kind"] == "track_preview"
    assert request_preview(owner, clip, key="second").json()["id"] == first.json()["id"]
    another = clip_for(owner, ready_project["project_id"])
    assert request_preview(owner, another).json()["id"] == first.json()["id"]
    assert owner.get(f"/api/v1/clips/{clip['id']}").json()["revision"] == before
    saved = owner.patch(f"/api/v1/clips/{clip['id']}", json={"expected_revision": 1, **draft()})
    assert saved.status_code == 200
    assert request_preview(owner, clip).json()["id"] == first.json()["id"]
    with database() as db:
        job = db.get(Job, first.json()["id"])
        assert set(job.input_json) == {"tracking_spec"}
        spec = job.input_json["tracking_spec"]
        assert spec["source_asset_id"] == ready_project["asset_id"]
        assert spec["crop_json"] == draft()["crop_json"]
        assert "clip_id" not in spec and "clip_revision_id" not in spec
        assert db.scalar(select(func.count()).select_from(Export)) == 0
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        assert db.scalar(select(func.count()).select_from(Asset)) == 1


@pytest.mark.parametrize("body", [draft(start_ms=-1), draft(end_ms=13000), draft(end_ms=5000),
    draft(start_ms=7000, end_ms=6000), draft(crop_json={"mode": "fit", "tracking": "face"}),
    draft(crop_json={"tracking": "static"}), draft(crop_json={"tracking": "face", "x": 2}),
    {**draft(), "revision": 1}])
def test_preview_rejects_invalid_bounds_and_modes(clients, ready_project, body):
    clip = clip_for(clients[0], ready_project["project_id"])
    assert request_preview(clients[0], clip, body).status_code == 422


def test_preview_ownership_csrf_source_and_tombstone(clients, ready_project, database):
    owner, other = clients
    clip = clip_for(owner, ready_project["project_id"])
    assert request_preview(other, clip).status_code == 404
    endpoint = f"/api/v1/clips/{clip['id']}/tracking-preview"
    assert owner.post(endpoint, json=draft(), headers={"X-CSRF-Token": "wrong"}).status_code == 403
    with database() as db:
        db.get(Asset, ready_project["asset_id"]).state = "validating"
        db.commit()
    assert request_preview(owner, clip).status_code == 409
    with database() as db:
        db.get(Asset, ready_project["asset_id"]).state = "ready"
        db.get(Project, ready_project["project_id"]).lifecycle_state = "deleting"
        db.commit()
    assert request_preview(owner, clip).status_code == 404


def test_preview_idempotency_and_queue_limits(clients, ready_project, monkeypatch):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    monkeypatch.setattr(get_settings(), "max_active_jobs_per_user", 1)
    first = request_preview(owner, clip, key="same").json()
    assert request_preview(owner, clip, key="alias").json()["id"] == first["id"]
    assert request_preview(owner, clip, draft(start_ms=0), key="same").status_code == 409
    assert request_preview(owner, clip, draft(start_ms=0)).status_code == 429
    assert request_preview(owner, clip, key="x" * 129).status_code == 422


def test_preview_duration_limits_include_five_and_180_seconds(clients, ready_project, database):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    with database() as db:
        asset = db.get(Asset, ready_project["asset_id"])
        asset.meta_json = {**asset.meta_json, "duration_ms": 240000}
        db.commit()
    assert request_preview(owner, clip, draft(start_ms=0, end_ms=5000)).status_code == 202
    assert request_preview(owner, clip, draft(start_ms=0, end_ms=180000)).status_code == 202
    assert request_preview(owner, clip, draft(start_ms=0, end_ms=180001)).status_code == 422


def test_preview_worker_uses_proxy_and_publishes_only_analysis(clients, ready_project, database, monkeypatch, tracking_model):
    owner = clients[0]
    project_id = ready_project["project_id"]
    storage = LocalStorage()
    key = storage.new_key(project_id, ".mp4")
    path = storage.prepare(key)
    path.write_bytes(b"controlled proxy")
    with database() as db:
        preview = Asset(project_id=project_id, kind="preview", state="ready", storage_key=key,
                        checksum=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=16, mime="video/mp4")
        db.add(preview)
        db.flush()
        db.get(Project, project_id).preview_asset_id = preview.id
        preview_id = preview.id
        db.commit()
    clip = clip_for(owner, project_id)
    job = request_preview(owner, clip).json()
    def analyze(source, directory, **options):
        assert source == path
        assert options["start_ms"] == 1000 and options["end_ms"] == 7000
        assert options["crop"] == draft()["crop_json"]
        assert str(options["speaker_model_path"]) == get_settings().speaker_model_path
        with database() as db:
            assert db.get(Job, job["id"]).stage == "track_faces"
        options["progress"](.5)
        return framing(tracking_model)
    monkeypatch.setattr("app.jobs.tasks.track_clip", analyze)
    run_job(job["id"])
    result = owner.get(f"/api/v1/jobs/{job['id']}").json()
    assert result["status"] == "succeeded", result
    assert result["result_json"]["tracking_spec"]["preview_asset_id"] == preview_id
    assert result["result_json"]["framing"] == framing(tracking_model)
    assert request_preview(owner, clip).json() == result
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Asset)) == 2
        assert db.scalar(select(func.count()).select_from(Export)) == 0
        assert db.scalar(select(func.count()).select_from(ClipRevision)) == 1
        assert db.get(Project, project_id).status == "ready"


@pytest.mark.parametrize("failure", ["manual", "exception", "bad_model"])
def test_failed_analysis_does_not_fail_project_and_can_retry(clients, ready_project, database, monkeypatch, tracking_model, failure):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    job = request_preview(owner, clip).json()
    def failed(*args, **kwargs):
        if failure == "exception":
            raise MediaError("media_failed", "Controlled failure")
        return framing(tracking_model, **({"method": "manual", "fallback_reason": "Unavailable"}
                                        if failure == "manual" else {"model_sha256": "different"}))
    monkeypatch.setattr("app.jobs.tasks.track_clip", failed)
    run_job(job["id"])
    status = owner.get(f"/api/v1/jobs/{job['id']}").json()
    assert status["status"] == "failed" and status["result_json"] == {}
    assert request_preview(owner, clip).json()["id"] == job["id"]
    with database() as db:
        project = db.get(Project, ready_project["project_id"])
        assert project.status == "ready" and project.error_message is None
    monkeypatch.setattr("app.jobs.tasks.track_clip", lambda *a, **kw: framing(tracking_model))
    assert owner.post(f"/api/v1/jobs/{job['id']}/retry").status_code == 202
    run_job(job["id"])
    assert owner.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "succeeded"


def test_completed_no_face_result_is_cacheable(clients, ready_project, database, monkeypatch, tracking_model):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    job = request_preview(owner, clip).json()
    expected = framing(tracking_model, detected_frames=0, fallback_reason="Wajah tidak terdeteksi; posisi manual digunakan.")
    monkeypatch.setattr("app.jobs.tasks.track_clip", lambda *a, **kw: expected)
    run_job(job["id"])
    with database() as db:
        row = db.get(Job, job["id"])
        assert row.status == "succeeded"
        assert find_tracking_result(db, ready_project["project_id"], row.input_json["tracking_spec"]) == expected


@pytest.mark.parametrize("mode", ["face", "speaker"])
def test_v1_jobs_remain_immutable_but_new_requests_get_current_signature(clients, ready_project, database, mode):
    from app.jobs.service import create_job
    from app.jobs.tracking_cache import make_tracking_spec
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    body = draft(crop_json={**draft()["crop_json"], "tracking": mode})
    with database() as db:
        source = db.get(Asset, ready_project["asset_id"])
        spec = make_tracking_spec(source, None, body["start_ms"], body["end_ms"], body["crop_json"])
        spec["analysis_version"] = "tracking-preview-1"
        spec["method"] = "yunet-mouth-motion-audio-v1" if mode == "speaker" else FACE_METHOD
        spec.pop("algorithm_signature")
        spec.pop("speaker_model_sha256")
        old = create_job(db, db.get(Project, ready_project["project_id"]), "track_preview", {"tracking_spec": spec})
        old.status = "succeeded"
        old.result_json = {"tracking_spec": spec, "framing": {"mode": mode, "method": spec["method"]}}
        old_id, old_result = old.id, copy.deepcopy(old.result_json)
        db.commit()
    fresh = request_preview(owner, clip, body)
    assert fresh.status_code == 202 and fresh.json()["id"] != old_id
    with database() as db:
        old = db.get(Job, old_id)
        current = db.get(Job, fresh.json()["id"]).input_json["tracking_spec"]
        assert old.result_json == old_result and old.status == "succeeded"
        assert current["analysis_version"] == ANALYSIS_VERSION
        assert current["algorithm_signature"] == clip["tracking_signatures"][mode]
        assert find_tracking_result(db, ready_project["project_id"], spec) is None
        assert find_tracking_result(db, ready_project["project_id"], current) is None


def test_missing_speaker_model_fails_preview_without_heuristic_reuse(clients, ready_project, database, monkeypatch, tmp_path, tracking_model):
    owner = clients[0]
    missing = tmp_path / "not-yet-installed.onnx"
    monkeypatch.setattr(get_settings(), "speaker_model_path", str(missing))
    clip = clip_for(owner, ready_project["project_id"])
    speaker_signature = clip["tracking_signatures"]["speaker"]
    face_signature = clip["tracking_signatures"]["face"]
    job = request_preview(owner, clip).json()
    # Even a faulty adapter claiming successful inference cannot publish it.
    monkeypatch.setattr("app.jobs.tasks.track_clip", lambda *a, **kw: framing(tracking_model))
    run_job(job["id"])
    with database() as db:
        row = db.get(Job, job["id"])
        assert row.status == "failed" and row.error_code == "tracking_unavailable"
        assert row.result_json == {} and row.input_json["tracking_spec"]["speaker_model_sha256"] is None
        assert db.get(Project, ready_project["project_id"]).status == "ready"
    missing.write_bytes(SPEAKER_MODEL_BYTES)
    refreshed = owner.get(f"/api/v1/clips/{clip['id']}").json()
    assert refreshed["tracking_signatures"]["speaker"] != speaker_signature
    assert refreshed["tracking_signatures"]["face"] == face_signature
    fresh = request_preview(owner, clip).json()
    assert fresh["id"] != job["id"]
    run_job(fresh["id"])
    assert owner.get(f"/api/v1/jobs/{fresh['id']}").json()["status"] == "succeeded"


def test_export_deduplication_changes_with_model_without_mutating_saved_revision(clients, ready_project, database):
    from pathlib import Path
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    endpoint = f"/api/v1/clips/{clip['id']}"
    assert owner.patch(endpoint, json={"expected_revision": 1, **draft()}).status_code == 200
    saved = owner.get(endpoint).json()
    original = owner.post(endpoint + "/exports", json={"revision": 2, "resolution": 720}).json()
    with database() as db:
        row = db.get(Job, original["id"])
        row.status, row.result_json = "succeeded", {"preserved": True}
        old_signature = row.input_json["tracking_signature"]
        db.commit()
    Path(get_settings().speaker_model_path).write_bytes(b"updated trained model")
    response = owner.post(endpoint + "/exports", json={"revision": 2, "resolution": 720})
    assert response.status_code == 202 and response.json()["id"] != original["id"]
    repeated = owner.post(endpoint + "/exports", json={"revision": 2, "resolution": 720})
    assert repeated.json()["id"] == response.json()["id"]
    assert owner.get(endpoint).json()["revision"] == saved["revision"]
    with database() as db:
        assert db.get(Job, original["id"]).result_json == {"preserved": True}
        assert db.get(Job, response.json()["id"]).input_json["tracking_signature"] != old_signature
        assert db.scalar(select(func.count()).select_from(Export)) == 2


def test_queued_export_rejects_changed_model_signature(clients, ready_project, database, monkeypatch):
    from pathlib import Path
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    endpoint = f"/api/v1/clips/{clip['id']}"
    assert owner.patch(endpoint, json={"expected_revision": 1, **draft()}).status_code == 200
    job = owner.post(endpoint + "/exports", json={"revision": 2, "resolution": 720}).json()
    Path(get_settings().speaker_model_path).write_bytes(b"changed before worker claims")
    def unexpected(*args, **kwargs):
        pytest.fail("A stale request must be rejected before rendering")
    monkeypatch.setattr("app.jobs.tasks.render_clip", unexpected)
    run_job(job["id"])
    with database() as db:
        status = db.get(Job, job["id"])
        assert status.status == "failed" and status.error_code == "tracking_input_changed"
        assert db.get(Project, ready_project["project_id"]).status == "ready"


@pytest.mark.parametrize("change", ["model", "speaker_model", "source", "proxy"])
def test_changed_analysis_inputs_cannot_publish_stale_result(clients, ready_project, database, monkeypatch, tracking_model, change):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    job = request_preview(owner, clip).json()
    def mutate_inputs(*args, **kwargs):
        if change in ("model", "speaker_model"):
            from pathlib import Path
            path = get_settings().tracking_model_path if change == "model" else get_settings().speaker_model_path
            Path(path).write_bytes(b"new model version")
        else:
            with database() as db:
                if change == "source":
                    db.get(Asset, ready_project["asset_id"]).checksum = "a" * 64
                else:
                    project = db.get(Project, ready_project["project_id"])
                    proxy = Asset(project_id=project.id, storage_key="controlled-proxy.mp4", kind="preview",
                                  state="ready", bytes=1, mime="video/mp4", checksum="b" * 64)
                    db.add(proxy)
                    db.flush()
                    project.preview_asset_id = proxy.id
                db.commit()
        return framing(tracking_model)
    monkeypatch.setattr("app.jobs.tasks.track_clip", mutate_inputs)
    run_job(job["id"])
    status = owner.get(f"/api/v1/jobs/{job['id']}").json()
    assert status["status"] == "failed" and status["error_code"] == "tracking_input_changed"
    assert status["result_json"] == {}
    fresh = request_preview(owner, clip)
    assert fresh.status_code == 202 and fresh.json()["id"] != job["id"]


@pytest.mark.parametrize("corruption", ["failed", "cancelled", "input", "result_spec", "coordinates", "signature", "speaker_signature", "old_method", "manual"])
def test_cache_rejects_non_success_or_malformed_results(clients, ready_project, database, monkeypatch, tracking_model, corruption):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    job = request_preview(owner, clip).json()
    monkeypatch.setattr("app.jobs.tasks.track_clip", lambda *a, **kw: framing(tracking_model))
    run_job(job["id"])
    with database() as db:
        row = db.get(Job, job["id"])
        spec = copy.deepcopy(row.input_json["tracking_spec"])
        result = copy.deepcopy(row.result_json)
        if corruption in ("failed", "cancelled"):
            row.status = corruption
        elif corruption == "input":
            row.input_json = {"tracking_spec": {**spec, "start_ms": 0}}
        elif corruption == "result_spec":
            result["tracking_spec"]["end_ms"] += 1
        elif corruption == "coordinates":
            result["framing"]["keyframes"][0]["x"] = "malformed"
        elif corruption == "signature":
            result["framing"]["model_sha256"] = "different"
        elif corruption == "speaker_signature":
            result["framing"]["speaker_model_sha256"] = "different"
        elif corruption == "old_method":
            result["framing"]["method"] = "yunet-mouth-motion-audio-v1"
        else:
            result["framing"]["method"] = "manual"
            result["framing"]["fallback_reason"] = "Tracker failed"
        row.result_json = result
        db.commit()
        assert find_tracking_result(db, ready_project["project_id"], spec) is None


@pytest.mark.parametrize("change", ["start_ms", "end_ms", "crop_json", "source_asset_id", "source_checksum", "preview_asset_id", "preview_checksum", "model_sha256", "speaker_model_sha256", "algorithm_signature", "method", "sample_fps", "pipeline_version", "analysis_version"])
def test_cache_identity_rejects_changed_source_bounds_crop_and_algorithm(clients, ready_project, database, monkeypatch, tracking_model, change):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    job = request_preview(owner, clip).json()
    monkeypatch.setattr("app.jobs.tasks.track_clip", lambda *a, **kw: framing(tracking_model))
    run_job(job["id"])
    with database() as db:
        row = db.get(Job, job["id"])
        spec = copy.deepcopy(row.input_json["tracking_spec"])
        assert find_tracking_result(db, ready_project["project_id"], spec) is not None
        spec[change] = ({**spec[change], "x": .1} if change == "crop_json" else
                        spec[change] + 1 if type(spec[change]) is int else "changed")
        assert find_tracking_result(db, ready_project["project_id"], spec) is None


def test_render_reuses_draft_analysis_after_save_and_title_edit(clients, ready_project, database, monkeypatch, tracking_model):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    preview = request_preview(owner, clip).json()
    monkeypatch.setattr("app.jobs.tasks.track_clip", lambda *a, **kw: framing(tracking_model))
    run_job(preview["id"])
    endpoint = f"/api/v1/clips/{clip['id']}"
    assert owner.patch(endpoint, json={"expected_revision": 1, **draft()}).status_code == 200
    assert owner.patch(endpoint, json={"expected_revision": 2, "title": "Caption edit", "cues": [{"start_ms": 0, "end_ms": 3000, "text": "Test"}]}).status_code == 200
    captured = []
    def controlled_render(source, directory, revision, config, **options):
        captured.append(options["tracking_result"])
        mp4, srt = directory / "result.mp4", directory / "captions.srt"
        mp4.write_bytes(b"controlled adapter only")
        srt.write_text("", encoding="utf-8")
        return {"mp4": mp4, "srt": srt, "meta": {}}
    monkeypatch.setattr("app.jobs.tasks.render_clip", controlled_render)
    render = owner.post(endpoint + "/exports", json={"revision": 3, "resolution": 720}).json()
    run_job(render["id"])
    assert owner.get(f"/api/v1/jobs/{render['id']}").json()["status"] == "succeeded"
    assert captured == [framing(tracking_model)]
    assert owner.patch(endpoint, json={"expected_revision": 3, "start_ms": 0}).status_code == 200
    changed = owner.post(endpoint + "/exports", json={"revision": 4, "resolution": 720}).json()
    run_job(changed["id"])
    assert captured[1] is None
    with database() as db:
        assert "analysis_reused" not in db.get(Job, preview["id"]).result_json["framing"]


@pytest.mark.parametrize("cancel", ["cancel", "delete"])
def test_running_preview_fenced_on_cancellation_or_tombstone(clients, ready_project, database, monkeypatch, tracking_model, cancel):
    owner = clients[0]
    clip = clip_for(owner, ready_project["project_id"])
    job = request_preview(owner, clip).json()
    def interrupted(*args, **kwargs):
        if cancel == "delete":
            assert owner.delete(f"/api/v1/projects/{ready_project['project_id']}").status_code == 202
        else:
            assert owner.post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 200
        return framing(tracking_model)
    monkeypatch.setattr("app.jobs.tasks.track_clip", interrupted)
    run_job(job["id"])
    with database() as db:
        row = db.get(Job, job["id"])
        assert row.status == "cancelled" and row.result_json == {}
        if cancel == "cancel":
            assert db.get(Project, ready_project["project_id"]).status == "ready"


def test_lease_failure_preserves_project_and_deletion_clears_tracking_payloads(clients, ready_project, database, monkeypatch, tracking_model):
    owner = clients[0]
    project_id = ready_project["project_id"]
    clip = clip_for(owner, project_id)
    succeeded = request_preview(owner, clip).json()
    monkeypatch.setattr("app.jobs.tasks.track_clip", lambda *a, **kw: framing(tracking_model))
    run_job(succeeded["id"])
    expired = request_preview(owner, clip, draft(start_ms=0)).json()
    with database() as db:
        job = db.get(Job, expired["id"])
        job.status, job.attempt = "running", get_settings().job_max_attempts
        job.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    reconcile_once()
    with database() as db:
        assert db.get(Job, expired["id"]).status == "failed"
        assert db.get(Project, project_id).status == "ready"
    deleted = owner.delete(f"/api/v1/projects/{project_id}").json()
    run_job(deleted["id"])
    with database() as db:
        assert db.get(Project, project_id).lifecycle_state == "deleted"
        for job_id in (succeeded["id"], expired["id"]):
            job = db.get(Job, job_id)
            assert job.input_json == {} and job.result_json == {}
