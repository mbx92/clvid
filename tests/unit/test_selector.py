import json

import httpx
import pytest
from pydantic import ValidationError

from app.ai.selector import CandidateResponse, GamingCandidateResponse, chunks, deduplicate, select_clips, validate_candidates, rank_game_candidates, visual_candidates
from app.media.process import MediaError


def segments():
    return [{"id": f"s{i}", "start_ms": i * 10000, "end_ms": (i + 1) * 10000, "text": f"Kalimat {i}."} for i in range(12)]


def candidate(start="s1", end="s4"):
    return {"start_segment_id": start, "end_segment_id": end, "title": "Judul", "reason": "Alasan", "topic": "Topik"}


def game_candidate(start='s0', end='s3', moment='streamer_joke', **updates):
    return {**candidate(start, end), 'moment_type': moment,
            'hook_segment_id': start, 'hook_quote': f'Kalimat {start[1:]}.',
            'payoff_segment_id': end, 'payoff_quote': f'Kalimat {end[1:]}.', **updates}


def test_segment_ids_are_authority_not_provider_timestamps():
    response = CandidateResponse(clips=[candidate(), candidate("invented"), candidate("s4", "s1")])
    valid = validate_candidates(response, segments(), duration_ms=120000, min_duration_ms=30000, max_duration_ms=60000)
    assert len(valid) == 1
    assert valid[0]["start_ms"] == 10000 and valid[0]["end_ms"] == 50000
    with pytest.raises(ValidationError):
        CandidateResponse(clips=[{**candidate(), "start_ms": 123}])


def test_deduplicate_overlapping_candidates():
    candidates = [{"start_ms": 0, "end_ms": 60000}, {"start_ms": 5000, "end_ms": 60000}, {"start_ms": 70000, "end_ms": 110000}]
    assert deduplicate(candidates, 5) == [candidates[0], candidates[2]]


def test_chunking_preserves_every_segment_with_overlap_and_progress():
    original = [{**s, "text": "pengujian " * 30} for s in segments()]
    batches = chunks(original, token_budget=2600)
    assert len(batches) > 1
    assert {s["id"] for batch in batches for s in batch} == {s["id"] for s in original}
    assert batches[0][-1] in batches[1]


def test_blank_provider_response_is_explicit_failure_without_fake_candidates():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [{"message": {"content": " "}}]})))
    reports = []
    with pytest.raises(MediaError, match="Respons AI kosong"):
        select_clips(segments(), duration_ms=120000, api_key="test-only", base_url="https://example.test", model="test", max_retries=0, client=client, usage=reports.append)
    assert reports[0]["outcome"] == "failed"


def test_controlled_provider_adapter_validates_and_records_usage():
    def respond(request):
        request_body = json.loads(request.content)
        assert request_body["response_format"] == {"type": "json_object"}
        assert "transcript" in request_body["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"clips": [candidate()]})}}], "usage": {"prompt_tokens": 88, "completion_tokens": 27}}, headers={"x-request-id": "test-request"})
    reports = []
    client = httpx.Client(transport=httpx.MockTransport(respond))
    result = select_clips(segments(), duration_ms=120000, api_key="test-only", base_url="https://example.test", model="test", client=client, usage=reports.append)
    assert len(result.candidates) == 1
    assert reports[0]["input_tokens"] == 88 and reports[0]["request_id"] == "test-request"


def test_missing_key_fails_before_network():
    with pytest.raises(MediaError) as error:
        select_clips(segments(), duration_ms=120000, api_key="", base_url="https://example.test", model="test")
    assert error.value.code == "ai_not_configured"


def test_gaming_ranks_later_boss_fight_before_early_reaction_across_batches(monkeypatch):
    source = segments()
    monkeypatch.setattr('app.ai.selector.chunks', lambda *args: [source[:6], source[6:]])
    calls = []
    def respond(request):
        body = json.loads(request.content)
        payload = json.loads(body['messages'][1]['content'])
        calls.append(payload)
        assert payload['content_profile'] == 'gaming'
        assert 'ONLY timed transcript text' in body['messages'][0]['content']
        assert 'boss' in body['messages'][0]['content']
        row = game_candidate('s0', 's3', 'reaction', payoff_segment_id=None, payoff_quote=None) if len(calls) == 1 else game_candidate('s6', 's9', 'boss_fight')
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'clips': [row]})}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = select_clips(source, duration_ms=120000, count=1, content_profile='gaming', api_key='test', base_url='https://example.test', model='test', client=client)
    assert len(calls) == 2
    assert len(result.candidates) == 1
    assert result.candidates[0]['start_ms'] == 60000
    assert result.candidates[0]['moment_type'] == 'boss_fight'


@pytest.mark.parametrize('rows', [
    [game_candidate(moment='story')],
    [game_candidate(moment='other')],
    [game_candidate('s0', 's0', 'boss_fight')],
    [],
])
def test_gaming_never_fills_quota_with_story_or_invalid_duration(rows):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'clips': rows})}}]}))) as client:
        with pytest.raises(MediaError) as exc:
            select_clips(segments(), duration_ms=120000, content_profile='gaming', api_key='test', base_url='https://example.test', model='test', client=client)
    assert exc.value.code == 'no_valid_candidates'
    assert 'Aksi tanpa ucapan' in str(exc.value)


@pytest.mark.parametrize('updates', [
    {'hook_quote': 'Ucapan yang tidak ada'}, {'hook_quote': '   '},
    {'hook_segment_id': 'missing'}, {'hook_segment_id': 's8', 'hook_quote': 'Kalimat 8.'},
    {'hook_segment_id': 's2', 'hook_quote': 'Kalimat 2.', 'payoff_segment_id': 's1', 'payoff_quote': 'Kalimat 1.'},
    {'payoff_quote': None}, {'payoff_segment_id': None},
    {'payoff_segment_id': 's8', 'payoff_quote': 'Kalimat 8.'},
])
def test_gaming_rejects_fabricated_or_misordered_evidence(updates):
    response = GamingCandidateResponse(clips=[game_candidate(**updates)])
    assert validate_candidates(response, segments(), duration_ms=120000, min_duration_ms=30000, max_duration_ms=60000) == []


def test_complete_joke_can_rank_above_boss_and_same_segment_punchline_is_valid():
    response = GamingCandidateResponse(clips=[
        game_candidate('s6', 's9', 'boss_fight', payoff_segment_id=None, payoff_quote=None),
        game_candidate('s0', 's3', 'streamer_joke', payoff_segment_id='s0', payoff_quote='kalimat   0.'),
        game_candidate('s0', 's4', 'streamer_joke', payoff_segment_id='s0', payoff_quote='Kalimat 0.'),
        game_candidate('s8', 's11', 'character_death'),
    ])
    valid = validate_candidates(response, segments(), duration_ms=120000, min_duration_ms=30000, max_duration_ms=60000)
    ranked = rank_game_candidates(valid)
    assert [c['moment_type'] for c in ranked] == ['streamer_joke', 'character_death', 'boss_fight']
    assert ranked[0]['hook_ms'] == ranked[0]['payoff_ms'] == 0
    assert 'Kalimat 0.' in ranked[0]['reason']


def test_visual_death_can_make_candidate_without_transcript_and_stays_within_source():
    events = [{'hook_ms': 110000, 'end_ms': 115000, 'moment_type': 'character_death', 'description': 'Layar YOU DIED terlihat.', 'evidence_frames': ['f0022', 'f0023']}]
    result = select_clips([], duration_ms=120000, content_profile='gaming', visual_events=events, api_key='test', base_url='https://example.test', model='test')
    assert len(result.candidates) == 1
    clip = result.candidates[0]
    assert clip['end_ms'] == 120000
    assert 30000 <= clip['end_ms'] - clip['start_ms'] <= 60000
    assert clip['evidence_source'] == 'frames'
    assert 'start_segment_id' not in clip
    assert visual_candidates(events, duration_ms=1000, min_duration_ms=30000, max_duration_ms=60000) == []


def test_visual_and_transcript_references_to_same_hook_do_not_duplicate():
    base = {'start_ms': 0, 'end_ms': 30000, 'hook_ms': 5000, 'payoff_ms': 12000, 'moment_type': 'character_death'}
    text = {**base, 'evidence_source': 'transcript', 'hook_segment_id': 's1', 'hook_quote': 'aku mati'}
    frame = {**base, 'end_ms': 45000, 'hook_ms': 7000, 'evidence_source': 'frames'}
    assert rank_game_candidates([text, frame]) == [text]


def test_visual_window_preserves_known_payoff_or_rejects_impossible_span():
    base = {'hook_ms': 10000, 'moment_type': 'boss_fight', 'description': 'Pertarungan berakhir dengan kemenangan.', 'evidence_frames': ['f1', 'f2']}
    assert visual_candidates([{**base, 'end_ms': 80000}], duration_ms=120000, min_duration_ms=30000, max_duration_ms=60000) == []
    clip = visual_candidates([{**base, 'end_ms': 70000}], duration_ms=120000, min_duration_ms=30000, max_duration_ms=60000)[0]
    assert clip['start_ms'] == 10000 and clip['end_ms'] == 70000
    assert clip['payoff_ms'] == 70000


def test_hook_evidence_must_be_in_clip_time_bounds_even_when_segments_overlap():
    rows = segments()
    rows[2] = {**rows[2], 'start_ms': 90000, 'end_ms': 100000}
    response = GamingCandidateResponse(clips=[game_candidate(hook_segment_id='s2', hook_quote='Kalimat 2.', payoff_segment_id=None, payoff_quote=None)])
    assert validate_candidates(response, rows, duration_ms=120000, min_duration_ms=30000, max_duration_ms=60000) == []
