from pathlib import Path

import pytest

from app.media.process import Cancelled, ProcessResult
from app.media.tracking import CropPlanner, FaceAssociator, crop_for_face, track_clip, write_tracking_commands


def face(identity, x, activity=0., width=.16):
    return {"id": identity, "box": (x, .2, width, .3), "eyes_y": .31, "activity": activity}


def test_crop_coordinates_are_alignment_not_face_center():
    left = crop_for_face(face(1, .08), 16 / 9)
    right = crop_for_face(face(2, .75), 16 / 9)
    assert left[0] < .1 and right[0] > .95
    assert left[1] == right[1] == .5


def test_geometric_track_survives_detector_order_change():
    associator = FaceAssociator()
    first = associator.update([(.1, .2, .15, .3), (.7, .2, .15, .3)], 0)
    second = associator.update([(.71, .2, .15, .3), (.11, .2, .15, .3)], 167)
    assert second == list(reversed(first))
    associator.reset()
    assert associator.update([(.1, .2, .15, .3)], 1000)[0] not in first


def test_speaker_switch_requires_audio_and_sustained_motion():
    planner = CropPlanner("speaker", 16 / 9, (.5, .5))
    first = planner.step(0, [face(1, .1, width=.2), face(2, .72)], False)
    for t in range(200, 2000, 200):
        current = planner.step(t, [face(1, .1, width=.2), face(2, .72, .15)], False)
    assert planner.target_id == 1 and planner.speaker_switches == 0
    for t in range(2000, 3000, 200):
        current = planner.step(t, [face(1, .1, .002, width=.2), face(2, .72, .15)], True)
    assert planner.target_id == 2 and planner.speaker_switches == 1
    assert current["x"] > first["x"] + .5


def test_face_follows_smoothly_and_holds_brief_dropout():
    planner = CropPlanner("face", 16 / 9, (.5, .5))
    first = planner.step(0, [face(1, .1)], True)
    moved = planner.step(167, [face(1, .2)], True)
    assert first["x"] < moved["x"] < crop_for_face(face(1, .2), 16 / 9)[0]
    dropout = planner.step(334, [], False)
    assert dropout["x"] == moved["x"]
    fallback = planner.step(1600, [], False)
    assert fallback["x"] > moved["x"]


def test_shot_change_resets_without_sweeping_between_faces():
    planner = CropPlanner("face", 16 / 9, (.5, .5))
    planner.step(0, [face(1, .1)], False)
    cut = planner.step(167, [face(2, .75)], False, shot_cut=True)
    assert cut["cut"] and cut["x"] > .9


def test_dynamic_crop_commands_use_clip_local_time_and_cut_hold(tmp_path):
    path = tmp_path / "tracking.cmd"
    write_tracking_commands(path, [{"t_ms": 0, "x": .1, "y": .5}, {"t_ms": 1000, "x": .8, "y": .5, "cut": True}])
    lines = path.read_text().splitlines()
    assert lines[0].startswith("0.000") and "(iw-ow)*0.100000" in lines[0]
    assert lines[1].startswith("1.000") and "(iw-ow)*0.800000" in lines[1]


def test_missing_model_falls_back_explicitly_without_media_work(tmp_path):
    result = track_clip(tmp_path / "source.mp4", tmp_path, start_ms=0, end_ms=5000,
                        crop={"mode": "fill", "tracking": "speaker", "x": .25, "y": .7},
                        ffmpeg_bin="never-called", model_path=tmp_path / "missing.onnx")
    assert result["mode"] == "speaker" and result["method"] == "manual"
    assert result["fallback_reason"] and result["keyframes"][0]["x"] == .25
    assert result["keyframes"][0]["y"] == .7


def test_cancellation_does_not_turn_into_a_successful_static_render(tmp_path, monkeypatch):
    model = tmp_path / "test.onnx"
    model.write_bytes(b"controlled test placeholder")
    def cancel(*args, **kwargs):
        raise Cancelled()
    monkeypatch.setattr("app.media.tracking.ffmpeg", cancel)
    with pytest.raises(Cancelled):
        track_clip(tmp_path / "source.mp4", tmp_path, start_ms=0, end_ms=5000,
                   crop={"mode": "fill", "tracking": "face"}, ffmpeg_bin="unused", model_path=model)


def test_speaker_model_missing_is_explicit_before_video_work(tmp_path):
    model = tmp_path / "yunet.onnx"
    model.write_bytes(b"controlled detector placeholder")
    result = track_clip(tmp_path / "source.mp4", tmp_path, start_ms=0, end_ms=5000,
                        crop={"mode": "fill", "tracking": "speaker", "x": .2, "y": .6}, ffmpeg_bin="never-called",
                        model_path=model, speaker_model_path=tmp_path / "missing-asd.onnx")
    assert result["method"] == "manual" and "audiovisual" in result["fallback_reason"]
    assert result["keyframes"][0]["x"] == .2


def test_speaker_inference_failure_is_disclosed_instead_of_pixel_motion_fallback(tmp_path, monkeypatch):
    import json
    model, speaker = tmp_path / "yunet.onnx", tmp_path / "speaker.onnx"
    model.write_bytes(b"controlled detector placeholder")
    speaker.write_bytes(b"controlled audiovisual placeholder")
    commands = []
    monkeypatch.setattr("app.media.tracking.ffmpeg", lambda args, **kwargs: commands.append(args))
    monkeypatch.setattr("app.media.tracking.run_process", lambda *args, **kwargs: ProcessResult("", "Controlled failure", 1))
    result = track_clip(tmp_path / "source.mp4", tmp_path, start_ms=0, end_ms=5000,
                        crop={"mode": "fill", "tracking": "speaker"}, ffmpeg_bin="unused",
                        model_path=model, speaker_model_path=speaker)
    request = json.loads((tmp_path / "tracking-input.json").read_text())
    assert request["sample_fps"] == 6 and request["speaker_model_sha256"]
    assert "fps=25" in commands[0][commands[0].index("-vf") + 1]
    assert result["method"] == "manual" and result["fallback_reason"]


def test_face_tracking_keeps_six_fps_and_has_no_speaker_model_dependency(tmp_path, monkeypatch):
    import json
    model = tmp_path / "yunet.onnx"
    model.write_bytes(b"controlled detector placeholder")
    commands = []
    monkeypatch.setattr("app.media.tracking.ffmpeg", lambda args, **kwargs: commands.append(args))
    def controlled_child(args, **kwargs):
        request = json.loads(Path(args[-1]).read_text())
        assert request["speaker_model"] is None and request["speaker_model_sha256"] is None
        Path(request["output"]).write_text(json.dumps({"mode": "face", "method": "yunet-face-v1", "keyframes": [{"t_ms": 0, "x": .5, "y": .5}]}))
        return ProcessResult("", "", 0)
    monkeypatch.setattr("app.media.tracking.run_process", controlled_child)
    result = track_clip(tmp_path / "source.mp4", tmp_path, start_ms=0, end_ms=5000,
                        crop={"mode": "fill", "tracking": "face"}, ffmpeg_bin="unused",
                        model_path=model, speaker_model_path=tmp_path / "absent.onnx")
    assert "fps=6" in commands[0][commands[0].index("-vf") + 1]
    assert result["method"] == "yunet-face-v1"
