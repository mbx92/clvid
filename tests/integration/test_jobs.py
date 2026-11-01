"""Database lifecycle tests. Broker failures are explicit controlled adapters."""
import os
import time
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.domain.models import Asset, Clip, Export, Job, JobAttempt, OutboxEvent, Project, Transcript, TranscriptSegment, utcnow
from app.jobs.dispatcher import dispatch_once
from app.jobs.reconciler import cleanup_once, reconcile_once
from app.jobs.runtime import JobContext, claim
from app.jobs.service import create_job
from app.jobs.tasks import run_job
from app.media.process import Cancelled
from app.storage.local import LocalStorage


def new_job(database, project_id, kind="analyze", inputs=None):
    with database() as db:
        job = create_job(db, db.get(Project, project_id), kind, inputs or {})
        db.commit()
        return job.id


def test_duplicate_delivery_has_only_one_claim(database, ready_project):
    job_id = new_job(database, ready_project["project_id"])
    first = claim(job_id)
    assert first and first[0] == 1
    assert claim(job_id) is None
    with database() as db:
        assert db.scalar(select(func.count()).select_from(JobAttempt)) == 1
        assert db.get(Job, job_id).status == "running"


def test_expired_lease_recovers_and_fences_old_attempt(database, ready_project):
    job_id = new_job(database, ready_project["project_id"])
    number, attempt_id = claim(job_id)
    with database() as db:
        db.get(Job, job_id).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert reconcile_once()["recovered"] == 1
    second = claim(job_id)
    assert second[0] == 2
    with database() as db:
        assert db.get(JobAttempt, attempt_id).outcome == "worker_lost"
        with pytest.raises(Cancelled):
            JobContext(job_id, number, attempt_id).check(db)


def test_recovery_attempts_bounded_and_cancellation_does_not_requeue(database, ready_project, monkeypatch):
    monkeypatch.setattr(get_settings(), "job_max_attempts", 1)
    job_id = new_job(database, ready_project["project_id"])
    claim(job_id)
    with database() as db:
        db.get(Job, job_id).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    reconcile_once()
    with database() as db:
        assert db.get(Job, job_id).status == "failed"
    cancelled_id = new_job(database, ready_project["project_id"], inputs={"different": True})
    claim(cancelled_id)
    with database() as db:
        row = db.get(Job, cancelled_id)
        row.status, row.lease_expires_at = "cancel_requested", utcnow() - timedelta(seconds=1)
        db.commit()
    reconcile_once()
    with database() as db:
        assert db.get(Job, cancelled_id).status == "cancelled"


def test_dispatch_failure_retains_outbox_then_dispatches(database, ready_project, monkeypatch):
    from app.jobs.dispatcher import celery_app
    job_id = new_job(database, ready_project["project_id"])
    def unavailable(*args, **kwargs):
        raise ConnectionError("Controlled broker outage")
    monkeypatch.setattr(celery_app, "send_task", unavailable)
    assert dispatch_once() == 0
    with database() as db:
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.job_id == job_id))
        assert event.attempt == 1 and event.dispatched_at is None
    sent = []
    monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: sent.append((args, kwargs)))
    assert dispatch_once() == 1
    assert sent[0][1]["queue"] == "light"
    with database() as db:
        assert db.scalar(select(OutboxEvent).where(OutboxEvent.job_id == job_id)).dispatched_at is not None


def test_queued_message_republished_after_broker_loss(database, ready_project):
    job_id = new_job(database, ready_project["project_id"])
    with database() as db:
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.job_id == job_id))
        event.dispatched_at = utcnow() - timedelta(minutes=10)
        db.commit()
    assert reconcile_once()["republished"] == 1
    assert reconcile_once()["republished"] == 0


def test_deletion_removes_files_transcript_clip_and_assets(clients, database, ready_project):
    client = clients[0]
    project_id = ready_project["project_id"]
    source_path = None
    with database() as db:
        source_path = LocalStorage().path(db.get(Asset, ready_project["asset_id"]).storage_key)
        transcript = Transcript(project_id=project_id, version=1, language="id", model="test-fixture")
        db.add(transcript)
        db.flush()
        db.add(TranscriptSegment(transcript_id=transcript.id, order=0, start_ms=0, end_ms=8000, text="Ucapan fixture milik pengguna"))
        db.commit()
    clip = client.post(f"/api/v1/projects/{project_id}/clips", json={"start_ms": 0, "end_ms": 8000, "title": "Manual"}).json()
    pending = client.post(f"/api/v1/clips/{clip['id']}/exports", json={"revision": 1, "resolution": 720}).json()
    private_scratch = LocalStorage().path(f"scratch/{pending['id']}/1")
    private_scratch.mkdir(parents=True)
    (private_scratch / "transcription-output.json").write_text("private transcript", encoding="utf-8")
    deletion = client.delete(f"/api/v1/projects/{project_id}").json()
    run_job(deletion["id"])
    run_job(deletion["id"])  # Duplicate delivery is inert.
    assert not source_path.exists()
    assert not private_scratch.exists()
    with database() as db:
        job = db.get(Job, deletion["id"])
        assert job.status == "succeeded", (job.error_code, job.error_message)
        assert db.get(Project, project_id).lifecycle_state == "deleted"
        assert db.get(Job, pending["id"]).status == "cancelled"
        for model in (Asset, Clip, Export, Transcript, TranscriptSegment):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_cleanup_recovers_dead_upload_and_preserves_active_scratch(database, ready_project, monkeypatch):
    monkeypatch.setattr(get_settings(), "partial_upload_ttl_seconds", 5)
    monkeypatch.setattr(get_settings(), "scratch_ttl_seconds", 5)
    storage = LocalStorage()
    partial = storage.prepare("uploads/dead.part")
    partial.write_bytes(b"partial")
    old = time.time() - 20
    os.utime(partial, (old, old))
    with database() as db:
        source = db.get(Asset, ready_project["asset_id"])
        source.state, source.meta_json = "uploading", {"upload_key": "uploads/dead.part"}
        source.created_at = utcnow() - timedelta(seconds=20)
        db.commit()
    active_id = new_job(database, ready_project["project_id"])
    scratch = storage.path(f"scratch/{active_id}/1")
    scratch.mkdir(parents=True)
    marker = scratch / ".terminal"
    marker.touch()
    os.utime(marker, (old, old))
    cleanup_once()
    assert not partial.exists() and scratch.exists()
    with database() as db:
        project = db.get(Project, ready_project["project_id"])
        assert project.source_asset_id is None and project.status == "empty"


def test_cancel_requested_blocks_publication_before_heartbeat(database, ready_project):
    job_id = new_job(database, ready_project["project_id"])
    number, attempt_id = claim(job_id)
    with database() as db:
        db.get(Job, job_id).status = "cancel_requested"
        db.commit()
    with database() as db, pytest.raises(Cancelled):
        JobContext(job_id, number, attempt_id).check(db)
