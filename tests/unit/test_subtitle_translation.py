import json
import httpx
import pytest
from app.ai.translate_subtitles import translate_cues
from app.config import Settings
from app.media.process import MediaError, Cancelled


def settings():
    return Settings(deepseek_api_key='test-only')


def test_translation_batches_keep_timestamps_and_restore_out_of_order_ids():
    cues = [{'start_ms':i*1200,'end_ms':i*1200+900,'text':f'English {i}'} for i in range(30)]
    calls, reports = [], []
    def respond(request):
        data = json.loads(request.content)
        batch = json.loads(data['messages'][1]['content'])['cues']; calls.append(batch)
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'translations':[
            {'id':c['id'],'text':f"Indonesia {c['id']}"} for c in reversed(batch)]})}}], 'usage':{'prompt_tokens':10,'completion_tokens':20}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = translate_cues(cues,settings(),lambda:False,reports.append,client=client)
    assert [len(c) for c in calls] == [24,6]
    assert [(c['start_ms'],c['end_ms']) for c in result] == [(c['start_ms'],c['end_ms']) for c in cues]
    assert [c['text'] for c in result] == [f'Indonesia {i}' for i in range(30)]
    assert cues[0]['text'] == 'English 0' and all(r['outcome']=='succeeded' for r in reports)


@pytest.mark.parametrize('translated', [[],[{'id':1,'text':'Salah'}],[{'id':0,'text':''}],
    [{'id':0,'text':'A'},{'id':0,'text':'B'}], [{'id':0,'text':'Halo','start_ms':5}], [{'id':0,'text':'x'*2001}]])
def test_invalid_ai_results_cannot_drop_add_or_retime_cues(translated):
    response = {'choices':[{'message':{'content':json.dumps({'translations':translated})}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response))) as client:
        with pytest.raises(MediaError,match='tidak lengkap atau tidak valid'):
            translate_cues([{'start_ms':0,'end_ms':1000,'text':'Hello'}],settings(),lambda:False,lambda _:None,client=client)


def test_cancelled_translation_does_not_call_provider():
    with httpx.Client(transport=httpx.MockTransport(lambda _:pytest.fail('Provider called after cancel'))) as client:
        with pytest.raises(Cancelled):
            translate_cues([{'start_ms':0,'end_ms':1000,'text':'Hello'}],settings(),lambda:True,lambda _:None,client=client)


def test_provider_timeout_leaves_no_result():
    def timeout(request):
        raise httpx.ReadTimeout('timeout',request=request)
    reports=[]
    with httpx.Client(transport=httpx.MockTransport(timeout)) as client, pytest.raises(MediaError,match='terputus'):
        translate_cues([{'start_ms':0,'end_ms':1000,'text':'Hello'}],settings(),lambda:False,reports.append,client=client)
    assert reports[0]['outcome']=='failed'
