from sqlalchemy import select

from app.domain.models import Asset, Job, Project


def test_url_import_ownership_dedupe_and_source_exclusion(clients, database):
    owner, other = clients
    pid = owner.post('/api/v1/projects', json={'name': 'URL import'}).json()['id']
    endpoint = f'/api/v1/projects/{pid}/source-url'
    body = {'url': 'https://example.com/video.mp4?token=signed'}
    assert other.post(endpoint, json=body).status_code == 404
    assert owner.post(endpoint, json={'url': 'http://127.0.0.1/video.mp4'}).status_code == 422
    result = owner.post(endpoint, json=body, headers={'Idempotency-Key': 'url-once'})
    assert result.status_code == 202, result.text
    job = result.json()
    assert job['kind'] == 'import_url' and 'signed' not in result.text
    assert owner.post(endpoint, json=body, headers={'Idempotency-Key': 'url-once'}).json()['id'] == job['id']
    assert owner.post(endpoint, json={'url': 'https://example.com/other.mp4'}, headers={'Idempotency-Key': 'url-once'}).status_code == 409
    assert owner.post(endpoint, json={'url': 'https://example.com/other.mp4'}).status_code == 409
    assert owner.post(f'/api/v1/projects/{pid}/source', content=b'video').status_code == 409
    assert owner.post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 202
    assert owner.get(f'/api/v1/projects/{pid}').json()['status'] == 'empty'
    assert owner.post(f"/api/v1/jobs/{job['id']}/retry").status_code == 202
    assert owner.get(f'/api/v1/projects/{pid}').json()['status'] == 'importing'
    with database() as db:
        row = db.get(Job, job['id'])
        row.status = 'failed'
        project = db.get(Project, pid)
        source = Asset(project_id=pid, kind='source', storage_key=f'projects/{pid}/source.mp4', state='ready', mime='video/mp4')
        db.add(source)
        db.flush()
        project.source_asset_id = source.id
        db.commit()
    assert owner.post(f"/api/v1/jobs/{job['id']}/retry").status_code == 409
    assert owner.post(endpoint, json={'url': 'https://example.com/new.mp4'}).status_code == 409


def test_failed_import_has_no_source_and_cleans_partial_files(clients, database, monkeypatch):
    from app.jobs.tasks import run_job
    from app.media.process import MediaError
    from app.storage.local import LocalStorage
    pid = clients[0].post('/api/v1/projects', json={'name': 'Failed import'}).json()['id']
    job = clients[0].post(f'/api/v1/projects/{pid}/source-url', json={'url': 'https://example.com/video.mp4'}).json()

    def failed(url, directory, **kwargs):
        (directory / 'source.mp4.part').write_bytes(b'partial')
        raise MediaError('url_download_failed', 'Video tidak tersedia.')

    monkeypatch.setattr('app.jobs.tasks.download_video', failed)
    run_job(job['id'])
    detail = clients[0].get(f'/api/v1/projects/{pid}').json()
    assert detail['source_asset'] is None
    assert detail['status'] == 'failed'
    assert not list(LocalStorage().root.rglob('*.part'))
    assert clients[0].get(f"/api/v1/jobs/{job['id']}").json()['error_code'] == 'url_download_failed'


def test_import_server_failure_reaches_project_and_job_without_limit_advice(clients, database, monkeypatch):
    from app.jobs.tasks import run_job
    from app.media.import_errors import public_import_error
    owner = clients[0]
    pid = owner.post('/api/v1/projects', json={'name': 'Server error message'}).json()['id']
    job = owner.post(f'/api/v1/projects/{pid}/source-url', json={'url': 'https://example.com/video.mp4'}).json()
    def failed(*args, **kwargs):
        raise public_import_error(RuntimeError('private provider URL?token=secret'), phase='merge')
    monkeypatch.setattr('app.jobs.tasks.download_video', failed)
    run_job(job['id'])
    result = owner.get(f"/api/v1/jobs/{job['id']}").json()
    detail = owner.get(f'/api/v1/projects/{pid}').json()
    assert result['error_code'] == 'import_merge_failed'
    assert 'gagal digabungkan' in result['error_message']
    assert detail['error_message'] == result['error_message']
    assert 'batas' not in result['error_message'] and 'secret' not in result['error_message']
