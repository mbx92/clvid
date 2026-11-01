import pytest

from app.media.speaker_tracking import ActiveSpeakerSelector, plan_speaker_crop


def face(identity, x, score, width=.18, **extra):
    return {"id": identity, "box": (x, .2, width, .3), "eyes_y": .31, "speaker_score": score, **extra}


def test_confident_handoff_survives_short_audio_pause_without_forced_alternation():
    selector = ActiveSpeakerSelector()
    assert selector.step(0, [face(1, .1, .95), face(2, .7, .05)], True) == 1
    for t in range(160, 1600, 160):
        selector.step(t, [face(1, .1, .95), face(2, .7, .05)], True)
    for t in range(1600, 2880, 160):
        selector.step(t, [face(1, .1, .05), face(2, .7, .96)], t not in (2080, 2240))
    assert selector.target_id == 2 and selector.switches == 1
    for t in range(2880, 10000, 160):
        selector.step(t, [face(1, .1, .05), face(2, .7, .96)], True)
    assert selector.target_id == 2 and selector.switches == 1


def test_silent_head_motion_and_appearance_do_not_become_speaker_scores():
    selector = ActiveSpeakerSelector()
    selector.step(0, [face(1, .1, .9), face(2, .7, .1)], True)
    for t in range(160, 4000, 160):
        selector.step(t, [face(1, .1, .85, activity=.001), face(2, .7, .12, activity=1000)], True)
    assert selector.target_id == 1 and selector.switches == 0
    for t in range(4000, 6000, 160):
        selector.step(t, [face(1, .1, .05), face(2, .7, .99)], False)
    assert selector.target_id == 1 and selector.switches == 0


def test_overlap_and_single_frame_spike_keep_current_composition():
    selector = ActiveSpeakerSelector()
    selector.step(0, [face(1, .1, .95), face(2, .7, .01)], True)
    for t in range(160, 2400, 160):
        selector.step(t, [face(1, .1, .85), face(2, .7, .93)], True)
    selector.step(2400, [face(1, .1, .01), face(2, .7, 1.)], True)
    for t in range(2560, 4000, 160):
        selector.step(t, [face(1, .1, .9), face(2, .7, .1)], True)
    assert selector.target_id == 1 and selector.switches == 0


@pytest.mark.parametrize("silence", [True, False])
def test_evidence_held_during_minimum_dwell_cannot_switch_after_support_ends(silence):
    selector = ActiveSpeakerSelector()
    selector.step(0, [face(1, .1, 0, width=.2), face(2, .7, 0)], True)
    for t in range(160, 801, 160):
        selector.step(t, [face(1, .1, 0, width=.2), face(2, .7, 1)], True)
    assert selector.target_id == 1 and selector.evidence[2] >= 400
    faces = [face(1, .1, 0 if silence else 1, width=.2), face(2, .7, 1 if silence else 0)]
    selector.step(960, faces, not silence)
    assert selector.target_id == 1 and selector.switches == 0


def test_shot_cut_resets_evidence_and_does_not_count_as_speaker_handoff():
    selector = ActiveSpeakerSelector()
    selector.step(0, [face(1, .1, .95), face(2, .7, .01)], True)
    selector.step(160, [face(1, .1, .01), face(2, .7, .99)], True)
    assert selector.step(320, [face(8, .7, .99)], True, shot_cut=True) == 8
    assert selector.switches == 0 and selector.evidence == {}


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -.1, 2., "1", True])
def test_invalid_model_probability_is_not_accepted_as_speech(invalid):
    selector = ActiveSpeakerSelector()
    for t in range(0, 4000, 160):
        selector.step(t, [face(1, .1, .8, width=.2), face(2, .7, invalid)], True)
    assert selector.target_id == 1 and selector.switches == 0


def test_crop_path_uses_model_handoff_and_preserves_observations():
    observations = [{"t_ms": t, "audio_active": True, "cut": False,
                     "faces": [face(1, .1, 0), face(2, .7, 0)]} for t in range(0, 5000, 160)]
    scores = {(index, identity): .95 if (row["t_ms"] < 2000) == (identity == 1) else .05
              for index, row in enumerate(observations) for identity in (1, 2)}
    path, switches = plan_speaker_crop(observations, scores, aspect=16 / 9, fallback=(.5, .5), duration_ms=5000)
    assert switches == 1 and path[0]["x"] < .1 and path[-1]["x"] > .9
    assert path[-1]["t_ms"] == 5000
    assert any(frame["cut"] and frame["x"] > .9 for frame in path[1:])
    assert all(face["speaker_score"] == 0 for row in observations for face in row["faces"])
