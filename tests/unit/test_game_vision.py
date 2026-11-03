import json
import math
from pathlib import Path

import httpx
import pytest

from app.ai.game_vision import (MAX_FRAMES, SampledFrame, VisualResponse, frame_batches,
                                sampling_interval, scan_gameplay, validate_events)
from app.media.process import Cancelled, MediaError


def frames(count=3):
    return [SampledFrame(f'f{i:04d}', i * 5000 + (17 if i else 0), Path(f'{i}.jpg')) for i in range(count)]


def event(**changes):
    return {'hook_frame_id': 'f0001', 'end_frame_id': 'f0002', 'moment_type': 'character_death',
            'description': 'Layar YOU DIED muncul setelah karakter jatuh.',
            'evidence_frames': ['f0001', 'f0002'], 'certainty': 'clear', **changes}


@pytest.mark.parametrize('duration', [1, 4999, 5000, 5001, 1800000, 1800001, 7200000, 43200000])
def test_sample_plan_is_bounded_across_entire_duration(duration):
    interval = sampling_interval(duration)
    assert interval >= 5000
    assert math.ceil(duration / interval) <= MAX_FRAMES


def test_batches_have_one_frame_overlap_without_duplicate_final_request():
    sampled = frames(23)
    batches = frame_batches(sampled)
    assert list(map(len, batches)) == [12, 12]
    assert batches[0][-1] == batches[1][0]
    assert {f.id for batch in batches for f in batch} == {f.id for f in sampled}
    assert list(map(len, frame_batches(frames(24)))) == [12, 12, 2]


def test_visual_events_use_source_pts_and_filter_invalid_evidence():
    response = VisualResponse(events=[
        event(),
        event(certainty='uncertain'),
        event(hook_frame_id='invented'),
        event(end_frame_id='f0000'),
        event(evidence_frames=['f0002', 'f0001']),
        event(evidence_frames=['f0001', 'f0001', 'f0002']),
        event(evidence_frames=['f0001', 'outside-batch']),
        event(hook_frame_id='f0000'),
        event(end_frame_id=None),  # Later evidence must not imply a payoff.
    ])
    accepted = validate_events(response, frames())
    assert len(accepted) == 1
    assert accepted[0] == {'hook_ms': 5017, 'end_ms': 10017, 'moment_type': 'character_death',
                           'description': event()['description'], 'evidence_frames': ['f0001', 'f0002']}
    single = VisualResponse(events=[event(end_frame_id=None, evidence_frames=['f0001'])])
    assert validate_events(single, frames())[0]['end_ms'] == 5017
    with pytest.raises(ValueError):
        VisualResponse(events=[event(hook_ms=1000)])
    with pytest.raises(ValueError):
        VisualResponse(events=[event(moment_type='streamer_joke')])


def mock_extractor(monkeypatch, count=3):
    created = []
    def extract(source, directory, **kwargs):
        result = []
        for frame in frames(count):
            path = directory / f'{frame.id}.jpg'
            path.write_bytes(b'\xff\xd8\xfftest-jpeg')
            result.append(SampledFrame(frame.id, frame.timestamp_ms, path))
        created.append(directory)
        return result, 5000
    monkeypatch.setattr('app.ai.game_vision.extract_frames', extract)
    return created


def test_scan_uses_inline_images_accounts_usage_and_removes_temporary_frames(monkeypatch, tmp_path):
    directories = mock_extractor(monkeypatch)
    reports, updates = [], []
    def respond(request):
        body = json.loads(request.content)
        content = body['messages'][1]['content']
        images = [part for part in content if part['type'] == 'image_url']
        assert len(images) == 3
        assert all(part['image_url']['url'].startswith('data:image/jpeg;base64,') for part in images)
        assert body['model'] == 'deepseek-flash'
        assert body['response_format'] == {'type': 'json_object'}
        assert 'untrusted quoted data' in body['messages'][0]['content']
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'events': [event()]})}}],
            'usage': {'prompt_tokens': 550, 'completion_tokens': 90}}, headers={'x-request-id': 'qa-vision'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = scan_gameplay(Path('unused.mp4'), tmp_path, duration_ms=15000, api_key='test-only',
                               base_url='https://example.test', client=client, usage=reports.append, progress=updates.append)
    assert result.sampled_frames == 3 and result.interval_ms == 5000
    assert result.events[0]['hook_ms'] == 5017
    assert reports[0]['input_tokens'] == 550 and reports[0]['outcome'] == 'succeeded'
    assert reports[0]['request_id'] == 'qa-vision'
    assert updates[-1] == 1
    assert all(not p.exists() for p in directories)


def test_cancel_after_provider_returns_is_not_swallowed(monkeypatch, tmp_path):
    directories = mock_extractor(monkeypatch)
    state = {'cancelled': False}
    reports = []
    def respond(request):
        state['cancelled'] = True
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"events":[]}'}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(Cancelled):
            scan_gameplay(Path('unused.mp4'), tmp_path, duration_ms=15000, api_key='test-only',
                          base_url='https://example.test', client=client, cancelled=lambda: state['cancelled'], usage=reports.append)
    assert len(reports) == 1
    assert all(not p.exists() for p in directories)


def test_retries_are_bounded_and_provider_details_are_not_exposed(monkeypatch, tmp_path):
    mock_extractor(monkeypatch)
    # Remove retry sleeps while still exercising the real retry control flow.
    clock = iter(range(1000))
    monkeypatch.setattr('app.ai.game_vision.time.monotonic', lambda: next(clock))
    monkeypatch.setattr('app.ai.game_vision.time.sleep', lambda _: None)
    reports = []
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503, text='private-provider-body'))) as client:
        with pytest.raises(MediaError) as exc:
            scan_gameplay(Path('unused.mp4'), tmp_path, duration_ms=15000, api_key='test-only',
                          base_url='https://example.test', client=client, usage=reports.append)
    assert exc.value.code == 'ai_temporarily_unavailable'
    assert 'private-provider-body' not in str(exc.value)
    assert len(reports) == 3


def test_missing_key_or_cancelled_job_never_extracts_frames(monkeypatch, tmp_path):
    monkeypatch.setattr('app.ai.game_vision.extract_frames', lambda *a, **k: pytest.fail('must not extract'))
    with pytest.raises(MediaError) as exc:
        scan_gameplay(Path('unused'), tmp_path, duration_ms=5000, api_key='', base_url='https://example.test')
    assert exc.value.code == 'ai_not_configured'
    with pytest.raises(Cancelled):
        scan_gameplay(Path('unused'), tmp_path, duration_ms=5000, api_key='test-only', base_url='https://example.test', cancelled=lambda: True)


def test_overlap_does_not_duplicate_same_observed_event(monkeypatch, tmp_path):
    mock_extractor(monkeypatch, count=23)
    repeated = event(hook_frame_id='f0011', end_frame_id=None, evidence_frames=['f0011'])
    reports = []
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        'choices': [{'message': {'content': json.dumps({'events': [repeated]})}}],
    }))) as client:
        result = scan_gameplay(Path('unused'), tmp_path, duration_ms=120000, api_key='test-only',
                               base_url='https://example.test', client=client, usage=reports.append)
    assert len(result.events) == 1
    assert result.events[0]['hook_ms'] == 55017
    assert len(reports) == 2


def test_unsupported_or_forbidden_vision_is_not_retried(monkeypatch, tmp_path):
    directories = mock_extractor(monkeypatch)
    reports = []
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, text='private-provider-body'))) as client:
        with pytest.raises(MediaError) as exc:
            scan_gameplay(Path('unused'), tmp_path, duration_ms=15000, api_key='test-only',
                          base_url='https://example.test', client=client, usage=reports.append)
    assert exc.value.code == 'ai_credentials_invalid'
    assert len(reports) == 1
    assert all(not p.exists() for p in directories)
