"""A lost media provider request must not silently start another billed call."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.domain.models import Job, JobAttempt, OutboxEvent, Project, utcnow
from app.jobs.reconciler import reconcile_once
from app.jobs.runtime import JobContext, claim
from app.jobs.service import create_job, retry_job
from app.media.process import Cancelled


def expired_job(database, project_id, kind, status="running"):
    with database() as db:
        job = create_job(db, db.get(Project, project_id), kind, {"version": 1})
        db.commit()
        job_id = job.id
    number, attempt_id = claim(job_id)
    with database() as db:
        job = db.get(Job, job_id)
        job.status = status
        job.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    return job_id, number, attempt_id


def test_lost_story_production_fails_without_automatic_billing_retry(database, ready_project):
    project_id = ready_project["project_id"]
    job_id, number, attempt_id = expired_job(database, project_id, "story_produce")
    assert reconcile_once() == {"recovered": 1, "republished": 0}
    assert reconcile_once() == {"recovered": 0, "republished": 0}
    with database() as db:
        job = db.get(Job, job_id)
        assert job.status == "failed" and job.error_code == "worker_lost"
        assert job.finished_at is not None and job.lease_expires_at is None
        assert "Periksa aset" in job.error_message and "biaya" in job.error_message
        assert "tidak diulang otomatis" in job.error_message
        assert db.get(JobAttempt, attempt_id).outcome == "worker_lost"
        assert db.get(Project, project_id).status == "ready"
        assert db.get(Project, project_id).error_message is None
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.job_id == job_id)) == 1
        with pytest.raises(Cancelled):
            JobContext(job_id, number, attempt_id).check(db)
    assert claim(job_id) is None
    # Explicit manual retry remains available after the user reviews results.
    with database() as db:
        retry_job(db, db.get(Job, job_id))
        db.commit()
        assert db.get(Job, job_id).status == "queued"
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.job_id == job_id)) == 2


@pytest.mark.parametrize("status,deleting", [("cancel_requested", False), ("running", True)])
def test_lost_story_production_honors_cancellation_and_project_deletion(database, ready_project, status, deleting):
    project_id = ready_project["project_id"]
    job_id, _, _ = expired_job(database, project_id, "story_produce", status)
    if deleting:
        with database() as db:
            db.get(Project, project_id).lifecycle_state = "deleting"
            db.commit()
    assert reconcile_once()["recovered"] == 1
    with database() as db:
        job = db.get(Job, job_id)
        assert job.status == "cancelled" and "pembatalan" in job.error_message
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.job_id == job_id)) == 1


@pytest.mark.parametrize("kind", ["story_generate", "story_render", "story_produce", "subtitle_translate"])
def test_exhausted_story_and_translation_jobs_do_not_fail_the_project(database, ready_project, monkeypatch, kind):
    monkeypatch.setattr(get_settings(), "job_max_attempts", 1)
    project_id = ready_project["project_id"]
    job_id, _, _ = expired_job(database, project_id, kind)
    reconcile_once()
    with database() as db:
        assert db.get(Job, job_id).status == "failed"
        assert db.get(Project, project_id).status == "ready"
        assert db.get(Project, project_id).error_message is None


@pytest.mark.parametrize("kind", ["transcribe", "story_render"])
def test_unrelated_lost_jobs_still_requeue_with_attempts_remaining(database, ready_project, kind):
    job_id, _, attempt_id = expired_job(database, ready_project["project_id"], kind)
    reconcile_once()
    with database() as db:
        job = db.get(Job, job_id)
        assert job.status == "queued" and job.error_code is None
        assert db.get(JobAttempt, attempt_id).outcome == "worker_lost"
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.job_id == job_id)) == 2
    assert claim(job_id)[0] == 2


def test_local_production_can_recover_automatically_without_api_billing(database, ready_project):
    job_id, _, _ = expired_job(database, ready_project['project_id'], 'story_produce')
    with database() as db:
        db.get(Job, job_id).input_json = {'provider_config': {'story_media_provider': 'local'}}
        db.commit()
    reconcile_once()
    with database() as db:
        assert db.get(Job, job_id).status == 'queued'
        assert db.get(Project, ready_project['project_id']).status == 'ready'
