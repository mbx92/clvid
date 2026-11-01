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
