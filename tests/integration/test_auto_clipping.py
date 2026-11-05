"""Automatic imports keep one durable continuation through clip creation."""
import pytest
from sqlalchemy import func, select

from app.ai.selector import SelectionResult
from app.config import get_settings
from app.domain.models import Asset, Clip, ClipRevision, Export, Job, Project, SubtitleCue
from app.jobs.tasks import run_job
from app.media.process import MediaError


URL = 'https://example.com/source.mp4?token=private-source'
OPTIONS = {'language': 'en', 'count': 2, 'content_profile': 'gaming',
           'min_duration_ms': 5000, 'max_duration_ms': 10000}


def create_project(owner):
    response = owner.post('/api/v1/projects', json={'name': 'Auto clipping'})
    assert response.status_code == 201
    return response.json()['id']


def test_auto_clip_preflight_has_no_queue_side_effects(clients, database, monkeypatch):
    owner, other = clients
    pid = create_project(owner)
    endpoint = f'/api/v1/projects/{pid}/source-url'
    body = {'url': URL, 'process': OPTIONS}
    assert other.post(endpoint, json=body).status_code == 404
    response = owner.post(endpoint, json=body)
    assert response.status_code == 422 and response.json()['code'] == 'AI_NOT_CONFIGURED'
    monkeypatch.setattr(get_settings(), 'deepseek_api_key', 'test-only')
    limits = {'max_video_seconds': 120, 'max_upload_bytes': 1024**2, 'max_clip_ms': 5000}
    assert owner.patch('/api/v1/settings', json=limits).status_code == 200
    response = owner.post(endpoint, json=body)
    assert response.status_code == 422 and response.json()['code'] == 'CLIP_DURATION'
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.get(Project, pid).source_asset_id is None
    # Ordinary imports remain available when no AI provider is configured.
    monkeypatch.setattr(get_settings(), 'deepseek_api_key', '')
    ordinary = owner.post(endpoint, json={'url': URL})
    assert ordinary.status_code == 202
    with database() as db:
        assert db.get(Job, ordinary.json()['id']).input_json == {'url': URL}


@pytest.mark.parametrize('options', [
    {'analyze': False}, {'transcribe_again': True}, {'count': 0},
    {'count': 21}, {'language': 'xx'}, {'content_profile': 'unknown'},
    {'min_duration_ms': 10000, 'max_duration_ms': 5000},
    {'visual_analysis': True}, {'unrecognized': 'option'},
])
def test_auto_clip_options_are_validated(clients, database, options):
    owner = clients[0]
    pid = create_project(owner)
    response = owner.post(f'/api/v1/projects/{pid}/source-url', json={'url': URL, 'process': options})
    assert response.status_code == 422
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0


@pytest.fixture
def media_stubs(monkeypatch):
    observed = {'downloads': 0, 'transcriptions': 0, 'selections': 0}
    monkeypatch.setattr(get_settings(), 'deepseek_api_key', 'test-only')

    def download(url, directory, **kwargs):
        observed['downloads'] += 1
        assert url == URL
        observed['import_limit'] = kwargs['settings'].max_video_seconds
        path = directory / 'imported.mp4'
        path.write_bytes(b'test-only-video')
        return {'path': path, 'title': 'Public source'}

    def prepare(*args, **kwargs):
        return {'duration_ms': 60000, 'width': 640, 'height': 360}, None

    def transcribe(*args, **kwargs):
        observed['transcriptions'] += 1
        assert kwargs['language'] == OPTIONS['language']
        return {'language': 'en', 'segments': [
            {'start_ms': 0, 'end_ms': 8000, 'text': 'A complete example with a clear ending.'},
        ]}

    def select_clips(segments, **kwargs):
        observed['selections'] += 1
        for key in ('count', 'content_profile', 'min_duration_ms', 'max_duration_ms'):
            assert kwargs[key] == OPTIONS[key]
        return SelectionResult([{'start_ms': 0, 'end_ms': 8000, 'title': 'Selected moment',
                                 'reason': 'Complete example', 'topic': 'Example'}], 2, 1)

    monkeypatch.setattr('app.jobs.tasks.download_video', download)
    monkeypatch.setattr('app.jobs.tasks.prepare_source', prepare)
    monkeypatch.setattr('app.jobs.tasks.transcribe', transcribe)
    monkeypatch.setattr('app.jobs.tasks.select_clips', select_clips)
    return observed


def next_job(owner, job_id):
    data = owner.get(f'/api/v1/jobs/{job_id}').json()
    assert data['status'] == 'succeeded', data
    return data['result_json']['next_job_id']


def test_import_chains_to_clips_once_and_preserves_original_limits(clients, database, monkeypatch, media_stubs):
    owner = clients[0]
    pid = create_project(owner)
    endpoint = f'/api/v1/projects/{pid}/source-url'
    body = {'url': URL, 'process': OPTIONS}
    monkeypatch.setattr(get_settings(), 'max_active_jobs_per_user', 1)
    response = owner.post(endpoint, json=body, headers={'Idempotency-Key': 'auto-once'})
    assert response.status_code == 202
    assert 'private-source' not in response.text
    root_id = response.json()['id']
    assert owner.post(endpoint, json=body, headers={'Idempotency-Key': 'auto-once'}).json()['id'] == root_id
    changed = {'url': URL, 'process': {**OPTIONS, 'count': 3}}
    assert owner.post(endpoint, json=changed, headers={'Idempotency-Key': 'auto-once'}).status_code == 409
    with database() as db:
        initial_limits = dict(db.get(Job, root_id).limits_json)
    assert owner.patch('/api/v1/settings', json={
        'max_video_seconds': 120, 'max_upload_bytes': 1024**2, 'max_clip_ms': 5000,
    }).status_code == 200
    run_job(root_id)
    run_job(root_id)  # Duplicate delivery cannot publish another source or child.
    transcript_id = next_job(owner, root_id)
    with database() as db:
        child = db.get(Job, transcript_id)
        assert child.kind == 'transcribe' and child.limits_json == initial_limits
    run_job(transcript_id)
    run_job(transcript_id)
    analyze_id = next_job(owner, transcript_id)
    with database() as db:
        assert db.get(Job, analyze_id).limits_json == initial_limits
    run_job(analyze_id)
    run_job(analyze_id)
    detail = owner.get(f'/api/v1/projects/{pid}').json()
    assert detail['status'] == 'ready' and detail['clip_count'] == 1
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 3
        assert db.scalar(select(func.count()).select_from(Asset)) == 1
        assert db.scalar(select(func.count()).select_from(Export)) == 0
        clip = db.scalar(select(Clip))
        revision = db.get(ClipRevision, clip.active_revision_id)
        assert revision.start_ms == 0 and revision.end_ms == 8000
        assert db.scalar(select(SubtitleCue).where(SubtitleCue.clip_revision_id == revision.id)) is not None
    assert media_stubs == {'downloads': 1, 'transcriptions': 1, 'selections': 1,
                           'import_limit': initial_limits['max_video_seconds']}
    # A replay returns the accepted job even if provider settings were removed.
    monkeypatch.setattr(get_settings(), 'deepseek_api_key', '')
    assert owner.post(endpoint, json=body, headers={'Idempotency-Key': 'auto-once'}).json()['id'] == root_id


def test_cancelled_import_does_not_start_pipeline(clients, database, media_stubs):
    owner = clients[0]
    pid = create_project(owner)
    root_id = owner.post(f'/api/v1/projects/{pid}/source-url', json={'url': URL, 'process': OPTIONS}).json()['id']
    assert owner.post(f'/api/v1/jobs/{root_id}/cancel').status_code == 202
    run_job(root_id)
    with database() as db:
        assert db.get(Project, pid).source_asset_id is None
        assert db.scalar(select(func.count()).select_from(Job)) == 1
    assert media_stubs['downloads'] == 0


@pytest.mark.parametrize('stop', ['cancel', 'failure'])
def test_resume_downstream_stage_does_not_reimport(clients, database, monkeypatch, media_stubs, stop):
    owner = clients[0]
    pid = create_project(owner)
    root_id = owner.post(f'/api/v1/projects/{pid}/source-url', json={'url': URL, 'process': OPTIONS}).json()['id']
    run_job(root_id)
    child_id = next_job(owner, root_id)
    if stop == 'cancel':
        assert owner.post(f'/api/v1/jobs/{child_id}/cancel').status_code == 202
        run_job(child_id)
    else:
        with monkeypatch.context() as patch:
            def fail(*args, **kwargs):
                raise MediaError('transcription_failed', 'Transkripsi gagal sementara.')
            patch.setattr('app.jobs.tasks.transcribe', fail)
            run_job(child_id)
    with database() as db:
        assert db.get(Job, child_id).status == ('cancelled' if stop == 'cancel' else 'failed')
        assert db.scalar(select(func.count()).select_from(Job)) == 2
    assert owner.post(f'/api/v1/jobs/{child_id}/retry').status_code == 202
    run_job(child_id)
    analyze_id = next_job(owner, child_id)
    run_job(analyze_id)
    assert media_stubs['downloads'] == 1
    assert owner.get(f'/api/v1/projects/{pid}').json()['clip_count'] == 1
