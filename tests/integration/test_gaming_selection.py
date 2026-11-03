import pytest
from sqlalchemy import select

from app.ai.selector import SelectionResult
from app.domain.models import Job, Clip, ClipRevision, SubtitleCue, Transcript, TranscriptSegment
from app.jobs.runtime import JobContext, claim
from app.jobs.tasks import _transcribe, _analyze
from app.media.process import Cancelled, MediaError


def test_gaming_profile_survives_transcription_and_reanalysis(clients, database, ready_project, monkeypatch, tmp_path):
    owner = clients[0]
    path = f"/api/v1/projects/{ready_project['project_id']}/process"
    response = owner.post(path, json={'content_profile': 'gaming', 'min_duration_ms': 5000, 'max_duration_ms': 10000})
    assert response.status_code == 202
    job_id = response.json()['id']
    monkeypatch.setattr('app.jobs.tasks.transcribe', lambda *args, **kwargs: {
        'language': 'id', 'segments': [{'start_ms': 0, 'end_ms': 9000, 'text': 'Boss menyerang! Dodge sekarang, akhirnya menang!'}],
    })
    _transcribe(JobContext(job_id, *claim(job_id)), tmp_path)
    with database() as db:
        analyze = db.scalar(select(Job).where(Job.kind == 'analyze'))
        assert analyze.input_json['content_profile'] == 'gaming'
        analyze_id = analyze.id
    observed = []
    def select_game(segments, **kwargs):
        observed.append(kwargs['content_profile'])
        return SelectionResult([{'start_ms': 0, 'end_ms': 9000, 'title': 'Boss terakhir', 'reason': 'Ucapan kemenangan', 'topic': 'Boss', 'moment_type': 'boss_fight'}], 5, 1)
    monkeypatch.setattr('app.jobs.tasks.select_clips', select_game)
    _analyze(JobContext(analyze_id, *claim(analyze_id)), tmp_path)
    assert observed == ['gaming']
    # Reusing a saved transcript must carry the profile too, without new ASR.
    retry = owner.post(path, json={'content_profile': 'gaming', 'min_duration_ms': 5000, 'max_duration_ms': 10000})
    assert retry.status_code == 202
    with database() as db:
        queued = db.get(Job, retry.json()['id'])
        assert queued.kind == 'analyze'
        assert queued.input_json['content_profile'] == 'gaming'


def test_process_profile_is_validated_and_legacy_requests_remain_general(clients, database, ready_project):
    path = f"/api/v1/projects/{ready_project['project_id']}/process"
    assert clients[0].post(path, json={'content_profile': 'invented'}).status_code == 422
    assert clients[0].post(path, json={'visual_analysis': True}).status_code == 422
    assert clients[0].post(path, json={'content_profile': 'gaming', 'visual_analysis': True, 'analyze': False}).status_code == 422
    response = clients[0].post(path, json={})
    assert response.status_code == 202
    with database() as db:
        assert db.get(Job, response.json()['id']).input_json['content_profile'] == 'general'


def test_opt_in_visual_analysis_continues_after_silent_transcript(clients, database, ready_project, monkeypatch, tmp_path):
    from app.ai.game_vision import GameVisionResult
    path = f"/api/v1/projects/{ready_project['project_id']}/process"
    response = clients[0].post(path, json={'content_profile': 'gaming', 'visual_analysis': True, 'min_duration_ms': 5000, 'max_duration_ms': 10000})
    assert response.status_code == 202
    job_id = response.json()['id']
    monkeypatch.setattr('app.jobs.tasks.transcribe', lambda *a, **kw: {'language': 'id', 'segments': []})
    _transcribe(JobContext(job_id, *claim(job_id)), tmp_path)
    with database() as db:
        job = db.scalar(select(Job).where(Job.kind == 'analyze'))
        assert job.input_json['visual_analysis'] is True
        analyze_id = job.id
    event = {'hook_ms': 5000, 'end_ms': 5000, 'moment_type': 'character_death', 'description': 'Layar YOU DIED.', 'evidence_frames': ['f0001']}
    calls = []
    def scan(*a, **kw):
        calls.append(kw['duration_ms'])
        return GameVisionResult([event], 3, 5000)
    monkeypatch.setattr('app.ai.game_vision.scan_gameplay', scan)
    checks = []
    def recover(*a, **kw):
        checks.append((kw['start_ms'], kw['end_ms'], kw['language']))
        return {'language': 'id', 'segments': []}
    monkeypatch.setattr('app.jobs.tasks.transcribe_clip', recover)
    # The real selector performs local window construction, with no text request.
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'deepseek_api_key', 'test-only')
    _analyze(JobContext(analyze_id, *claim(analyze_id)), tmp_path)
    assert calls == [12000]
    assert checks == [(0, 7500, 'id')]
    with database() as db:
        job = db.get(Job, analyze_id)
        assert job.status == 'succeeded'
        assert job.result_json['visual_analysis'] == {'sampled_frames': 3, 'interval_ms': 5000, 'events': 1}
        assert job.result_json['subtitle_checks'] == [{'start_ms': 0, 'end_ms': 7500, 'cues': 0, 'status': 'no_speech'}]
        clip = db.scalar(select(Clip).where(Clip.project_id == ready_project['project_id']))
        revision = db.get(ClipRevision, clip.active_revision_id)
        assert revision.start_ms == 0 and revision.end_ms == 7500
        assert 'Petunjuk frame' in revision.reason
        assert db.scalar(select(SubtitleCue).where(SubtitleCue.clip_revision_id == revision.id)) is None
        assert db.get(Transcript, revision.transcript_id).version == 1


@pytest.fixture
def visual_subtitle_job(clients, database, ready_project, monkeypatch, tmp_path):
    from app.ai.game_vision import GameVisionResult
    from app.config import get_settings
    path = f"/api/v1/projects/{ready_project['project_id']}/process"
    response = clients[0].post(path, json={'content_profile': 'gaming', 'visual_analysis': True,
                                         'min_duration_ms': 5000, 'max_duration_ms': 10000})
    assert response.status_code == 202
    job_id = response.json()['id']
    monkeypatch.setattr('app.jobs.tasks.transcribe', lambda *a, **kw: {'language': 'id', 'segments': []})
    _transcribe(JobContext(job_id, *claim(job_id)), tmp_path)
    with database() as db:
        analyze = db.scalar(select(Job).where(Job.kind == 'analyze'))
        analyze_id, transcript_id = analyze.id, analyze.input_json['transcript_id']
    event = {'hook_ms': 8000, 'end_ms': 8000, 'moment_type': 'character_death',
             'description': 'Layar YOU DIED.', 'evidence_frames': ['f0001']}
    monkeypatch.setattr('app.ai.game_vision.scan_gameplay', lambda *a, **kw: GameVisionResult([event], 3, 5000))
    monkeypatch.setattr(get_settings(), 'deepseek_api_key', 'test-only')
    return analyze_id, transcript_id


def test_visual_subtitles_recover_absolute_speech_and_persist_matching_word_timing(
        visual_subtitle_job, clients, database, monkeypatch, tmp_path):
    analyze_id, original_id = visual_subtitle_job
    words = [{'word': ' Aduh', 'start_ms': 4200, 'end_ms': 4500, 'probability': .95},
             {'word': ' kalah!', 'start_ms': 4700, 'end_ms': 5200, 'probability': .9}]
    observed = []
    def recover(*a, **kw):
        observed.append((kw['start_ms'], kw['end_ms'], kw['language']))
        return {'language': 'id', 'segments': [{'start_ms': 4200, 'end_ms': 5200,
                'text': 'Aduh kalah!', 'words_json': words}]}
    monkeypatch.setattr('app.jobs.tasks.transcribe_clip', recover)
    _analyze(JobContext(analyze_id, *claim(analyze_id)), tmp_path)
    assert observed == [(3000, 10500, 'id')]
    with database() as db:
        job = db.get(Job, analyze_id)
        assert job.status == 'succeeded'
        assert job.result_json['subtitle_checks'] == [{'start_ms': 3000, 'end_ms': 10500, 'cues': 1, 'status': 'recovered'}]
        clip = db.get(Clip, job.result_json['clip_ids'][0])
        revision = db.get(ClipRevision, clip.active_revision_id)
        assert revision.transcript_id != original_id
        transcript = db.get(Transcript, revision.transcript_id)
        assert transcript.version == 2
        assert transcript.config_json['base_transcript_id'] == original_id
        assert transcript.config_json['origin'] == 'visual_clip_subtitles'
        assert db.scalar(select(TranscriptSegment).where(TranscriptSegment.transcript_id == original_id)) is None
        stored = db.scalar(select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id))
        assert (stored.start_ms, stored.end_ms, stored.text, stored.words_json) == (4200, 5200, 'Aduh kalah!', words)
        clip_id = clip.id
    response = clients[0].get(f'/api/v1/clips/{clip_id}')
    assert response.status_code == 200
    saved = response.json()['revision']
    assert saved['cues'] == [{'start_ms': 1200, 'end_ms': 2200, 'text': 'Aduh kalah!'}]
    assert saved['source_words'] == [{key: word[key] for key in ('word', 'start_ms', 'end_ms')} for word in words]
    from app.media.word_captions import align_words
    events, missing = align_words(saved['cues'], saved['source_words'], saved['start_ms'])
    assert missing == 0 and len(events) == 2


def test_visual_subtitle_failure_keeps_candidate_and_original_transcript(
        visual_subtitle_job, database, monkeypatch, tmp_path):
    analyze_id, original_id = visual_subtitle_job
    def recover(*a, **kw):
        raise MediaError('transcription_failed', 'Private diagnostic details')
    monkeypatch.setattr('app.jobs.tasks.transcribe_clip', recover)
    _analyze(JobContext(analyze_id, *claim(analyze_id)), tmp_path)
    with database() as db:
        job = db.get(Job, analyze_id)
        assert job.status == 'succeeded' and len(job.result_json['clip_ids']) == 1
        assert job.result_json['subtitle_checks'] == [{'start_ms': 3000, 'end_ms': 10500, 'cues': 0,
                                                       'status': 'failed', 'error_code': 'transcription_failed'}]
        clip = db.get(Clip, job.result_json['clip_ids'][0])
        revision = db.get(ClipRevision, clip.active_revision_id)
        assert revision.transcript_id == original_id
        assert db.scalar(select(SubtitleCue).where(SubtitleCue.clip_revision_id == revision.id)) is None


def test_visual_subtitle_cancellation_stops_before_publishing_candidates(
        visual_subtitle_job, database, monkeypatch, tmp_path):
    analyze_id, original_id = visual_subtitle_job
    def recover(*a, **kw):
        raise Cancelled()
    monkeypatch.setattr('app.jobs.tasks.transcribe_clip', recover)
    with pytest.raises(Cancelled):
        _analyze(JobContext(analyze_id, *claim(analyze_id)), tmp_path)
    with database() as db:
        job = db.get(Job, analyze_id)
        assert job.status != 'succeeded'
        assert db.scalar(select(Clip).where(Clip.project_id == job.project_id)) is None
        assert list(db.scalars(select(Transcript.id).where(Transcript.project_id == job.project_id))) == [original_id]


def test_visual_scan_uses_heavy_queue(clients, database, ready_project, monkeypatch):
    from app.domain.models import Project
    from app.jobs.service import create_job
    from app.jobs.dispatcher import dispatch_once, celery_app
    with database() as db:
        job = create_job(db, db.get(Project, ready_project['project_id']), 'analyze', {'content_profile': 'gaming', 'visual_analysis': True})
        db.commit()
    sent = []
    monkeypatch.setattr(celery_app, 'send_task', lambda *a, **kw: sent.append(kw))
    assert dispatch_once() == 1
    assert sent[0]['queue'] == 'heavy'
