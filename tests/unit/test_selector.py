import json

import httpx
import pytest
from pydantic import ValidationError

from app.ai.selector import CandidateResponse, chunks, deduplicate, select_clips, validate_candidates
from app.media.process import MediaError


def segments():
    return [{"id": f"s{i}", "start_ms": i * 10000, "end_ms": (i + 1) * 10000, "text": f"Kalimat {i}."} for i in range(12)]


def candidate(start="s1", end="s4"):
    return {"start_segment_id": start, "end_segment_id": end, "title": "Judul", "reason": "Alasan", "topic": "Topik"}


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
        row = {**candidate('s0', 's3'), 'moment_type': 'reaction'} if len(calls) == 1 else {**candidate('s6', 's9'), 'moment_type': 'boss_fight'}
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'clips': [row]})}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = select_clips(source, duration_ms=120000, count=1, content_profile='gaming', api_key='test', base_url='https://example.test', model='test', client=client)
    assert len(calls) == 2
    assert len(result.candidates) == 1
    assert result.candidates[0]['start_ms'] == 60000
    assert result.candidates[0]['moment_type'] == 'boss_fight'


@pytest.mark.parametrize('rows', [
    [{**candidate(), 'moment_type': 'story'}],
    [{**candidate(), 'moment_type': 'other'}],
    [{**candidate('s0', 's0'), 'moment_type': 'boss_fight'}],
    [],
])
def test_gaming_never_fills_quota_with_story_or_invalid_duration(rows):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'clips': rows})}}]}))) as client:
        with pytest.raises(MediaError) as exc:
            select_clips(segments(), duration_ms=120000, content_profile='gaming', api_key='test', base_url='https://example.test', model='test', client=client)
    assert exc.value.code == 'no_valid_candidates'
    assert 'Aksi tanpa ucapan' in str(exc.value)
