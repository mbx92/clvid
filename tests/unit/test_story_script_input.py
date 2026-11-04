import json
import re
from pathlib import Path
import httpx
import pytest
from app.config import Settings
from app.media.process import MediaError
from app.story.jobs import generate_document
from app.story.schemas import Document
from app.story.script_input import parse_storyboard, table_document, cells

SCRIPT = (Path(__file__).parents[1] / 'fixtures/story-coffee.md').read_text(encoding='utf-8')

def document():
    return Document(script=SCRIPT, scenes=[{'id':'initial','title':'Draft saya'}]).model_dump()

def test_coffee_table_preserves_six_scenes_68_seconds_and_references():
    parsed = parse_storyboard(SCRIPT)
    result = table_document(document(), parsed)
    assert result['title'] == 'Mana Biji Kopi yang Tumbuh Sendirian?'
    assert result['aspect'] == 'portrait'
    assert [s['duration_ms'] for s in result['scenes']] == [7000,11000,11000,11000,15000,13000]
    assert sum(s['duration_ms'] for s in result['scenes']) == 68000
    assert result['scenes'][0]['narration'] == 'Salah satu biji kopi ini tumbuh sendirian di dalam buahnya. Coba tebak, yang A atau yang B?'
    assert 'https://' not in ' '.join(s['narration'] for s in result['scenes'])
    assert 'ctahr.hawaii.edu' in result['script'] and 'ugm.ac.id' in result['script']
    assert 'Nama lainnya peaberry.' in result['scenes'][4]['narration']
    assert 'Yang B.' in result['scenes'][5]['narration']
    assert 'jeda dua detik' in result['scenes'][5]['visual_note']

def test_table_ai_receives_separate_fields_and_cannot_change_authoritative_rows():
    original = document()
    proposed = table_document(original, parse_storyboard(SCRIPT))
    for s in proposed['scenes']:
        s.update(title='Judul singkat AI', narration='Narasi diubah AI', duration_ms=5000, visual_note='Diubah')
    def respond(request):
        payload = json.loads(json.loads(request.content)['messages'][1]['content'])
        assert len(payload['storyboard_rows']) == 6
        assert 'ctahr.hawaii.edu' not in payload['script']
        return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(proposed)}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = generate_document(original, 'storyboard', Settings(), lambda: False, lambda _: None, client)
    expected = parse_storyboard(SCRIPT)['scenes']
    assert result['script'] == original['script']
    for source, scene in zip(expected,result['scenes']):
        assert scene['title'] == 'Judul singkat AI'
        for key in ('narration','duration_ms','visual_note'):
            assert scene[key] == source[key]

@pytest.mark.parametrize('replacement', ['07–19','19–29','18–50','29–18'])
def test_malformed_table_times_are_not_silently_ignored(replacement):
    with pytest.raises(MediaError, match='Periksa baris'):
        parse_storyboard(SCRIPT.replace('18–29', replacement))

def test_prose_unchanged_and_clock_format_accepted():
    assert parse_storyboard('Narasi biasa tanpa tabel.') is None
    assert parse_storyboard(SCRIPT.replace('00–07', '00:00-00:07'))['scenes'][0]['duration_ms'] == 7000

def test_browser_clipboard_tab_separated_table_with_plain_source_labels():
    lines = []
    for line in SCRIPT.splitlines():
        if line.startswith('| ---'):
            continue
        line = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', line)
        line = line.replace('*','').lstrip('# ')
        lines.append('\t'.join(cells(line)) if '|' in line else line)
    clipboard = '\n'.join(lines)
    parsed = parse_storyboard(clipboard)
    assert parsed['title'] == 'Mana Biji Kopi yang Tumbuh Sendirian?'
    assert len(parsed['scenes']) == 6 and sum(s['duration_ms'] for s in parsed['scenes']) == 68000
    narration = ' '.join(s['narration'] for s in parsed['scenes'])
    assert 'ctahr' not in narration and 'Universitas' not in narration
    assert 'ctahr.hawaii.edu' in table_document({**document(), 'script':clipboard}, parsed)['script']

def test_table_import_api_is_owner_scoped_and_does_not_modify_saved_draft(clients):
    a,b = clients
    story = a.post('/api/v1/studio', json=document()).json()
    url = f"/api/v1/studio/{story['id']}/import-table"
    result = a.post(url,json={'expected_version':1})
    assert result.status_code == 200, result.text
    assert len(result.json()['document']['scenes']) == 6
    assert a.get(f"/api/v1/studio/{story['id']}").json()['document']['scenes'][0]['title'] == 'Draft saya'
    assert b.post(url,json={'expected_version':1}).status_code == 404
    assert a.post(url,json={'expected_version':2}).status_code == 409
