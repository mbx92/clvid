import pytest
from app.domain.models import Asset, Job
from app.jobs.runtime import JobContext
from app.config import get_settings
from app.jobs.service import retry_job, JobConflict


def limits(**updates):
    return {"max_video_seconds": 7200, "max_upload_bytes": 4 * 1024**3, "max_clip_ms": 300000, **updates}


def test_limits_persist_are_private_and_jobs_keep_snapshot(clients, database, ready_project):
    owner, other = clients
    before = other.get('/api/v1/settings').json()
    response = owner.patch('/api/v1/settings', json=limits())
    assert response.status_code == 200
    assert owner.get('/api/v1/settings').json()['max_video_seconds'] == 7200
    assert other.get('/api/v1/settings').json()['max_video_seconds'] == before['max_video_seconds']
    with database() as db:
        db.get(Asset, ready_project['asset_id']).meta_json = {"duration_ms": 800000, "width": 640, "height": 360}
        db.commit()
    clip = owner.post(f"/api/v1/projects/{ready_project['project_id']}/clips", json={"start_ms": 0, "end_ms": 240000}).json()
    assert clip['limits']['max_clip_ms'] == 300000
    created = owner.post(f"/api/v1/clips/{clip['id']}/exports", json={"revision": 1, "resolution": 720})
    assert created.status_code == 202
    jid = created.json()['id']
    owner.patch('/api/v1/settings', json=limits(max_video_seconds=3600, max_upload_bytes=2*1024**3, max_clip_ms=60000))
    with database() as db:
        job = db.get(Job, jid)
        assert job.limits_json == limits()
    context = JobContext(jid, 1, 'not-started')
    assert context.settings.max_video_seconds == 7200 and context.settings.max_upload_bytes == 4*1024**3
    # Lower limits apply to new clips, not existing saved work or title-only edits.
    assert owner.post(f"/api/v1/projects/{ready_project['project_id']}/clips", json={"start_ms": 0, "end_ms": 240000}).status_code == 422
    edit = owner.patch(f"/api/v1/clips/{clip['id']}", json={"expected_revision": 1, "title": "Tetap tersimpan"})
    assert edit.status_code == 200 and edit.json()['revision']['end_ms'] == 240000


@pytest.mark.parametrize('change', [dict(max_clip_ms=600001), dict(max_video_seconds=43201),
    dict(max_upload_bytes=64*1024**3+1), dict(max_clip_ms=4999), dict(max_video_seconds=60, max_clip_ms=61000),
    dict(max_upload_bytes=True), dict(max_video_seconds='7200'), dict(secret='not-allowed')])
def test_settings_validation_is_atomic(clients, change):
    owner = clients[0]
    before = owner.get('/api/v1/settings').json()
    assert owner.patch('/api/v1/settings', json=limits(**change)).status_code == 422
    assert owner.get('/api/v1/settings').json()['max_video_seconds'] == before['max_video_seconds']


def test_settings_require_csrf_and_apply_to_upload_and_candidate_bounds(clients, database, ready_project):
    owner = clients[0]
    token = owner.headers.pop('X-CSRF-Token')
    assert owner.patch('/api/v1/settings', json=limits()).status_code == 403
    owner.headers['X-CSRF-Token'] = token
    assert owner.patch('/api/v1/settings', json=limits(max_upload_bytes=1024**2, max_clip_ms=10000)).status_code == 200
    project = owner.post('/api/v1/projects', json={'name': 'Upload limit'}).json()
    assert owner.post(f"/api/v1/projects/{project['id']}/source", content=b'x'*(1024**2+1), headers={'X-Filename':'large.mp4'}).status_code == 413
    assert owner.post(f"/api/v1/projects/{ready_project['project_id']}/process", json={'min_duration_ms':5000,'max_duration_ms':11000}).status_code == 422
    imported = owner.post(f"/api/v1/projects/{project['id']}/source-url", json={'url':'https://www.youtube.com/watch?v=test-limits'})
    assert imported.status_code == 202
    with database() as db:
        job = db.get(Job, imported.json()['id'])
        assert job.limits_json['max_upload_bytes'] == 1024**2


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('error,key', [('duration_limit','max_video_seconds'),
    ('upload_too_large','max_upload_bytes'), ('file_too_large','max_upload_bytes')])
def test_corrected_limit_allows_one_retry_after_exhaustion(clients, database, legacy, error, key):
    owner, other = clients
    project = owner.post('/api/v1/projects', json={'name':'Recover import'}).json()
    job_id = owner.post(f"/api/v1/projects/{project['id']}/source-url",
                        json={'url':'https://www.youtube.com/watch?v=retry-limit'}).json()['id']
    cap = get_settings().job_max_attempts
    with database() as db:
        job = db.get(Job, job_id)
        job.status, job.attempt, job.error_code = 'failed', cap, error
        if legacy:
            job.limits_json = {}
        db.commit()
    assert owner.post(f'/api/v1/jobs/{job_id}/retry').status_code == 409
    assert owner.patch('/api/v1/settings', json=limits()).status_code == 200
    assert other.post(f'/api/v1/jobs/{job_id}/retry').status_code == 404
    response = owner.post(f'/api/v1/jobs/{job_id}/retry', headers={'Idempotency-Key':'corrected-limit'})
    assert response.status_code == 202
    assert response.json()['status'] == 'queued'
    assert owner.post(f'/api/v1/jobs/{job_id}/retry', headers={'Idempotency-Key':'corrected-limit'}).status_code == 202
    with database() as db:
        job = db.get(Job, job_id)
        assert job.attempt == cap  # Never reset or reuse historical attempt numbers.
        assert job.limits_json == limits()
        job.status, job.attempt, job.error_code = 'failed', cap+1, error
        db.commit()
    assert owner.post(f'/api/v1/jobs/{job_id}/retry').status_code == 409
    # Altering an unrelated limit does not unlock another attempt.
    changed = limits(max_clip_ms=400000)
    assert owner.patch('/api/v1/settings', json=changed).status_code == 200
    assert owner.post(f'/api/v1/jobs/{job_id}/retry').status_code == 409
    changed[key] *= 2
    assert owner.patch('/api/v1/settings', json=changed).status_code == 200
    with database() as db:
        job = retry_job(db, db.get(Job, job_id))
        assert job.status == 'queued' and job.attempt == cap+1
        assert job.limits_json == changed
        db.commit()


def test_increased_limits_do_not_unlock_unrelated_failure(clients, database):
    owner = clients[0]
    project = owner.post('/api/v1/projects', json={'name':'Network failure'}).json()
    job_id = owner.post(f"/api/v1/projects/{project['id']}/source-url",
                        json={'url':'https://www.youtube.com/watch?v=retry-network'}).json()['id']
    with database() as db:
        job = db.get(Job, job_id)
        job.status, job.attempt, job.error_code = 'failed', get_settings().job_max_attempts, 'download_failed'
        db.commit()
    assert owner.patch('/api/v1/settings', json=limits()).status_code == 200
    assert owner.post(f'/api/v1/jobs/{job_id}/retry').status_code == 409
    with database() as db:
        with pytest.raises(JobConflict, match='Batas percobaan'):
            retry_job(db, db.get(Job, job_id))
