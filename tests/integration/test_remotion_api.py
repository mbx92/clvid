"""Saved Remotion style, immutable export config, and queued version fencing."""
from sqlalchemy import select

from app.domain.models import ClipRevision, Export, Job, Project, Transcript, TranscriptSegment
from app.domain.subtitle_timing import subtitle_events
from app.jobs.tasks import run_job
from app.media.remotion import REMOTION_RENDERER_VERSION


def create_clip(client, project_id, style=None):
    response = client.post(f"/api/v1/projects/{project_id}/clips", json={
        "start_ms": 1000, "end_ms": 7000,
        "cues": [{"start_ms": 100, "end_ms": 2000, "text": "Momen lucu"}],
        "subtitle_style_json": style or {},
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_podcast_reference_template_is_saved_and_used_in_export(clients, ready_project, database):
    owner = clients[0]
    with database() as db:
        transcript = Transcript(project_id=ready_project['project_id'], version=1, language='id', model='fixture')
        db.add(transcript)
        db.flush()
        db.add(TranscriptSegment(transcript_id=transcript.id, order=0, start_ms=1100, end_ms=1800, text='Momen lucu',
            words_json=[{'word': 'Momen', 'start_ms': 1100, 'end_ms': 1400}, {'word': ' lucu', 'start_ms': 1500, 'end_ms': 1800}]))
        db.commit()
    clip = create_clip(owner, ready_project['project_id'])
    endpoint = f"/api/v1/clips/{clip['id']}"
    style = {'renderer': 'remotion', 'remotion_template': 'podcast', 'bold': True,
             'italic': True, 'uppercase': True, 'text_color': '#FFE600', 'outline_width': 6,
             'background': False, 'font_size': 64, 'auto_fit': False, 'safe_margin': .16}
    saved = owner.patch(endpoint, json={'expected_revision': 1, 'subtitle_style_json': style})
    assert saved.status_code == 200
    reloaded = owner.get(endpoint).json()['revision']['subtitle_style_json']
    assert all(reloaded[key] == value for key, value in style.items())
    exported = owner.post(endpoint + '/exports', json={'revision': 2, 'resolution': 720})
    assert exported.status_code == 202
    with database() as db:
        export = db.scalar(select(Export).where(Export.job_id == exported.json()['id']))
        config = export.config_json
        assert config['remotion_template'] == 'podcast'
        assert config['renderer_version'] == REMOTION_RENDERER_VERSION
        revision = db.get(ClipRevision, export.clip_revision_id)
        events = subtitle_events(db, revision, [{'start_ms': 100, 'end_ms': 2000, 'text': 'Momen lucu'}])
        assert events == [{'start_ms': 100, 'end_ms': 2000, 'text': 'Momen lucu', 'word_spans': [
            {'start_ms': 100, 'end_ms': 400, 'start_word': 0, 'end_word': 1},
            {'start_ms': 500, 'end_ms': 800, 'start_word': 1, 'end_word': 2}]}]
        revision.subtitle_style_json = {**revision.subtitle_style_json, 'display_mode': 'words'}
        assert subtitle_events(db, revision, [{'start_ms': 100, 'end_ms': 2000, 'text': 'Momen lucu'}]) == events


def test_podcast_export_requires_word_timing_only_when_captions_are_enabled(clients, ready_project):
    owner = clients[0]
    style = {'renderer': 'remotion', 'remotion_template': 'podcast'}
    clip = create_clip(owner, ready_project['project_id'], style)
    endpoint = f"/api/v1/clips/{clip['id']}"
    response = owner.post(endpoint + '/exports', json={'revision': 1, 'resolution': 720})
    assert response.status_code == 422 and response.json()['code'] == 'SUBTITLE_WORD_TIMING'
    assert 'Highlight kata' in response.json()['message']
    assert owner.patch(endpoint, json={'expected_revision': 1, 'subtitle_style_json': {**style, 'enabled': False}}).status_code == 200
    assert owner.post(endpoint + '/exports', json={'revision': 2, 'resolution': 720}).status_code == 202


def test_remotion_style_round_trip_and_saved_revision_selects_export_renderer(clients, ready_project, database):
    owner = clients[0]
    clip = create_clip(owner, ready_project["project_id"])
    assert clip["revision"]["subtitle_style_json"]["renderer"] == "ffmpeg"
    endpoint = f"/api/v1/clips/{clip['id']}"
    updated = owner.patch(endpoint, json={"expected_revision": 1, "subtitle_style_json": {
        "renderer": "remotion", "remotion_template": "cinematic", "animation": "fade", "enabled": False,
    }})
    assert updated.status_code == 200, updated.text
    style = owner.get(endpoint).json()["revision"]["subtitle_style_json"]
    assert style["renderer"] == "remotion" and style["remotion_template"] == "cinematic" and style["enabled"] is False
    for invalid in ({"renderer": "arbitrary-script"}, {"remotion_template": "../../private"}):
        assert owner.patch(endpoint, json={"expected_revision": 2, "subtitle_style_json": invalid}).status_code == 422
    assert owner.get(endpoint).json()["revision"]["revision"] == 2
    jobs = []
    for revision in (1, 2):
        response = owner.post(endpoint + "/exports", json={"revision": revision, "resolution": 720})
        assert response.status_code == 202, response.text
        jobs.append(response.json()["id"])
    repeated = owner.post(endpoint + "/exports", json={"revision": 2, "resolution": 720})
    assert repeated.json()["id"] == jobs[1]
    with database() as db:
        configs = [db.scalar(select(Export).where(Export.job_id == job)).config_json for job in jobs]
        assert configs[0]["renderer"] == "ffmpeg" and "renderer_version" not in configs[0]
        assert configs[1]["renderer"] == "remotion"
        assert configs[1]["renderer_version"] == REMOTION_RENDERER_VERSION
        assert configs[1]["remotion_template"] == "cinematic"
        assert db.get(Job, jobs[1]).input_json["config"] == configs[1]


def test_renderer_version_changes_fingerprint_and_fences_old_job(clients, ready_project, database, monkeypatch):
    owner = clients[0]
    clip = create_clip(owner, ready_project["project_id"], {"renderer": "remotion", "remotion_template": "gaming"})
    endpoint = f"/api/v1/clips/{clip['id']}/exports"
    first = owner.post(endpoint, json={"revision": 1, "resolution": 720}).json()["id"]
    monkeypatch.setattr("app.media.remotion.REMOTION_RENDERER_VERSION", "next-test-version")
    second = owner.post(endpoint, json={"revision": 1, "resolution": 720}).json()["id"]
    assert first != second
    def unexpected_render(*args, **options):
        raise AssertionError("An old queued Remotion version must be rejected before rendering")
    monkeypatch.setattr("app.jobs.tasks.render_clip", unexpected_render)
    run_job(first)
    with database() as db:
        job = db.get(Job, first)
        assert job.status == "failed" and job.error_code == "remotion_version_changed"
        assert db.scalar(select(Export).where(Export.job_id == first)).status == "failed"
        assert db.get(Project, ready_project["project_id"]).status == "ready"


def test_render_job_uses_saved_style_and_passes_configured_node_paths(clients, ready_project, database, monkeypatch):
    from app.config import get_settings

    owner = clients[0]
    clip = create_clip(owner, ready_project["project_id"], {"renderer": "remotion", "remotion_template": "minimal", "enabled": False,
        "remotion_effects": {"transition_in": "fade", "intro": {"enabled": True, "text": "Intro tersimpan"},
                             "zooms": [{"start_ms": 500, "end_ms": 2000, "scale": 1.5}]}})
    saved_effects = clip["revision"]["subtitle_style_json"]["remotion_effects"]
    endpoint = f"/api/v1/clips/{clip['id']}"
    job_id = owner.post(endpoint + "/exports", json={"revision": 1, "resolution": 720}).json()["id"]
    assert owner.patch(endpoint, json={"expected_revision": 1, "subtitle_style_json": {"renderer": "ffmpeg"}}).status_code == 200
    monkeypatch.setattr(get_settings(), "remotion_node_path", "custom-node")
    monkeypatch.setattr(get_settings(), "remotion_script_path", "/custom/render.mjs")
    captured = []
    def controlled_render(source, directory, snapshot, config, **options):
        captured.append((snapshot, config, options))
        mp4, srt = directory / "result.mp4", directory / "captions.srt"
        mp4.write_bytes(b"controlled export, not an actual MP4")
        srt.write_text("Momen lucu", encoding="utf-8")
        return dict(mp4=mp4, srt=srt, meta={"renderer": "remotion"})
    monkeypatch.setattr("app.jobs.tasks.render_clip", controlled_render)
    run_job(job_id)
    assert len(captured) == 1
    snapshot, config, options = captured[0]
    assert snapshot["subtitle_style_json"]["renderer"] == "remotion"
    assert snapshot["subtitle_style_json"]["remotion_template"] == "minimal"
    assert snapshot["subtitle_style_json"]["enabled"] is False
    assert snapshot["subtitle_style_json"]["remotion_effects"] == saved_effects
    assert snapshot["subtitle_events"] == snapshot["cues"]
    assert config["renderer"] == "remotion" and config["renderer_version"] == REMOTION_RENDERER_VERSION
    assert options["remotion_node_path"] == "custom-node" and options["remotion_script_path"] == "/custom/render.mjs"
    with database() as db:
        assert db.get(Job, job_id).status == "succeeded"
        export = db.scalar(select(Export).where(Export.job_id == job_id))
        assert export.status == "ready" and export.mp4_asset_id and export.srt_asset_id


def test_effects_round_trip_overlap_dedup_and_trim_validation_with_subtitles_disabled(clients, ready_project):
    owner = clients[0]
    effects = {
        "transition_in": "slide", "transition_out": "fade", "transition_ms": 400,
        "intro": {"enabled": True, "text": "Awal pertarungan", "duration_ms": 1200},
        "outro": {"enabled": True, "text": "Sampai jumpa", "duration_ms": 1500},
        "zooms": [{"start_ms": 2000, "end_ms": 6000, "scale": 1.3, "x": .2, "y": .7},
                  {"start_ms": 3000, "end_ms": 4000, "scale": 1.6, "x": .8, "y": .3}],
    }
    clip = create_clip(owner, ready_project["project_id"], {"renderer": "remotion", "enabled": False, "remotion_effects": effects})
    endpoint = f"/api/v1/clips/{clip['id']}"
    assert clip["revision"]["subtitle_style_json"]["remotion_effects"] == effects
    first = owner.post(endpoint + "/exports", json={"revision": 1, "resolution": 720})
    assert first.status_code == 202
    assert owner.post(endpoint + "/exports", json={"revision": 1, "resolution": 720}).json()["id"] == first.json()["id"]
    # A shorter cut must not silently leave a zoom pointing beyond the clip.
    trimmed = owner.patch(endpoint, json={"expected_revision": 1, "end_ms": 6000})
    assert trimmed.status_code == 422 and "Zoom 1" in trimmed.text
    assert owner.get(endpoint).json()["revision"]["revision"] == 1
    effects["zooms"][0]["end_ms"] = 5000
    saved = owner.patch(endpoint, json={"expected_revision": 1, "end_ms": 6000,
        "subtitle_style_json": {"renderer": "remotion", "enabled": False, "remotion_effects": effects}})
    assert saved.status_code == 200 and saved.json()["revision"]["subtitle_style_json"]["remotion_effects"] == effects
    second = owner.post(endpoint + "/exports", json={"revision": 2, "resolution": 720})
    assert second.status_code == 202 and second.json()["id"] != first.json()["id"]


def test_invalid_effects_never_save_even_with_subtitles_disabled(clients, ready_project):
    owner = clients[0]
    clip = create_clip(owner, ready_project["project_id"])
    endpoint = f"/api/v1/clips/{clip['id']}"
    invalid_effects = [
        {"transition_in": "flash"}, {"transition_ms": 1001},
        {"intro": {"enabled": True, "text": "   "}},
        {"outro": {"enabled": True, "text": "x" * 81}},
        {"intro": {"enabled": True, "text": "control\u0000"}},
        {"intro": {"enabled": True, "text": "Valid", "duration_ms": 5001}},
        {"zooms": [{"start_ms": 2000, "end_ms": 2000}]},
        {"zooms": [{"start_ms": 0, "end_ms": 6001}]},
        {"zooms": [{"start_ms": 0, "end_ms": 1000, "scale": 2.1}]},
        {"zooms": [{"start_ms": 0, "end_ms": 1000, "x": -.1}]},
        {"zooms": [{"start_ms": 0, "end_ms": 1000}] * 21},
    ]
    for effects in invalid_effects:
        response = owner.patch(endpoint, json={"expected_revision": 1,
            "subtitle_style_json": {"renderer": "remotion", "enabled": False, "remotion_effects": effects}})
        assert response.status_code == 422, response.text
    assert owner.get(endpoint).json()["revision"]["revision"] == 1
    # Titles use Unicode code points, matching the renderer rather than UTF-16 units.
    unicode_title = owner.patch(endpoint, json={"expected_revision": 1,
        "subtitle_style_json": {"renderer": "remotion", "enabled": False,
            "remotion_effects": {"intro": {"enabled": True, "text": "\U0001f600" * 80}}}})
    assert unicode_title.status_code == 200, unicode_title.text


def test_export_revalidates_saved_hidden_effects(clients, ready_project, database):
    owner = clients[0]
    clip = create_clip(owner, ready_project["project_id"], {"renderer": "remotion", "enabled": False})
    endpoint = f"/api/v1/clips/{clip['id']}/exports"
    for effects in ({"zooms": [{"start_ms": 0, "end_ms": 7000}]}, {"intro": {"enabled": True, "text": ""}}):
        with database() as db:
            revision = db.get(ClipRevision, clip["revision"]["id"])
            revision.subtitle_style_json = {**revision.subtitle_style_json, "remotion_effects": effects}
            db.commit()
        assert owner.post(endpoint, json={"revision": 1, "resolution": 720}).status_code == 422
    with database() as db:
        assert db.scalar(select(Export).where(Export.clip_revision_id == clip["revision"]["id"])) is None
