"""Read timed Markdown storyboards without treating directions as spoken text."""
import re
import math
from .schemas import Document, Scene
from app.media.process import MediaError


def plain(text):
    # Citation links are references, not words for the narrator. The original
    # Markdown (including its sources) remains in Document.script.
    text = re.sub(r"!?\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = text.replace("\\|", "|")
    text = re.sub(r"[*_`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def speech(text):
    value = plain(text)
    # Browser clipboard tables often retain only the citation label after a
    # quoted narration (not its Markdown URL). Keep it in the source script,
    # but only the quoted passage is spoken.
    for opening, closing in [('“', '”'), ('"', '"')]:
        if value.startswith(opening) and value.rfind(closing) > 0:
            value = value[1:value.rfind(closing)].strip()
            break
    return value


def cells(line, delimiter='|'):
    if delimiter == '\t':
        return [s.strip() for s in line.split('\t')]
    return [s.strip() for s in re.split(r"(?<!\\)\|", line.strip().strip('|'))]


def milliseconds(value):
    parts = value.replace(',', '.').split(':')
    if len(parts) > 3 or any(float(p) >= 60 for p in parts[1:]):
        raise ValueError()
    result = sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts))) * 1000
    if not math.isfinite(result) or not 0 <= result <= 180000:
        raise ValueError()
    return round(result)


def parse_storyboard(script):
    """Return None for prose; reject malformed recognized tables explicitly."""
    lines = script.splitlines()
    for index, line in enumerate(lines):
        delimiter = '|' if '|' in line else '\t'
        headers = [plain(c).lower() for c in cells(line, delimiter)]
        time_col = next((i for i, h in enumerate(headers) if h in ('waktu', 'time', 'timestamp')), None)
        narration_col = next((i for i, h in enumerate(headers) if h.startswith(('narasi', 'narration', 'voiceover'))), None)
        visual_col = next((i for i, h in enumerate(headers) if h.startswith(('visual', 'gambar'))), None)
        if delimiter not in line or time_col is None or narration_col is None:
            continue
        scenes, previous_end = [], 0
        for row in lines[index + 1:]:
            if not row.strip() or delimiter not in row:
                if scenes:
                    break
                continue
            values = cells(row, delimiter)
            if all(re.fullmatch(r"[:\-\s]+", c) for c in values):
                continue
            row_number = len(scenes) + 1
            try:
                if len(values) != len(headers):
                    raise ValueError()
                timing = plain(values[time_col])
                match = re.fullmatch(r"([\d:.,]+)\s*[-–—]\s*([\d:.,]+)(?:\s*(?:detik|seconds|s))?", timing, re.I)
                if not match:
                    raise ValueError()
                start, end = milliseconds(match[1]), milliseconds(match[2])
                if start != previous_end:
                    raise ValueError()
                narration = speech(values[narration_col])
                visual = plain(values[visual_col]) if visual_col is not None else ''
                scene = Scene(id=f'scene-{row_number}', title=f'Adegan {row_number}', narration=narration,
                              visual_note=visual, duration_ms=end-start)
                if not narration or len(scenes) >= 20 or end > 180000:
                    raise ValueError()
            except (ValueError, IndexError):
                raise MediaError('story_table_invalid', f'Periksa baris {row_number} pada tabel storyboard. Waktu harus berurutan mulai 00, durasi tiap adegan 1–30 detik, narasi maksimal 600 karakter, dan visual maksimal 500 karakter. Maksimal 20 adegan / 3 menit.')
            scenes.append(scene.model_dump())
            previous_end = end
        if not scenes:
            raise MediaError('story_table_empty', 'Tabel storyboard belum memiliki baris waktu dan narasi yang valid.')
        preamble = '\n'.join(lines[:index])
        title_match = re.search(r'^\s*#{1,6}\s+(.+)$', preamble, re.M)
        first_line = next((plain(s) for s in lines[:index] if s.strip()), '')
        title = plain(title_match[1]) if title_match else first_line if len(first_line) <= 200 and not first_line.lower().startswith(('durasi', 'siapkan', 'duration')) else None
        aspect = next((a for ratio, a in [('9:16', 'portrait'), ('16:9', 'landscape'), ('1:1', 'square')] if ratio in preamble), None)
        return {'scenes': scenes, 'title': title[:200] if title else None, 'aspect': aspect}
    return None


def table_document(document, parsed):
    from .visuals import fill_visuals
    return fill_visuals({**document, 'scenes': parsed['scenes'],
        'title': parsed['title'] or document['title'], 'aspect': parsed['aspect'] or document['aspect']})
