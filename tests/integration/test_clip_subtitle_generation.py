from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.domain.models import Asset, Clip, ClipRevision, Job, OutboxEvent, Project, SubtitleCue, Transcript, TranscriptSegment
from app.jobs.runtime import JobContext, claim
from app.media.process import Cancelled, MediaError


def empty_clip(owner, project_id):
    response = owner.post(f"/api/v1/projects/{project_id}/clips", json={
        "title": "Pertarungan", "start_ms": 2000, "end_ms": 10000, "cues": [],
        "crop_json": {"mode": "fit"}, "subtitle_style_json": {"animation": "pop", "display_mode": "words"},
    })
    assert response.status_code == 201, response.text
    return response.json()


def request_subtitles(owner, clip, *, replace_existing=False):
    body = {"expected_revision": clip["revision"]["revision"], "language": "id"}
    if replace_existing:
        body["replace_existing"] = True
    return owner.post(f"/api/v1/clips/{clip['id']}/subtitles/generate", json=body)


def clip_with_existing_subtitles(owner, project_id):
    clip = empty_clip(owner, project_id)
    response = owner.patch(f"/api/v1/clips/{clip['id']}", json={
        "expected_revision": 1, "title": "Judul editorial", "crop_json": {"mode": "fill", "x": .3, "y": .6},
        "subtitle_style_json": {"animation": "fade", "display_mode": "sentence", "font_size": 64},
        "cues": [{"start_ms": 100, "end_ms": 1100, "text": "Subtitle lama"}],
    })
    assert response.status_code == 200, response.text
    return response.json()


def speech_result():
    return {"language": "id", "segments": [{"start_ms": 3500, "end_ms": 4700, "text": "Awas serangan!",
        "words_json": [{"start_ms": 3500, "end_ms": 3900, "word": " Awas", "probability": .98},
                       {"start_ms": 4000, "end_ms": 4700, "word": " serangan!", "probability": .98}]}], "runtime": {"device": "cpu"}}


def add_transcript(database, project_id, version=1):
    with database() as db:
        transcript = Transcript(project_id=project_id, version=version, language="id", model="small")
        db.add(transcript)
        db.flush()
        db.add_all([
            TranscriptSegment(transcript_id=transcript.id, order=0, start_ms=0, end_ms=1500, text="Sebelum", words_json=[{"start_ms": 0, "end_ms": 1500, "word": " Sebelum"}]),
            TranscriptSegment(transcript_id=transcript.id, order=1, start_ms=10500, end_ms=12000, text="Sesudah", words_json=[{"start_ms": 10500, "end_ms": 12000, "word": " Sesudah"}]),
        ])
        db.commit()
        return transcript.id


def test_generation_is_owned_versioned_and_deduplicated(clients, database, ready_project):
    clip = empty_clip(clients[0], ready_project["project_id"])
    endpoint = f"/api/v1/clips/{clip['id']}/subtitles/generate"
    assert clients[1].post(endpoint, json={"expected_revision": 1}).status_code == 404
    assert clients[0].post(endpoint, json={"expected_revision": 2}).status_code == 409
    assert clients[0].post(endpoint, json={"expected_revision": 1, "language": "invalid"}).status_code == 422
    response = request_subtitles(clients[0], clip)
    assert response.status_code == 202, response.text
    assert request_subtitles(clients[0], clip).json()["id"] == response.json()["id"]
    with database() as db:
        job = db.get(Job, response.json()["id"])
        assert job.kind == "subtitle_generate" and job.status == "queued"
        assert job.input_json["replace_existing"] is False
        assert job.input_json["source_asset_id"] == ready_project["asset_id"]
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.job_id == job.id)) == 1


def test_empty_result_cache_changes_with_model_decoding_and_algorithm(clients, database, ready_project, monkeypatch):
    from app.ai import subtitle_recovery_config
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "whisper_subtitle_model", None)
    clip = empty_clip(clients[0], ready_project["project_id"])
    original = request_subtitles(clients[0], clip).json()["id"]
    with database() as db:
        job = db.get(Job, original)
        job.status, job.result_json = "succeeded", {"cues": 0}
        db.commit()
    assert request_subtitles(clients[0], clip).json()["id"] == original
    monkeypatch.setattr(get_settings(), "whisper_model", "medium")
    model_changed = request_subtitles(clients[0], clip).json()["id"]
    assert model_changed != original
    assert request_subtitles(clients[0], clip).json()["id"] == model_changed
    monkeypatch.setattr(get_settings(), "whisper_beam_size", 7)
    decoding_changed = request_subtitles(clients[0], clip).json()["id"]
    assert decoding_changed not in (original, model_changed)
    monkeypatch.setattr(subtitle_recovery_config, "ALGORITHM_VERSION", "test-recovery-v3")
    algorithm_changed = request_subtitles(clients[0], clip).json()["id"]
    assert algorithm_changed not in (original, model_changed, decoding_changed)
    with database() as db:
        requested = db.get(Job, algorithm_changed).input_json["recovery_signature"]
        assert requested["algorithm"] == "test-recovery-v3"
        assert requested["asr"]["model"] == "medium" and requested["asr"]["beam_size"] == 7


def test_recovery_executes_queued_settings_and_records_actual_runtime(clients, database, ready_project, monkeypatch, tmp_path):
    from app.config import get_settings
    from app.jobs.clip_subtitles import generate_subtitles
    settings = get_settings()
    monkeypatch.setattr(settings, "whisper_model", "small")
    monkeypatch.setattr(settings, "whisper_subtitle_model", None)
    monkeypatch.setattr(settings, "whisper_device", "auto")
    monkeypatch.setattr(settings, "whisper_beam_size", 5)
    clip = empty_clip(clients[0], ready_project["project_id"])
    job_id = request_subtitles(clients[0], clip).json()["id"]
    # A later server configuration must not silently change the queued job.
    monkeypatch.setattr(settings, "whisper_model", "medium")
    monkeypatch.setattr(settings, "whisper_subtitle_model", "large-v3-turbo")
    monkeypatch.setattr(settings, "whisper_beam_size", 7)
    observed = []
    def transcribe(*args, **kwargs):
        actual = kwargs["settings"]
        observed.append((actual.whisper_model, actual.whisper_subtitle_model, actual.whisper_device, actual.whisper_beam_size))
        return speech_result()
    monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", transcribe)
    generate_subtitles(JobContext(job_id, *claim(job_id)), tmp_path)
    assert observed == [("small", "small", "auto", 5)]
    with database() as db:
        job = db.get(Job, job_id)
        signature = job.input_json["recovery_signature"]
        assert job.result_json["recovery_signature"] == signature
        assert job.result_json["runtime"]["device"] == "cpu"
        revision = db.get(ClipRevision, db.get(Clip, clip["id"]).active_revision_id)
        transcript = db.get(Transcript, revision.transcript_id)
        assert transcript.model == "small"
        assert transcript.config_json["recovery_signature"] == signature
        assert transcript.config_json["runtime"]["device"] == "cpu"


def test_subtitle_model_override_has_its_own_cache_identity(clients, database, ready_project, monkeypatch):
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "whisper_model", "small")
    monkeypatch.setattr(settings, "whisper_subtitle_model", None)
    clip = empty_clip(clients[0], ready_project["project_id"])
    initial = request_subtitles(clients[0], clip).json()["id"]
    monkeypatch.setattr(settings, "whisper_subtitle_model", "large-v3-turbo")
    overridden = request_subtitles(clients[0], clip).json()["id"]
    assert overridden != initial
    # The general transcription model does not affect a pinned subtitle model.
    monkeypatch.setattr(settings, "whisper_model", "medium")
    assert request_subtitles(clients[0], clip).json()["id"] == overridden
    with database() as db:
        assert db.get(Job, overridden).input_json["recovery_signature"]["asr"]["model"] == "large-v3-turbo"


def test_recovery_rejects_incompatible_algorithm_before_asr(clients, database, ready_project, monkeypatch, tmp_path):
    from app.jobs.clip_subtitles import generate_subtitles
    clip = empty_clip(clients[0], ready_project["project_id"])
    job_id = request_subtitles(clients[0], clip).json()["id"]
    with database() as db:
        job = db.get(Job, job_id)
        job.input_json = {**job.input_json, "recovery_signature": {**job.input_json["recovery_signature"], "algorithm": "unsupported-policy"}}
        db.commit()
    monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", lambda *a, **kw: pytest.fail("ASR must not run for incompatible policy"))
    with pytest.raises(MediaError) as failure:
        generate_subtitles(JobContext(job_id, *claim(job_id)), tmp_path)
    assert failure.value.code == "subtitle_pipeline_changed"


def test_generation_rejects_existing_cues_and_unready_source(clients, database, ready_project):
    clip = empty_clip(clients[0], ready_project["project_id"])
    with database() as db:
        source = db.get(Asset, ready_project["asset_id"])
        source.state = "pending"
        db.commit()
    assert request_subtitles(clients[0], clip).status_code == 409
    with database() as db:
        db.get(Asset, ready_project["asset_id"]).state = "ready"
        revision_id = db.get(Clip, clip["id"]).active_revision_id
        db.add(SubtitleCue(clip_revision_id=revision_id, start_ms=0, end_ms=1000, text="Edit manual"))
        db.commit()
    response = request_subtitles(clients[0], clip)
    assert response.status_code == 409 and response.json()["code"] == "SUBTITLES_EXIST"
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0


def test_explicit_replacement_keeps_old_revision_and_editorial_settings(clients, database, ready_project, monkeypatch, tmp_path):
    from app.jobs.clip_subtitles import generate_subtitles
    clip = clip_with_existing_subtitles(clients[0], ready_project["project_id"])
    assert request_subtitles(clients[0], clip).status_code == 409
    response = request_subtitles(clients[0], clip, replace_existing=True)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", lambda *a, **kw: speech_result())
    generate_subtitles(JobContext(job_id, *claim(job_id)), tmp_path)
    with database() as db:
        job = db.get(Job, job_id)
        assert job.status == "succeeded" and job.input_json["replace_existing"] is True
        old = db.get(ClipRevision, clip["revision"]["id"])
        new = db.get(ClipRevision, db.get(Clip, clip["id"]).active_revision_id)
        assert new.id != old.id and new.revision == old.revision + 1
        for field in ("start_ms", "end_ms", "title", "reason", "topic", "crop_json", "subtitle_style_json"):
            assert getattr(new, field) == getattr(old, field)
        assert [cue.text for cue in db.scalars(select(SubtitleCue).where(SubtitleCue.clip_revision_id == old.id))] == ["Subtitle lama"]
        assert [cue.text for cue in db.scalars(select(SubtitleCue).where(SubtitleCue.clip_revision_id == new.id))] == ["Awas serangan!"]
        assert db.get(Transcript, new.transcript_id).config_json["replace_existing"] is True


def test_empty_replacement_result_preserves_existing_cues(clients, database, ready_project, monkeypatch, tmp_path):
    from app.jobs.clip_subtitles import generate_subtitles
    clip = clip_with_existing_subtitles(clients[0], ready_project["project_id"])
    job_id = request_subtitles(clients[0], clip, replace_existing=True).json()["id"]
    monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", lambda *a, **kw: {"language": "id", "segments": []})
    generate_subtitles(JobContext(job_id, *claim(job_id)), tmp_path)
    with database() as db:
        job = db.get(Job, job_id)
        assert job.status == "succeeded" and job.result_json["cues"] == 0
        assert job.result_json["preserved_existing"] is True
        assert "Subtitle sebelumnya tetap dipertahankan" in job.result_json["message"]
        assert db.get(Clip, clip["id"]).active_revision_id == clip["revision"]["id"]
        assert db.scalar(select(func.count()).select_from(ClipRevision)) == 2
        assert db.scalar(select(func.count()).select_from(Transcript)) == 0
        assert [cue.text for cue in db.scalars(select(SubtitleCue))] == ["Subtitle lama"]


def test_explicit_replacement_cannot_overwrite_a_concurrent_edit(clients, database, ready_project, monkeypatch, tmp_path):
    from app.jobs.clip_subtitles import generate_subtitles
    clip = clip_with_existing_subtitles(clients[0], ready_project["project_id"])
    job_id = request_subtitles(clients[0], clip, replace_existing=True).json()["id"]
    edited = []
    def transcribe(*a, **kw):
        response = clients[0].patch(f"/api/v1/clips/{clip['id']}", json={
            "expected_revision": clip["revision"]["revision"], "title": "Edit baru",
            "cues": [{"start_ms": 200, "end_ms": 1000, "text": "Koreksi pengguna"}],
        })
        assert response.status_code == 200
        edited.append(response.json())
        return speech_result()
    monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", transcribe)
    with pytest.raises(MediaError) as failure:
        generate_subtitles(JobContext(job_id, *claim(job_id)), tmp_path)
    assert failure.value.code == "revision_conflict"
    with database() as db:
        current = db.get(ClipRevision, db.get(Clip, clip["id"]).active_revision_id)
        assert current.id == edited[0]["revision"]["id"] and current.title == "Edit baru"
        assert [cue.text for cue in db.scalars(select(SubtitleCue).where(SubtitleCue.clip_revision_id == current.id))] == ["Koreksi pengguna"]
        assert db.scalar(select(func.count()).select_from(Transcript)) == 0


def test_generation_creates_new_revision_and_retains_project_transcript(clients, database, ready_project, monkeypatch, tmp_path):
    from app.jobs.clip_subtitles import generate_subtitles
    first_transcript = add_transcript(database, ready_project["project_id"])
    clip = empty_clip(clients[0], ready_project["project_id"])
    job_id = request_subtitles(clients[0], clip).json()["id"]
    # A full transcription completed after the request: merge into this newer version.
    latest_transcript = add_transcript(database, ready_project["project_id"], version=2)
    observed = []
    def transcribe(source, scratch, **kwargs):
        observed.append(kwargs)
        assert isinstance(source, Path)
        return speech_result()
    monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", transcribe)
    generate_subtitles(JobContext(job_id, *claim(job_id)), tmp_path)
    assert observed[0]["start_ms"] == 2000 and observed[0]["end_ms"] == 10000 and observed[0]["language"] == "id"
    with database() as db:
        job = db.get(Job, job_id)
        assert job.status == "succeeded" and job.result_json["cues"] == 1
        revisions = db.scalars(select(ClipRevision).where(ClipRevision.clip_id == clip["id"]).order_by(ClipRevision.revision)).all()
        old, new = revisions
        assert old.transcript_id == first_transcript
        assert (new.start_ms, new.end_ms, new.title, new.crop_json, new.subtitle_style_json) == (old.start_ms, old.end_ms, old.title, old.crop_json, old.subtitle_style_json)
        assert db.get(Clip, clip["id"]).active_revision_id == new.id
        transcript = db.get(Transcript, new.transcript_id)
        assert transcript.version == 3 and transcript.config_json["base_transcript_id"] == latest_transcript
        segments = db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id).order_by(TranscriptSegment.order)).all()
        assert [segment.text for segment in segments] == ["Sebelum", "Awas serangan!", "Sesudah"]
        assert segments[1].words_json[0]["start_ms"] == 3500
        assert db.scalar(select(func.count()).select_from(SubtitleCue).where(SubtitleCue.clip_revision_id == old.id)) == 0
        cue = db.scalar(select(SubtitleCue).where(SubtitleCue.clip_revision_id == new.id))
        assert (cue.start_ms, cue.end_ms, cue.text) == (1500, 2700, "Awas serangan!")
        from app.domain.subtitle_timing import subtitle_events
        events = subtitle_events(db, new, [{"start_ms": cue.start_ms, "end_ms": cue.end_ms, "text": cue.text}])
        assert [(event["start_ms"], event["end_ms"], event["text"]) for event in events] == [(1500, 1900, "Awas"), (2000, 2700, "serangan!")]
    # Per-word preview/export uses the recovered absolute word timestamps.
    response = clients[0].get(f"/api/v1/clips/{clip['id']}/subtitle-words?start_ms=2000&end_ms=10000")
    assert response.status_code == 200
    assert response.json()["source_words"][0]["start_ms"] == 3500


def test_no_speech_finishes_without_fabricating_cues_or_changing_revision(clients, database, ready_project, monkeypatch, tmp_path):
    from app.jobs.clip_subtitles import generate_subtitles
    clip = empty_clip(clients[0], ready_project["project_id"])
    job_id = request_subtitles(clients[0], clip).json()["id"]
    monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", lambda *args, **kwargs: {"language": "id", "segments": []})
    generate_subtitles(JobContext(job_id, *claim(job_id)), tmp_path)
    with database() as db:
        job = db.get(Job, job_id)
        assert job.status == "succeeded" and job.result_json["cues"] == 0
        assert "Ucapan belum berhasil dikenali" in job.result_json["message"]
        assert job.result_json["recovery_signature"] == job.input_json["recovery_signature"]
        assert db.scalar(select(func.count()).select_from(ClipRevision)) == 1
        assert db.scalar(select(func.count()).select_from(Transcript)) == 0
        assert db.scalar(select(func.count()).select_from(SubtitleCue)) == 0
        assert db.get(Project, ready_project["project_id"]).status == "ready"


@pytest.mark.parametrize("requested,expected", [("auto", "id"), ("id", "id"), ("en", "en")])
def test_generation_prefers_full_video_language_unless_explicit(clients, database, ready_project, monkeypatch, tmp_path, requested, expected):
    from app.jobs.clip_subtitles import generate_subtitles
    add_transcript(database, ready_project["project_id"])
    clip = empty_clip(clients[0], ready_project["project_id"])
    response = clients[0].post(f"/api/v1/clips/{clip['id']}/subtitles/generate", json={"expected_revision": 1, "language": requested})
    assert response.status_code == 202
    observed = []
    def transcribe(*args, **kwargs):
        observed.append(kwargs["language"])
        return {"language": expected, "segments": []}
    monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", transcribe)
    job_id = response.json()["id"]
    generate_subtitles(JobContext(job_id, *claim(job_id)), tmp_path)
    assert observed == [expected]


@pytest.mark.parametrize("mutation,error", [("edit", "revision_conflict"), ("source", "source_not_ready"), ("delete", None), ("cancel", None)])
def test_generation_cannot_publish_over_newer_edits_or_invalid_work(clients, database, ready_project, monkeypatch, tmp_path, mutation, error):
    from app.jobs.clip_subtitles import generate_subtitles
    clip = empty_clip(clients[0], ready_project["project_id"])
    job_id = request_subtitles(clients[0], clip).json()["id"]
    def transcribe(*args, **kwargs):
        if mutation == "edit":
            response = clients[0].patch(f"/api/v1/clips/{clip['id']}", json={"expected_revision": 1, "title": "Judul baru"})
            assert response.status_code == 200
        else:
            with database() as db:
                if mutation == "source":
                    db.get(Asset, ready_project["asset_id"]).state = "invalid"
                elif mutation == "delete":
                    db.get(Project, ready_project["project_id"]).lifecycle_state = "deleting"
                else:
                    db.get(Job, job_id).status = "cancel_requested"
                db.commit()
        return speech_result()
    monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", transcribe)
    with pytest.raises(MediaError if error else Cancelled) as failure:
        generate_subtitles(JobContext(job_id, *claim(job_id)), tmp_path)
    if error:
        assert failure.value.code == error
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Transcript)) == 0
        assert db.scalar(select(func.count()).select_from(SubtitleCue)) == 0


def test_merge_keeps_words_before_and_after_recovered_interval():
    from app.jobs.clip_subtitles import merged_segments
    previous = [{"start_ms": 1000, "end_ms": 11000, "text": "Sebelum tengah sesudah", "words_json": [
        {"start_ms": 1000, "end_ms": 1500, "word": " Sebelum"},
        {"start_ms": 3000, "end_ms": 4000, "word": " tengah"},
        {"start_ms": 10500, "end_ms": 11000, "word": " sesudah"},
    ]}]
    result = merged_segments(previous, speech_result()["segments"], 2000, 10000)
    assert [item["text"] for item in result] == ["Sebelum", "Awas serangan!", "sesudah"]
    assert result[0]["end_ms"] <= 2000 and result[-1]["start_ms"] >= 10000
    assert previous[0]["text"] == "Sebelum tengah sesudah"


@pytest.mark.parametrize("failure", ["worker", "expired_lease"])
def test_subtitle_failure_does_not_mark_project_failed(clients, database, ready_project, monkeypatch, failure):
    from datetime import timedelta
    from app.config import get_settings
    from app.domain.models import utcnow
    from app.jobs.reconciler import reconcile_once
    from app.jobs.tasks import run_job
    clip = empty_clip(clients[0], ready_project["project_id"])
    job_id = request_subtitles(clients[0], clip).json()["id"]
    if failure == "worker":
        def unavailable(*args, **kwargs):
            raise MediaError("transcription_failed", "Transkripsi gagal.")
        monkeypatch.setattr("app.jobs.clip_subtitles.transcribe_clip", unavailable)
        run_job(job_id)
    else:
        monkeypatch.setattr(get_settings(), "job_max_attempts", 1)
        claim(job_id)
        with database() as db:
            db.get(Job, job_id).lease_expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        assert reconcile_once()["recovered"] == 1
    with database() as db:
        assert db.get(Job, job_id).status == "failed"
        project = db.get(Project, ready_project["project_id"])
        assert project.status == "ready" and project.error_message is None
        assert db.scalar(select(func.count()).select_from(ClipRevision)) == 1
        assert db.scalar(select(func.count()).select_from(SubtitleCue)) == 0
