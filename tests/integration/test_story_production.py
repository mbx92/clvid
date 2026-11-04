from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.domain.models import Asset, Job, Storyboard
from app.jobs.runtime import JobContext, claim
from app.media.process import MediaError
from app.storage.local import LocalStorage
from app.story.production import produce, plan
from app.story.schemas import Document


def create(client, scenes=None):
    doc = Document(title='Produksi', scenes=scenes or [{'id':'s1', 'title':'Kopi', 'narration':'Ini kopi segar.', 'duration_ms':1000}]).model_dump()
    response = client.post('/api/v1/studio', json=doc)
    assert response.status_code == 201, response.text
    return response.json()


def request(client, story, **kwargs):
    return client.post(f"/api/v1/studio/{story['id']}/produce", json={'expected_version':story['version'], **kwargs})


def run(job_id):
    attempt, attempt_id = claim(job_id)
    scratch = LocalStorage().prepare(f'scratch/{job_id}/run-{attempt}/placeholder').parent
    with JobContext(job_id, attempt, attempt_id) as ctx:
        produce(ctx, scratch)


@pytest.fixture
def providers(monkeypatch):
    monkeypatch.setattr(get_settings(), 'story_media_provider', 'openai')
    monkeypatch.setattr(get_settings(), 'openai_api_key', 'fake-test-key')
    calls = []
    def image(scene, doc, path, settings, cancelled):
        calls.append(('image',scene['id'])); path.write_bytes(b'image'); return {'provider':'test','usage':{}}
    def speech(scene, voice, path, settings, cancelled):
        calls.append(('speech',scene['id'])); path.write_bytes(b'audio'); return {'provider':'test','usage':{}}
    def normalize(path, suffix, settings):
        kind = 'image' if suffix == '.png' else 'audio'
        output = path.with_suffix('.png' if kind == 'image' else '.m4a')
        output.write_bytes(path.read_bytes())
        return output, 'image/png' if kind == 'image' else 'audio/mp4', {'story_kind':kind,'duration_ms':0 if kind == 'image' else 2345}
    def align(source, scratch, **kwargs):
        calls.append(('align', source.name))
        return {'narration':kwargs['narration'] or 'Ini kopi segar.', 'captions':[{'start_ms':200,'end_ms':2300,'text':'Ini kopi segar.'}], 'warnings':[]}
    monkeypatch.setattr('app.story.providers.generate_image', image)
    monkeypatch.setattr('app.story.providers.generate_speech', speech)
    monkeypatch.setattr('app.story.media.normalize_upload', normalize)
    monkeypatch.setattr('app.story.alignment.align_audio', align)
    return calls


def test_produce_preflight_ownership_configuration_validation(clients):
    a,b = clients
    story = create(a)
    assert story['capabilities']['alignment'] is True
    assert story['capabilities']['images'] is False
    assert request(b, story).status_code == 404
    assert request(a, story).json()['code'] == 'STORY_PROVIDER_NOT_CONFIGURED'
    assert request(a, story, scene_id='missing').status_code == 422
    assert request(a, story, replace_existing=True).status_code == 422
    assert request(a, {**story,'version':99}).status_code == 409
    assert request(a, story, mode='captions').status_code == 422


def test_full_production_checkpoint_assets_proposal_and_audio_duration(clients, database, providers):
    a = clients[0]; story = create(a)
    response = request(a, story)
    assert response.status_code == 202, response.text
    job_id = response.json()['id']
    assert request(a, story).json()['id'] == job_id
    assert request(a, story, mode='speech').status_code == 409
    run(job_id)
    with database() as db:
        job = db.get(Job, job_id)
        result = job.result_json
        scene = result['document']['scenes'][0]
        assert job.status == 'succeeded'
        assert scene['duration_ms'] == 2400
        assert scene['caption_audio_id'] == scene['audio_id']
        assert scene['captions'][-1]['end_ms'] == 2300
        assert result['base_version'] == 1 and result['warnings']
        assert db.get(Storyboard, story['id']).document_json == story['document']
        assert len(list(db.scalars(select(Asset).where(Asset.project_id == story['id'])))) == 2
        assert db.get(Asset, scene['audio_id']).meta_json['ai_generated_voice'] is True
    response = a.put(f"/api/v1/studio/{story['id']}", json={'expected_version':1, 'document':result['document']})
    assert response.status_code == 200, response.text
    assert request(a, response.json(), mode='images').status_code == 422
    assert providers[:2] == [('image','s1'),('speech','s1')]


def test_retry_reuses_successful_provider_assets(clients, database, providers, monkeypatch):
    story = create(clients[0]); job_id = request(clients[0], story).json()['id']
    original = __import__('app.story.alignment', fromlist=['align_audio']).align_audio
    def fail(*args, **kwargs):
        raise MediaError('test_failure', 'ASR temporarily unavailable')
    monkeypatch.setattr('app.story.alignment.align_audio', fail)
    with pytest.raises(MediaError):
        run(job_id)
    with database() as db:
        job = db.get(Job, job_id); job.status = 'queued'; db.commit()
    monkeypatch.setattr('app.story.alignment.align_audio', original)
    run(job_id)
    assert len([c for c in providers if c[0] == 'image']) == 1
    assert len([c for c in providers if c[0] == 'speech']) == 1
    with database() as db:
        assert db.get(Job, job_id).status == 'succeeded'


def test_normalization_retry_reuses_raw_response_and_snapshot_model(clients, database, providers, monkeypatch):
    story = create(clients[0]); job_id = request(clients[0], story, mode='images').json()['id']
    original = __import__('app.story.media', fromlist=['normalize_upload']).normalize_upload
    def fail(*args, **kwargs):
        raise MediaError('normalize_failed', 'retry normalization')
    monkeypatch.setattr('app.story.media.normalize_upload', fail)
    with pytest.raises(MediaError):
        run(job_id)
    with database() as db:
        assert db.scalar(select(Asset).where(Asset.kind == 'story_raw')).state == 'pending'
        job = db.get(Job, job_id); job.status = 'queued'; db.commit()
    monkeypatch.setattr(get_settings(), 'story_image_model', 'different-model-after-queue')
    monkeypatch.setattr('app.story.media.normalize_upload', original)
    run(job_id)
    assert providers == [('image','s1')]
    with database() as db:
        assert db.scalar(select(Asset).where(Asset.kind == 'story_raw')) is None
        assert db.scalar(select(Asset)).meta_json['model'] != 'different-model-after-queue'


def test_edit_during_provider_retains_asset_but_never_applies_old_proposal(clients, database, providers, monkeypatch):
    a = clients[0]; story = create(a); job_id = request(a, story, mode='images').json()['id']
    original = __import__('app.story.providers', fromlist=['generate_image']).generate_image
    def generate(*args, **kwargs):
        result = original(*args, **kwargs)
        doc = deepcopy(story['document']); doc['title'] = 'User edit during image generation'
        assert a.put(f"/api/v1/studio/{story['id']}", json={'expected_version':1,'document':doc}).status_code == 200
        return result
    monkeypatch.setattr('app.story.providers.generate_image', generate)
    with pytest.raises(MediaError, match='sudah berubah'):
        run(job_id)
    with database() as db:
        assert db.scalar(select(Asset)).state == 'ready'
        assert db.get(Storyboard, story['id']).document_json['title'] == 'User edit during image generation'
        assert not db.get(Job, job_id).result_json


def test_stale_snapshot_is_rejected_before_paid_call(clients, providers):
    a = clients[0]; story = create(a); job_id = request(a, story).json()['id']
    doc = deepcopy(story['document']); doc['title'] = 'Berubah'
    assert a.put(f"/api/v1/studio/{story['id']}", json={'expected_version':1,'document':doc}).status_code == 200
    with pytest.raises(MediaError, match='sudah berubah'):
        run(job_id)
    assert providers == []


def test_existing_assets_kept_unless_selected_for_replacement():
    doc = {'scenes':[{'id':'s1','asset_id':'image','audio_id':'voice','narration':'Hello.'}]}
    assert plan(doc, 'complete') == [('s1',False,False,True)]
    assert plan(doc, 'images') == []
    assert plan(doc, 'speech') == []
    assert plan(doc, 'images', 's1', True) == [('s1',True,False,False)]
    doc['scenes'][0].update(asset_id=None, visual={'kind':'coffee_compare'})
    assert plan(doc, 'complete') == [('s1',False,False,True)]
    assert plan(doc, 'images') == [('s1',True,False,False)]


def test_audio_over_scene_limit_is_not_silently_trimmed(clients, database, providers, monkeypatch):
    story = create(clients[0]); job_id = request(clients[0], story, mode='speech').json()['id']
    original = __import__('app.story.media', fromlist=['normalize_upload']).normalize_upload
    def too_long(*args):
        path, mime, meta = original(*args)
        return path, mime, {**meta,'duration_ms':31000}
    monkeypatch.setattr('app.story.media.normalize_upload', too_long)
    with pytest.raises(MediaError, match='melebihi 30 detik'):
        run(job_id)
    with database() as db:
        assert len(list(db.scalars(select(Asset).where(Asset.project_id == story['id'])))) == 1
        assert db.get(Storyboard, story['id']).document_json['scenes'][0]['audio_id'] is None


def test_spoken_number_alignment_keeps_original_script_and_invalidates_on_edit(clients, database, providers, monkeypatch):
    story = create(clients[0], [{'id':'s1','title':'Kopi','narration':'Ini 2 biji kopi.','duration_ms':3000}])
    def speech(scene, voice, path, settings, cancelled):
        path.write_bytes(b'audio')
        return {'provider':'local','spoken_text':'Ini dua biji kopi.','usage':{}}
    aligned_text = []
    def align(source, scratch, **kwargs):
        aligned_text.append(kwargs['narration'])
        return {'narration':kwargs['narration'], 'captions':[{'start_ms':200,'end_ms':2300,'text':kwargs['narration']}], 'warnings':[]}
    monkeypatch.setattr('app.story.providers.generate_speech', speech)
    monkeypatch.setattr('app.story.alignment.align_audio', align)
    job_id = request(clients[0], story, mode='speech').json()['id']; run(job_id)
    with database() as db:
        result = db.get(Job, job_id).result_json
    scene = result['document']['scenes'][0]
    assert scene['narration'] == scene['caption_narration'] == 'Ini 2 biji kopi.'
    assert scene['captions'][0]['text'] == 'Ini dua biji kopi.' and result['warnings']
    scene['narration'] = 'Ini 3 biji kopi.'
    response = clients[0].put(f"/api/v1/studio/{story['id']}", json={'expected_version':1, 'document':result['document']})
    assert response.status_code == 200
    # Synchronizing owned audio needs no image/speech models or API key.
    monkeypatch.setattr(get_settings(), 'story_media_provider', 'local')
    monkeypatch.setattr(get_settings(), 'story_local_enabled', False)
    job_id = request(clients[0], response.json(), mode='captions').json()['id']; run(job_id)
    assert aligned_text == ['Ini dua biji kopi.','Ini 3 biji kopi.']
