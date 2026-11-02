from sqlalchemy import select

from app.ai.selector import SelectionResult
from app.domain.models import Job
from app.jobs.runtime import JobContext, claim
from app.jobs.tasks import _transcribe, _analyze


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
    response = clients[0].post(path, json={})
    assert response.status_code == 202
    with database() as db:
        assert db.get(Job, response.json()['id']).input_json['content_profile'] == 'general'
