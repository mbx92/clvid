from copy import deepcopy
import json
import httpx
import pytest
from app.story.schemas import Document, Theme

def document():
    return Document(title="Cerita kopi", script="Kopi segar. Nikmati perlahan.", scenes=[{"id": "intro", "title": "Kopi segar", "narration": "Kopi segar. Nikmati perlahan."}]).model_dump()

def create(client):
    r = client.post('/api/v1/studio', json=document())
    assert r.status_code == 201, r.text
    return r.json()

def test_story_ownership_versions_and_no_source_video_required(clients):
    a, b = clients
    story = create(a)
    id = story['id']
    assert a.get('/api/v1/studio').json()['items'][0]['id'] == id
    assert a.get('/api/v1/projects').json()['total'] == 0
    assert b.get(f'/api/v1/studio/{id}').status_code == 404
    assert b.put(f'/api/v1/studio/{id}', json={'expected_version': 1, 'document': document()}).status_code == 404
    d = document(); d['title'] = 'Koreksi saya'
    assert a.put(f'/api/v1/studio/{id}', json={'expected_version': 1, 'document': d}).json()['version'] == 2
    assert a.put(f'/api/v1/studio/{id}', json={'expected_version': 1, 'document': document()}).status_code == 409
    assert a.get(f'/api/v1/studio/{id}').json()['document']['title'] == 'Koreksi saya'

def test_template_round_trip_and_owner_scope(clients):
    a, b = clients
    r = a.post('/api/v1/studio/templates', json={'name': 'Kopi', 'theme': Theme(accent='#AA4411').model_dump()})
    assert r.status_code == 201
    id = r.json()['id']
    assert any(t['id'] == id for t in a.get('/api/v1/studio/templates').json()['items'])
    assert all(t['id'] != id for t in b.get('/api/v1/studio/templates').json()['items'])
    assert b.delete(f'/api/v1/studio/templates/{id}').status_code == 404
    assert a.delete(f'/api/v1/studio/templates/{id}').status_code == 204

@pytest.mark.parametrize('change', [
    lambda d: d['theme'].update(background='url(https://example.org)'),
    lambda d: d['scenes'][0].update(duration_ms=1234),
    lambda d: d['scenes'].append(deepcopy(d['scenes'][0])),
    lambda d: d['scenes'][0].update(asset_id='not-owned'),
    lambda d: d.update(scenes=[{**d['scenes'][0], 'id': str(i), 'duration_ms': 30000} for i in range(7)]),
])
def test_invalid_story_is_rejected(clients, change):
    d = document(); change(d)
    assert clients[0].post('/api/v1/studio', json=d).status_code == 422

def test_render_snapshot_idempotency_and_cross_account_assets(clients, database):
    from app.domain.models import Asset, Job
    a, b = clients
    story, other = create(a), create(b)
    with database() as db:
        asset = Asset(project_id=other['id'], kind='story_media', storage_key='other.png', mime='image/png', state='ready', meta_json={'story_kind': 'image'})
        db.add(asset); db.commit(); asset_id = asset.id
    d = document(); d['scenes'][0]['asset_id'] = asset_id
    assert a.put(f"/api/v1/studio/{story['id']}", json={'expected_version':1,'document':d}).status_code == 422
    url = f"/api/v1/studio/{story['id']}/render"
    r = a.post(url, json={'expected_version':1}, headers={'Idempotency-Key': 'story-test'})
    assert r.status_code == 202, r.text
    assert a.post(url, json={'expected_version':1}, headers={'Idempotency-Key': 'story-test'}).json()['id'] == r.json()['id']
    d = document(); d['scenes'][0]['title'] = 'Versi berikutnya'
    a.put(f"/api/v1/studio/{story['id']}", json={'expected_version':1,'document':d})
    with database() as db:
        assert db.get(Job, r.json()['id']).input_json['document']['scenes'][0]['title'] == 'Kopi segar'
    assert b.post(url, json={'expected_version':1}).status_code == 404

def test_ai_is_optional_and_does_not_overwrite_saved_document(clients, database, monkeypatch, tmp_path):
    from app.config import get_settings
    from app.domain.models import Job, Storyboard
    from app.jobs.runtime import claim, JobContext
    from app.story.jobs import generate
    a = clients[0]; story = create(a)
    url = f"/api/v1/studio/{story['id']}/generate"
    assert a.post(url, json={'expected_version':1}).status_code == 422
    monkeypatch.setattr(get_settings(), 'deepseek_api_key', 'test-only')
    r = a.post(url, json={'expected_version':1})
    assert r.status_code == 202
    result = document(); result['scenes'][0]['title'] = 'Usulan AI'
    monkeypatch.setattr('app.story.jobs.generate_document', lambda *args, **kwargs: result)
    job_id = r.json()['id']; attempt, attempt_id = claim(job_id)
    with JobContext(job_id, attempt, attempt_id) as ctx:
        generate(ctx, tmp_path)
    with database() as db:
        assert db.get(Storyboard, story['id']).document_json['scenes'][0]['title'] == 'Kopi segar'
        assert db.get(Job, job_id).result_json['document']['scenes'][0]['title'] == 'Usulan AI'

def test_ai_preserves_script_and_style_only_keeps_scenes():
    from app.story.jobs import generate_document
    from app.config import Settings
    from app.media.process import MediaError
    d = document()
    def client(content):
        return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(content)}}], 'usage':{'prompt_tokens':5,'completion_tokens':10}})))
    reports = []
    with client(Theme(accent='#FFCC00').model_dump()) as c:
        r = generate_document(d, 'style', Settings(), lambda: False, reports.append, c)
        assert r['scenes'] == d['scenes'] and r['theme']['accent'] == '#FFCC00'
    wrong = deepcopy(d); wrong['scenes'][0]['narration'] = 'Berubah'
    with client(wrong) as c, pytest.raises(MediaError, match='AI mengubah naskah'):
        generate_document(d, 'storyboard', Settings(), lambda: False, reports.append, c)
    with client(d) as c:
        result = generate_document(d, 'storyboard', Settings(), lambda: False, reports.append, c)
        assert result['scenes'][0]['visual']['kind'] == 'diagram'
        result['scenes'][0]['visual'] = d['scenes'][0]['visual']
        assert result == d
    assert reports[-1]['outcome'] == 'succeeded'

def test_upload_rejects_invalid_file_and_foreign_project(clients):
    story = create(clients[0])
    path = f"/api/v1/studio/{story['id']}/assets"
    assert clients[1].post(path, params={'filename':'test.png'}, content=b'not an image').status_code == 404
    assert clients[0].post(path, params={'filename':'test.svg'}, content=b'<svg/>').status_code == 422


def test_visual_proposal_is_owned_versioned_and_requires_apply_before_save(clients, monkeypatch):
    a, b = clients
    story = create(a)
    path = f"/api/v1/studio/{story['id']}"
    body = {'expected_version':1, 'scene_id':'intro'}
    assert b.post(path+'/visuals', json=body).status_code == 404
    assert a.post(path+'/visuals', json={**body,'expected_version':99}).status_code == 409
    assert a.post(path+'/visuals', json={**body,'scene_id':'missing'}).status_code == 422
    proposal = a.post(path+'/visuals', json=body).json()
    assert proposal['mode'] == 'visuals' and proposal['base_version'] == 1
    assert proposal['document']['scenes'][0]['visual']['kind'] == 'diagram'
    assert a.get(path).json()['document']['scenes'][0]['visual']['kind'] == 'none'
    assert a.put(path,json={'expected_version':1,'document':proposal['document']}).status_code == 200
    assert a.get(path).json()['document']['scenes'][0]['visual']['kind'] == 'diagram'
    monkeypatch.setattr(__import__('app.config',fromlist=['get_settings']).get_settings(), 'deepseek_api_key','test-only')
    assert a.post(path+'/generate',json={'expected_version':2,'mode':'visuals','scene_id':'intro'}).status_code == 202

def test_upload_persists_owned_normalized_asset(clients, monkeypatch):
    story = create(clients[0])
    def normalize(path, suffix, settings):
        assert path.read_bytes() == b'fixture image'
        output = path.with_suffix('.png'); output.write_bytes(b'normalized image')
        return output, 'image/png', {'story_kind':'image','duration_ms':0}
    monkeypatch.setattr('app.story.media.normalize_upload', normalize)
    r = clients[0].post(f"/api/v1/studio/{story['id']}/assets", params={'filename':'foto.jpg'}, content=b'fixture image')
    assert r.status_code == 201, r.text
    assert r.json()['metadata']['filename'] == 'foto.jpg'
    assert clients[0].get(r.json()['content_url']).content == b'normalized image'
    assert clients[1].get(r.json()['content_url']).status_code == 404
    d = document(); d['scenes'][0]['asset_id'] = r.json()['id']
    assert clients[0].put(f"/api/v1/studio/{story['id']}", json={'expected_version':1,'document':d}).status_code == 200

def test_render_handler_publishes_video_and_subtitle_assets(clients, database, monkeypatch):
    from app.jobs.runtime import claim, JobContext
    from app.story.jobs import render
    from app.domain.models import Job, Asset
    from app.storage.local import LocalStorage
    story = create(clients[0])
    job = clients[0].post(f"/api/v1/studio/{story['id']}/render", json={'expected_version':1}).json()
    scratch = LocalStorage().path(f"scratch/{job['id']}/1"); scratch.mkdir(parents=True)
    def fake_render(document, assets, directory, settings, ctx):
        mp4, srt = directory / 'story.mp4', directory / 'story.srt'
        mp4.write_bytes(b'rendered'); srt.write_text('subtitle')
        return mp4, srt, {'duration_ms':5000,'width':720,'height':1280}
    monkeypatch.setattr('app.story.media.render_story', fake_render)
    attempt, attempt_id = claim(job['id'])
    with JobContext(job['id'],attempt,attempt_id) as ctx:
        render(ctx,scratch)
    with database() as db:
        result = db.get(Job,job['id'])
        assert result.status == 'succeeded' and result.result_json['version'] == 1
        assert db.get(Asset,result.result_json['mp4_asset_id']).state == 'ready'
        assert db.get(Asset,result.result_json['srt_asset_id']).mime == 'application/x-subrip'
