from copy import deepcopy

import pytest

from app.media.render import render_clip, reusable_tracking_result
from app.media.tracking_versions import SPEAKER_METHOD

CROP = {"mode": "fill", "tracking": "face", "x": .25, "y": .5}


def framing():
    return {"mode": "face", "method": "yunet-face-v1", "fallback_reason": None,
            "warnings": [], "detected_frames": 30, "total_frames": 30,
            "keyframes": [{"t_ms": 0, "x": .1, "y": .5, "cut": True},
                          {"t_ms": 5000, "x": .9, "y": .5, "cut": False}]}


def test_reusable_path_is_deep_copied_and_preserves_cut_snapshot():
    original = framing()
    result = reusable_tracking_result(original, CROP, 5000)
    assert result == original and result is not original
    result["keyframes"][0]["x"] = .4
    result["warnings"].append("Only the rendered copy changes")
    assert original["keyframes"][0]["x"] == .1 and original["warnings"] == []


def test_completed_no_face_run_is_reusable_but_infrastructure_failure_is_not():
    negative = framing()
    negative.update(detected_frames=0, fallback_reason="Wajah tidak terdeteksi; posisi manual digunakan.")
    assert reusable_tracking_result(negative, CROP, 5000) == negative
    negative["method"] = "manual"
    assert reusable_tracking_result(negative, CROP, 5000) is None


def test_old_speaker_heuristic_is_never_reused_as_current_audiovisual_analysis():
    crop = {**CROP, "tracking": "speaker"}
    current = {**framing(), "mode": "speaker", "method": SPEAKER_METHOD}
    assert reusable_tracking_result(current, crop, 5000) == current
    for old_method in ("yunet-mouth-motion-audio-v1", "manual", "light-asd-v1"):
        assert reusable_tracking_result({**current, "method": old_method}, crop, 5000) is None


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(mode="speaker"),
    lambda value: value.update(method="manual"),
    lambda value: value.update(fallback_reason="Model tidak tersedia"),
    lambda value: value.update(total_frames=0),
    lambda value: value.update(detected_frames=-1),
    lambda value: value.update(detected_frames=31),
    lambda value: value.update(detected_frames=False),
    lambda value: value.update(detected_frames=0, fallback_reason="Pelacakan tidak dapat diselesaikan; posisi manual digunakan."),
    lambda value: value.update(keyframes=[]),
    lambda value: value["keyframes"][0].update(t_ms=1),
    lambda value: value["keyframes"][0].update(t_ms=False),
    lambda value: value["keyframes"][1].update(t_ms=0),
    lambda value: value["keyframes"][1].update(t_ms=5001),
    lambda value: value["keyframes"][1].update(t_ms=4.5),
    lambda value: value["keyframes"][0].update(x=float("nan")),
    lambda value: value["keyframes"][0].update(y=float("inf")),
    lambda value: value["keyframes"][0].update(x=10**1000),
    lambda value: value["keyframes"][0].update(x=-.01),
    lambda value: value["keyframes"][0].update(x=True),
    lambda value: value["keyframes"][0].update(x="0; movie=secret"),
    lambda value: value["keyframes"][0].update(cut="false"),
    lambda value: value.update(keyframes=[{"t_ms": i, "x": .5, "y": .5} for i in range(100)]),
])
def test_malformed_cached_path_is_rejected(mutation):
    result = framing()
    mutation(result)
    assert reusable_tracking_result(result, CROP, 5000) is None


@pytest.mark.parametrize("crop", [{**CROP, "mode": "fit"}, {**CROP, "tracking": "static"}, {"mode": "fill", "x": .5, "y": .5}])
def test_static_fit_and_legacy_modes_never_consume_cached_path(crop):
    assert reusable_tracking_result(framing(), crop, 5000) is None


def test_invalid_cached_path_reanalyzes_with_controlled_media_adapter(tmp_path, monkeypatch):
    """Control codec work here; real crop and subtitle pixels are integration-tested."""
    source = tmp_path / "source.mp4"
    source.write_bytes(b"controlled fixture")
    metadata = {"duration_ms": 5000, "width": 720, "height": 1280, "video_codec": "h264", "audio_codec": "aac"}
    monkeypatch.setattr("app.media.render.probe", lambda *a, **kw: metadata.copy())
    monkeypatch.setattr("app.media.render.check_disk", lambda *a, **kw: None)
    def write_output(args, **kwargs):
        from pathlib import Path
        Path(args[-1]).write_bytes(b"controlled output, not an actual MP4")
    monkeypatch.setattr("app.media.render.ffmpeg", write_output)
    calls = []
    def analyze(*args, **kwargs):
        calls.append(kwargs)
        return framing()
    monkeypatch.setattr("app.media.render.track_clip", analyze)
    malformed = framing()
    malformed["keyframes"][0]["x"] = "filter-injection"
    stages = []
    speaker_model = tmp_path / "speaker.onnx"
    result = render_clip(source, tmp_path, {"start_ms": 0, "end_ms": 5000, "crop_json": CROP,
                         "subtitle_style_json": {"enabled": False}}, {"width": 720},
                         tracking_result=malformed, stage=stages.append, speaker_model_path=speaker_model)
    assert len(calls) == 1 and stages == ["track_faces", "render"]
    assert calls[0]["speaker_model_path"] == speaker_model
    assert result["meta"]["framing"]["analysis_reused"] is False
    assert "filter-injection" not in (tmp_path / "tracking.cmd").read_text()
