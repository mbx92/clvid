import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.schemas import SubtitleStyle
from app.media.process import MediaError
from app.media.subtitles import animation_tags, caption_layout, to_ass, to_srt


def test_browser_export_line_layout_shared_contract():
    fixtures = json.loads((Path(__file__).parents[1] / 'fixtures/subtitle-layout.json').read_text())
    for case in fixtures:
        assert caption_layout(case['text'], case['size'], case['auto']) == (case['wrapped'], case['effective'])


def test_animation_defaults_keep_existing_exports_static_and_validate_options():
    assert SubtitleStyle().animation == 'none'
    assert animation_tags({}, 2000, 720, 1280) == ''
    for change in ({'animation': r'{\p1}'}, {'animation_ms': 99}, {'animation_ms': 501}):
        with pytest.raises(ValidationError):
            SubtitleStyle(**change)
    with pytest.raises(MediaError):
        animation_tags({'animation': 'invented'}, 2000, 720, 1280)


def test_effect_timing_is_clamped_for_short_words_and_coordinates_scale():
    assert animation_tags({'animation': 'fade', 'animation_ms': 300}, 1500, 720, 1280) == r'\fad(300,150)'
    assert animation_tags({'animation': 'fade', 'animation_ms': 300}, 90, 720, 1280) == r'\fad(30,30)'
    assert animation_tags({'animation': 'pop', 'animation_ms': 160}, 1500, 720, 1280) == r'\fad(60,150)\fscx85\fscy85\t(0,160,\fscx100\fscy100)'
    assert r'\move(360,1104,360,1088,0,220)' in animation_tags({'animation': 'rise', 'animation_ms': 220}, 1500, 720, 1280)
    assert r'\move(540,264,540,288,0,220)' in animation_tags({'animation': 'rise', 'animation_ms': 220, 'position': 'top'}, 1500, 1080, 1920)


def test_animation_is_applied_per_clamped_cue_and_never_to_srt_text():
    cues = [{'start_ms': -100, 'end_ms': 400, 'text': r'Jangan {\t(0,10)}'}]
    ass = to_ass(cues, 200, {'animation': 'pop', 'animation_ms': 300})
    assert r'\t(0,66,\fscx100\fscy100)' in ass
    assert r'\t(0,10)' not in ass
    assert r'\fad' not in to_srt(cues, 200)
