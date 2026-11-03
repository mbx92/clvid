import pytest

from app.media.process import MediaError
from app.media.render import framing_filter
from app.media.subtitles import caption_layout, escape_ass, local_cues, retime_cues, to_ass, to_srt, transcript_cues


def test_manual_subtitle_size_is_not_silently_shrunk_and_styles_reach_ass():
    text = "Ukuran teks berubah sesuai pilihan"
    _, automatic = caption_layout(text, 100)
    wrapped, manual = caption_layout(text, 100, auto_fit=False)
    assert automatic < 100 and manual == 100
    assert len(wrapped.splitlines()) <= 4 and wrapped.replace('\n', ' ') == text
    cues = [{"start_ms": 0, "end_ms": 5000, "text": text}]
    style = {"font_size": 100, "auto_fit": False, "bold": True, "italic": True,
             "uppercase": True, "text_color": "#FFE600", "outline_color": "#123456",
             "outline_width": 5, "shadow": 4, "background": False}
    ass = to_ass(cues, 5000, style, 720, 1280)
    assert r'{\fs67}' in ass and 'UKURAN' in ass
    assert '&H0000E6FF' in ass and '&H00563412' in ass
    assert ',-1,-1,0,0,' in ass and ',1,3.33,2.67,' in ass
    assert text in to_srt(cues, 5000)  # Presentation does not rewrite the transcript/SRT.
    with pytest.raises(MediaError, match='empat baris'):
        caption_layout('subtitle panjang ' * 30, 100, auto_fit=False)


def test_subtitle_style_rejects_ass_injection_and_out_of_range_effects():
    from app.api.schemas import SubtitleStyle
    from pydantic import ValidationError
    for change in ({'text_color':'#FFF'}, {'outline_color':r'{\p1}'}, {'shadow':99}, {'outline_width':-1}):
        with pytest.raises(ValidationError):
            SubtitleStyle(**change)


def test_trim_intersection_keeps_edited_text_and_clamps():
    edited = [{"start_ms": 0, "end_ms": 4000, "text": "Koreksi pengguna"},
              {"start_ms": 4500, "end_ms": 7000, "text": "Kesimpulan"}]
    moved = retime_cues(edited, 10000, 12000, 16000)
    assert moved == [{"start_ms": 0, "end_ms": 2000, "text": "Koreksi pengguna"},
                     {"start_ms": 2500, "end_ms": 4000, "text": "Kesimpulan"}]


def test_srt_clamp_and_escape_user_instructions():
    cues = [{"start_ms": -200, "end_ms": 9000, "text": '<script>alert("x")</script>\n\n1 --> x'}]
    result = to_srt(cues, 5000)
    assert "00:00:00,000 --> 00:00:05,000" in result
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "\n\n1 -->" not in result


def test_ass_override_and_line_injection_is_display_text():
    unsafe = r"{\p1}m 0 0 l 500 500{\p0}" + "\nDialogue: fake"
    escaped = escape_ass(unsafe)
    assert "{" not in escaped and "}" not in escaped
    assert r"\p1" not in escaped
    result = to_ass([{"start_ms": 0, "end_ms": 5000, "text": unsafe}], 5000, {})
    assert len([line for line in result.splitlines() if line.startswith("Dialogue:")]) == 1


def test_cover_and_contain_follow_alignment_contract():
    assert "(iw-ow)*1.000000" in framing_filter({"mode": "fill", "x": 1, "y": .5}, 720, 1280)
    assert "force_original_aspect_ratio=decrease" in framing_filter({"mode": "fit"}, 720, 1280)
    with pytest.raises(MediaError):
        framing_filter({"x": -1}, 720, 1280)


def test_no_outside_source_segments_become_cues():
    assert local_cues([{"start_ms": 0, "end_ms": 1000, "text": "before"},
                       {"start_ms": 10000, "end_ms": 11000, "text": "after"}], 2000, 7000) == []


def test_long_text_is_rejected_instead_of_tiny_or_clipped_burn_in():
    with pytest.raises(MediaError) as error:
        caption_layout("kalimat terlalu panjang " * 30, 52)
    assert error.value.code == "subtitle_too_long"
    lines, size = caption_layout("Ini subtitle dengan panjang sedang dan tetap terbaca pada dua baris.", 52)
    assert len(lines.splitlines()) == 2 and 24 <= size <= 52


def test_auto_cue_split_uses_observed_word_timestamps():
    words = [{"word": f" kata{i}", "start_ms": i * 300, "end_ms": i * 300 + 250} for i in range(30)]
    original = {"start_ms": 0, "end_ms": 9000, "text": "".join(word["word"] for word in words).strip(), "words_json": words}
    cues = transcript_cues([original], 0, 9000)
    assert len(cues) > 1
    assert " ".join(cue["text"] for cue in cues) == original["text"]
    assert all(cue["start_ms"] in {word["start_ms"] for word in words} and cue["end_ms"] in {word["end_ms"] for word in words} for cue in cues)
    assert transcript_cues([{**original, "words_json": None}], 0, 9000) == [{key: original[key] for key in ("start_ms", "end_ms", "text")}]


def test_short_automatic_sentence_does_not_bridge_a_long_silent_gap():
    from app.media.word_captions import align_words
    words = [{"word": " Oh", "start_ms": 22880, "end_ms": 23680},
             {"word": " dikit", "start_ms": 41840, "end_ms": 42080},
             {"word": " lagi", "start_ms": 42080, "end_ms": 42260}]
    segment = {"start_ms": 22880, "end_ms": 42260, "text": "Oh dikit lagi", "words_json": words}
    cues = transcript_cues([segment], 0, 45000)
    assert cues == [{"start_ms": 22880, "end_ms": 23680, "text": "Oh"},
                    {"start_ms": 41840, "end_ms": 42260, "text": "dikit lagi"}]
    assert not any(cue["start_ms"] <= 30000 < cue["end_ms"] for cue in cues)
    events, missing = align_words(cues, words, 0)
    assert missing == 0 and len(events) == 3
    assert " ".join(event["text"] for event in events) == segment["text"]


@pytest.mark.parametrize("gap,groups", [(999, 1), (1000, 2)])
def test_automatic_sentence_splits_at_one_second_word_gap(gap, groups):
    words = [{"word": " Awas", "start_ms": 100, "end_ms": 500},
             {"word": " boss", "start_ms": 500 + gap, "end_ms": 900 + gap}]
    segment = {"start_ms": 0, "end_ms": 3000, "text": "Awas boss", "words_json": words}
    cues = transcript_cues([segment], 0, 3000)
    assert len(cues) == groups
    assert cues[0]["start_ms"] == 100 and cues[-1]["end_ms"] == 900 + gap


def test_short_contiguous_sentence_is_split_into_at_most_five_second_cues():
    from app.media.word_captions import align_words
    words = [{"word": f" k{i}", "start_ms": i * 800, "end_ms": (i + 1) * 800} for i in range(14)]
    segment = {"start_ms": 0, "end_ms": 11200, "text": "".join(w["word"] for w in words).strip(), "words_json": words}
    assert len(segment["text"]) < 85
    cues = transcript_cues([segment], 0, 11200)
    assert len(cues) == 3
    assert all(0 < cue["end_ms"] - cue["start_ms"] <= 5000 for cue in cues)
    assert " ".join(cue["text"] for cue in cues) == segment["text"]
    events, missing = align_words(cues, words, 0)
    assert missing == 0 and len(events) == len(words)


def test_elongated_single_word_keeps_observed_duration_without_joining_following_speech():
    words = [{"word": " Nooo!", "start_ms": 0, "end_ms": 6000},
             {"word": " Awas", "start_ms": 6100, "end_ms": 6500}]
    segment = {"start_ms": 0, "end_ms": 6500, "text": "Nooo! Awas", "words_json": words}
    assert transcript_cues([segment], 0, 6500) == [
        {"start_ms": 0, "end_ms": 6000, "text": "Nooo!"},
        {"start_ms": 6100, "end_ms": 6500, "text": "Awas"}]


@pytest.mark.parametrize("start,end,expected", [
    (1000, 3000, [{"start_ms": 0, "end_ms": 1900, "text": "dunia seru!"}]),
    (0, 1000, [{"start_ms": 100, "end_ms": 800, "text": "Halo"}]),
    (1200, 1800, [{"start_ms": 0, "end_ms": 600, "text": "dunia"}]),
    (800, 1000, []),  # A segment overlaps, but this window contains only silence.
])
def test_auto_cues_at_visual_boundaries_match_overlapping_words(start, end, expected):
    from app.media.word_captions import align_words
    words = [{"word": " Halo", "start_ms": 100, "end_ms": 800},
             {"word": " dunia", "start_ms": 1000, "end_ms": 2000},
             {"word": " seru!", "start_ms": 2200, "end_ms": 2900}]
    segment = {"start_ms": 0, "end_ms": 3000, "text": "Halo dunia seru!", "words_json": words}
    cues = transcript_cues([segment], start, end)
    assert cues == expected
    events, missing = align_words(cues, words, start)
    assert missing == 0
    assert bool(events) == bool(expected)
    assert all(0 <= cue["start_ms"] < cue["end_ms"] <= end-start for cue in events)
    assert segment["text"] == "Halo dunia seru!" and len(segment["words_json"]) == 3


def test_trimmed_long_auto_cues_keep_only_overlapping_words_and_valid_timing():
    from app.media.word_captions import align_words
    words = [{"word": f" kata{i}", "start_ms": i*300, "end_ms": i*300+250} for i in range(40)]
    segment = {"start_ms": 0, "end_ms": 12000, "text": "".join(w["word"] for w in words).strip(), "words_json": words}
    cues = transcript_cues([segment], 1300, 10700)
    expected_words = [w for w in words if w["end_ms"] > 1300 and w["start_ms"] < 10700]
    assert len(cues) > 1
    assert " ".join(cue["text"] for cue in cues) == "".join(w["word"] for w in expected_words).strip()
    events, missing = align_words(cues, words, 1300)
    assert missing == 0 and len(events) == len(expected_words)
    assert all(0 <= cue["start_ms"] < cue["end_ms"] <= 9400 for cue in events)


@pytest.mark.parametrize("words", [None, [], [{"word": " Halo"}],
    [{"word": " Halo", "start_ms": 0, "end_ms": 0}]])
def test_auto_cues_without_valid_word_timing_preserve_transcript_text(words):
    segment = {"start_ms": 0, "end_ms": 2000, "text": "Halo dunia", "words_json": words}
    assert transcript_cues([segment], 1000, 2000) == [
        {"start_ms": 0, "end_ms": 1000, "text": "Halo dunia"}]
