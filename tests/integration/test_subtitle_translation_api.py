from sqlalchemy import select
import pytest
from app.config import get_settings
from app.domain.models import Job, ClipRevision, ProviderUsage
from app.jobs.runtime import claim, JobContext
from app.jobs.clip_translation import translate_subtitles
from app.media.process import MediaError


def create(clients,ready_project,cues=None):
    response=clients[0].post(f"/api/v1/projects/{ready_project['project_id']}/clips",json={
        'start_ms':0,'end_ms':10000,'cues':cues if cues is not None else [
            {'start_ms':500,'end_ms':2500,'text':'Coffee grows inside a fruit.'},
            {'start_ms':3000,'end_ms':5000,'text':'Look at these two beans.'}]})
    assert response.status_code==201,response.text
    return response.json()


def test_translate_requires_owned_current_nonempty_clip_and_provider(clients,ready_project,monkeypatch):
    clip=create(clients,ready_project)
    url=f"/api/v1/clips/{clip['id']}/subtitles/translate"
    body={'expected_revision':1,'target_language':'id'}
    assert clients[1].post(url,json=body).status_code==404
    assert clients[0].post(url,json={**body,'expected_revision':2}).status_code==409
    assert clients[0].post(url,json=body).status_code==422
    monkeypatch.setattr(get_settings(),'deepseek_api_key','test-only')
    assert clients[0].post(url,json={**body,'target_language':'xx'}).status_code==422
    job=clients[0].post(url,json=body,headers={'Idempotency-Key':'translate'}).json()
    assert clients[0].post(url,json=body,headers={'Idempotency-Key':'translate'}).json()['id']==job['id']
    empty=create(clients,ready_project,[])
    assert clients[0].post(f"/api/v1/clips/{empty['id']}/subtitles/translate",json=body).json()['code']=='SUBTITLES_EMPTY'


def test_job_proposes_translation_without_changing_revision_then_editor_saves(clients,ready_project,database,monkeypatch,tmp_path):
    clip=create(clients,ready_project); url=f"/api/v1/clips/{clip['id']}"
    monkeypatch.setattr(get_settings(),'deepseek_api_key','test-only')
    job=clients[0].post(url+'/subtitles/translate',json={'expected_revision':1}).json()
    def translate(cues,settings,cancelled,usage,progress):
        usage({'provider':'deepseek','model':'test','outcome':'succeeded','latency_ms':1})
        return [{**c,'text':text} for c,text in zip(cues,['Kopi tumbuh di dalam buah.','Lihat dua biji ini.'])]
    monkeypatch.setattr('app.jobs.clip_translation.translate_cues',translate)
    attempt,attempt_id=claim(job['id'])
    with JobContext(job['id'],attempt,attempt_id) as ctx:
        translate_subtitles(ctx,tmp_path)
    result=clients[0].get('/api/v1/jobs/'+job['id']).json()['result_json']
    assert result['base_revision']==1 and result['translated_cues'][0]['start_ms']==500
    unchanged = clients[0].get(url).json()['revision']
    assert {k:v for k,v in unchanged.items() if k!='created_at'} == {k:v for k,v in clip['revision'].items() if k!='created_at'}
    saved=clients[0].patch(url,json={'expected_revision':1,'cues':result['translated_cues']}).json()
    assert saved['revision']['revision']==2 and saved['revision']['cues'][0]['text']=='Kopi tumbuh di dalam buah.'
    assert clients[1].get('/api/v1/jobs/'+job['id']).status_code==404
    with database() as db:
        assert db.get(ClipRevision,clip['revision']['id']) is not None
        assert db.scalar(select(ProviderUsage)).provider=='deepseek'


def test_edit_during_translation_cannot_publish_stale_result(clients,ready_project,monkeypatch,tmp_path):
    clip=create(clients,ready_project); url=f"/api/v1/clips/{clip['id']}"
    monkeypatch.setattr(get_settings(),'deepseek_api_key','test-only')
    job=clients[0].post(url+'/subtitles/translate',json={'expected_revision':1}).json()
    def translate(cues,*args):
        assert clients[0].patch(url,json={'expected_revision':1,'title':'Edit baru'}).status_code==200
        return cues
    monkeypatch.setattr('app.jobs.clip_translation.translate_cues',translate)
    attempt,attempt_id=claim(job['id'])
    with JobContext(job['id'],attempt,attempt_id) as ctx, pytest.raises(MediaError,match='sudah berubah'):
        translate_subtitles(ctx,tmp_path)
    assert clients[0].get(url).json()['revision']['title']=='Edit baru'
