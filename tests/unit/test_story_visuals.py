from pathlib import Path
import json
import httpx
import pytest
from app.config import Settings
from app.media.process import MediaError
from app.story.jobs import generate_document
from app.story.schemas import Document
from app.story.script_input import table_document, parse_storyboard
from app.story.visuals import fill_visuals


def test_coffee_story_illustrates_all_six_scenes_without_changing_timing():
    script = (Path(__file__).parents[1] / 'fixtures/story-coffee.md').read_text(encoding='utf-8')
    d = table_document(Document(script=script, scenes=[{'id':'one'}]).model_dump(), parse_storyboard(script))
    assert [s['visual']['kind'] for s in d['scenes']] == [
        'coffee_compare','coffee_flat','coffee_pair','coffee_separate','coffee_peaberry','coffee_reveal']
    assert sum(s['duration_ms'] for s in d['scenes']) == 68000
    assert d['script'] == script.strip() and d['scenes'][-1]['visual']['reveal_ms'] == 2000


def test_fill_skips_existing_visuals_and_uploads_and_targets_only_selected_scene():
    d = Document(scenes=[{'id':'one','visual':{'kind':'steps'}}, {'id':'two','asset_id':'upload'}, {'id':'three','title':'Air'}]).model_dump()
    result = fill_visuals(d)
    assert result['scenes'][:2] == d['scenes'][:2]
    assert result['scenes'][2]['visual']['items'][0]['icon'] == 'water'
    selected = fill_visuals(d, 'one')
    assert selected['scenes'][1:] == d['scenes'][1:]
    assert selected['scenes'][0]['visual']['kind'] == 'diagram'
    assert d['scenes'][2]['visual']['kind'] == 'none'


def mock_client(plan):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(plan)}}]})))


def test_ai_visuals_preserve_every_other_field_and_exclude_uploaded_media():
    d = Document(script='Naskah asli', scenes=[{'id':'one','narration':'Kopi','duration_ms':7000,'audio_id':'voice'}, {'id':'two','asset_id':'photo'}]).model_dump()
    plan = {'scenes':[{'scene_id':'one','visual':{'kind':'coffee_compare'}}]}
    with mock_client(plan) as c:
        result = generate_document(d, 'visuals', Settings(), lambda:False, lambda _:None, c)
    assert result['scenes'][0]['visual']['kind'] == 'coffee_compare'
    result['scenes'][0]['visual'] = d['scenes'][0]['visual']
    assert result == d


@pytest.mark.parametrize('plan', [
    {'scenes':[{'scene_id':'wrong','visual':{'kind':'diagram'}}]},
    {'scenes':[{'scene_id':'one','visual':{'kind':'none'}}]},
    {'scenes':[{'scene_id':'one','visual':{'kind':'diagram','url':'https://example.org'}}]},
    {'scenes':[{'scene_id':'one','visual':{'kind':'photograph'}}]},
    {'scenes':[{'scene_id':'one','visual':{'kind':'diagram'}}]*2},
])
def test_ai_rejects_incomplete_or_unsupported_visual_plans(plan):
    d = Document(scenes=[{'id':'one'}]).model_dump()
    with mock_client(plan) as c, pytest.raises(MediaError):
        generate_document(d, 'visuals', Settings(), lambda:False, lambda _:None, c)
