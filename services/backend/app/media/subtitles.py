import html
import re
import textwrap

from .process import MediaError


def local_cues(segments, start_ms, end_ms):
    result = []
    for item in segments:
        a, b = max(start_ms, item["start_ms"]), min(end_ms, item["end_ms"])
        if b > a and item["text"].strip():
            result.append(dict(start_ms=a-start_ms, end_ms=b-start_ms, text=item["text"]))
    return result


def retime_cues(cues, old_start, new_start, new_end):
    return local_cues([dict(c, start_ms=c["start_ms"]+old_start, end_ms=c["end_ms"]+old_start)
                       for c in cues], new_start, new_end)


def timestamp(ms, ass=False):
    hours, rem = divmod(max(0, int(ms)), 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours}:{minutes:02}:{seconds:02}.{millis//10:02}" if ass else f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def to_srt(cues, duration_ms):
    blocks = []
    for i, c in enumerate(local_cues(cues, 0, duration_ms), 1):
        text = html.escape(re.sub(r"\s+", " ", c["text"]).strip(), quote=False)
        blocks.append(f"{i}\n{timestamp(c['start_ms'])} --> {timestamp(c['end_ms'])}\n{text}\n")
    return "\n".join(blocks)


def escape_ass(text):
    return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\r", "").replace("\n", r"\N")


def caption_layout(text, font_size=52, auto_fit=True):
    text = " ".join(text.split())
    for size in range(font_size, 23, -1) if auto_fit else [font_size]:
        # Conservative Noto Sans average glyph width; explicit wrapping avoids
        # libass changing the line count between preview and export.
        width = max(1, int(900 / (size * .57)))
        lines = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
        if len(lines) <= (2 if auto_fit else 4) and all(len(line) <= width for line in lines):
            return "\n".join(lines), size
    raise MediaError("subtitle_too_long", "Subtitle terlalu panjang untuk dua baris." if auto_fit
                     else "Subtitle terlalu panjang untuk empat baris; pisahkan cue atau kecilkan ukuran teks.")


def validate_subtitle_layout(cues, style):
    if not style.get("enabled", True):
        return
    for cue in cues:
        text = cue["text"].upper() if style.get("uppercase") else cue["text"]
        caption_layout(text, style.get("font_size", 52), style.get("auto_fit", True))


def to_ass(cues, duration_ms, style, width=1080, height=1920):
    def color(value):
        if not re.fullmatch(r"#[a-fA-F0-9]{6}", value):
            raise MediaError("invalid_subtitle_style", "Warna subtitle tidak valid.")
        return "&H00" + value[5:7] + value[3:5] + value[1:3]
    scale = width / 1080
    primary = color(style.get("text_color", "#FFFFFF"))
    outline = color(style.get("outline_color", "#111111"))
    background = color(style.get("background_color", "#000000"))
    bold, italic = (-1 if style.get(k) else 0 for k in ("bold", "italic"))
    border = 3 if style.get("background", True) else 1
    edge, shadow = style.get("outline_width", 2.5)*scale, style.get("shadow", 0)*scale
    alignment = 8 if style.get("position") == "top" else 2
    margin = round(height * style.get("safe_margin", .15))
    header = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n"
              "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
              f"Style: Default,Noto Sans,{round(52*scale)},{primary},{primary},{outline},{background},{bold},{italic},0,0,100,100,0,0,{border},{edge:.2f},{shadow:.2f},{alignment},{round(60*scale)},{round(60*scale)},{margin},1\n"
              "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    rows = []
    for cue in local_cues(cues, 0, duration_ms):
        text = cue["text"].upper() if style.get("uppercase") else cue["text"]
        text, size = caption_layout(text, style.get("font_size", 52), style.get("auto_fit", True))
        rows.append(f"Dialogue: 0,{timestamp(cue['start_ms'], True)},{timestamp(cue['end_ms'], True)},Default,,0,0,0,,{{\\fs{round(size*scale)}}}{escape_ass(text)}")
    return header + "\n".join(rows) + "\n"


def transcript_cues(segments, start_ms, end_ms):
    output = []
    for seg in segments:
        words = seg.get("words_json")
        if not words or len(seg["text"]) <= 85:
            output.append(seg)
            continue
        group = []
        for word in words:
            if group and (len("".join(w["word"] for w in group)) + len(word["word"]) > 80):
                output.append(dict(start_ms=group[0]["start_ms"], end_ms=group[-1]["end_ms"], text="".join(w["word"] for w in group).strip()))
                group = []
            group.append(word)
        if group:
            output.append(dict(start_ms=group[0]["start_ms"], end_ms=group[-1]["end_ms"], text="".join(w["word"] for w in group).strip()))
    return local_cues(output, start_ms, end_ms)
