import pytest
from pydantic import ValidationError
from app.story.captions import has_timed_captions, scene_captions, story_captions
from app.story.schemas import Document, Scene
from app.media.subtitles import to_srt


def aligned_scene(**changes):
    return {"id": "one", "narration": "Awal. Akhir.", "duration_ms": 3000,
            "audio_id": "voice", "caption_audio_id": "voice", "caption_narration": "Awal. Akhir.",
            "show_caption": True, "captions": [
                {"start_ms": 300, "end_ms": 800, "text": "Awal."},
                {"start_ms": 2200, "end_ms": 2800, "text": "Akhir."}], **changes}


def test_real_caption_times_preserve_pauses_and_offset_with_scene_order():
    doc = Document(scenes=[{"id": "intro", "duration_ms": 1000, "narration": "Intro.", "show_caption": False}, aligned_scene()]).model_dump()
    cues = story_captions(doc)
    assert cues == [{"start_ms": 1300, "end_ms": 1800, "text": "Awal."},
                    {"start_ms": 3200, "end_ms": 3800, "text": "Akhir."}]
    assert "00:00:03,200 --> 00:00:03,800" in to_srt(cues, 4000)
    # Exporting does not modify scene-local timestamps.
    assert doc["scenes"][1]["captions"][0]["start_ms"] == 300


@pytest.mark.parametrize("changes", [{"audio_id": "another-voice"}, {"audio_id": None},
                                      {"narration": "Naskah diubah."}, {"caption_narration": ""}])
def test_stale_audio_or_text_never_reuses_previous_alignment(changes):
    scene = Scene.model_validate(aligned_scene(**changes)).model_dump()
    assert not has_timed_captions(scene)
    assert scene_captions(scene) == [{"start_ms": 0, "end_ms": 3000, "text": scene["narration"]}]


def test_hidden_captions_are_omitted_for_timed_and_legacy_documents():
    assert scene_captions(aligned_scene(show_caption=False)) == []
    assert scene_captions({"duration_ms": 1000, "narration": "Rahasia", "show_caption": False}) == []


def test_legacy_documents_keep_evenly_distributed_unicode_chunks():
    text = "a" * 60 + " " + "\U0001f600" * 5 + " akhir"
    scene = {"duration_ms": 1100, "narration": text, "show_caption": True}
    assert scene_captions(scene) == [
        {"start_ms": 0, "end_ms": 567, "text": "a" * 60},
        {"start_ms": 567, "end_ms": 1100, "text": "\U0001f600" * 5 + " akhir"}]
    assert scene_captions({**scene, "narration": ""}) == []
    assert Scene(id="old").captions == []


@pytest.mark.parametrize("cue", [
    {"start_ms": -1, "end_ms": 200, "text": "x"},
    {"start_ms": 200, "end_ms": 200, "text": "x"},
    {"start_ms": 200, "end_ms": 3001, "text": "x"},
    {"start_ms": 200, "end_ms": 500, "text": " "},
    {"start_ms": 200, "end_ms": 500, "text": "x" * 201},
    {"start_ms": "200", "end_ms": 500, "text": "x"},
    {"start_ms": True, "end_ms": 500, "text": "x"},
    {"start_ms": 200, "end_ms": 500, "text": "x", "html": "<b>"},
])
def test_invalid_caption_data_rejected(cue):
    with pytest.raises(ValidationError):
        Scene.model_validate(aligned_scene(captions=[cue]))


def test_captions_cannot_overlap_overrun_shortened_scene_or_exceed_limit():
    original = aligned_scene()
    for changes in [
        {"captions": [*original["captions"], {"start_ms": 2700, "end_ms": 2900, "text": "overlap"}]},
        {"duration_ms": 2000},
        {"captions": [{"start_ms": i, "end_ms": i + 1, "text": "x"} for i in range(201)]},
    ]:
        with pytest.raises(ValidationError):
            Scene.model_validate({**original, **changes})
