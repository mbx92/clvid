"""Align narration to measured speech, refusing missing phrases and early tails."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.ai.clip_transcribe import transcribe_clip
from app.media.process import MediaError


def _token(text):
    return ''.join(c.casefold() for c in text if c.isalnum())


def _observed_words(segments, duration_ms):
    words = []
    previous_end = 0
    for segment in segments:
        for item in segment.get('words_json') or []:
            tokens = item['word'].split()
            a, b = max(previous_end, int(item['start_ms']), 0), min(duration_ms, int(item['end_ms']))
            if b <= a or not tokens:
                continue
            for i, text in enumerate(tokens):
                start, end = round(a + (b - a) * i / len(tokens)), round(a + (b - a) * (i + 1) / len(tokens))
                if end > start:
                    if not _token(text) and words:
                        words[-1]['text'] += text
                    elif _token(text):
                        words.append({'text': text, 'start_ms': start, 'end_ms': end})
            previous_end = b
    return words


def aligned_words(narration, observed):
    if not observed:
        raise MediaError('story_no_speech', 'Tidak ditemukan ucapan yang dapat diberi waktu. Periksa rekaman atau isi subtitle secara manual.')
    if not narration.strip():
        return observed, ' '.join(w['text'] for w in observed), []
    source = re.findall(r'\S+', narration)
    # Attach standalone punctuation to a spoken token without fabricating audio.
    tokens = []
    for text in source:
        if _token(text):
            tokens.append(text)
        elif tokens:
            tokens[-1] += ' ' + text
    left, right = [_token(t) for t in tokens], [_token(w['text']) for w in observed]
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    if not tokens or matched / max(len(tokens), len(observed)) < .8:
        raise MediaError('story_audio_text_mismatch', 'Ucapan dan naskah berbeda. Periksa narasi; untuk mengambil transkrip rekaman, kosongkan narasi lalu sinkronkan lagi.')
    output, adjusted = [], False
    for op, a, b, c, d in matcher.get_opcodes():
        if op == 'equal':
            output.extend({**observed[j], 'text': tokens[i]} for i, j in zip(range(a, b), range(c, d)))
        elif op == 'replace' and 0 < b - a <= 3 and 0 < d - c <= 3:
            # Minor spelling differences share the corresponding observed audio span.
            start, end = observed[c]['start_ms'], observed[d - 1]['end_ms']
            for i in range(a, b):
                output.append({'text': tokens[i], 'start_ms': round(start + (end - start) * (i - a) / (b - a)),
                               'end_ms': round(start + (end - start) * (i - a + 1) / (b - a))})
            adjusted = True
        else:
            # Never stretch the last recognized sentence across missing speech.
            raise MediaError('story_alignment_incomplete', 'Sebagian naskah belum cocok dengan audio. Periksa ucapan awal/akhir, pecah adegan, atau kosongkan narasi untuk menyalin transkrip rekaman.')
    if any(w['end_ms'] <= w['start_ms'] for w in output):
        raise MediaError('story_alignment_incomplete', 'Timing ucapan belum cukup jelas. Gunakan rekaman yang lebih jernih atau edit subtitle secara manual.')
    warnings = ['Perbedaan ejaan kecil memakai rentang audio terdekat. Tinjau timing subtitle.'] if adjusted else []
    return output, narration, warnings


def word_cues(words):
    cues = []
    for word in words:
        text = word['text']
        if len(text) > 200:
            raise MediaError('story_caption_word_long', 'Ada kata lebih dari 200 karakter. Perbaiki pemisahan kata pada narasi.')
        current = cues[-1] if cues else None
        length = lambda value: len(value.encode('utf-16-le')) // 2
        if (not current or length(current['text']) + length(text) + 1 > 70 or
                word['start_ms'] - current['end_ms'] > 600 or word['end_ms'] - current['start_ms'] > 3500):
            cues.append({'start_ms': word['start_ms'], 'end_ms': word['end_ms'], 'text': text})
        else:
            current['text'] += ' ' + text
            current['end_ms'] = word['end_ms']
    if len(cues) > 200:
        raise MediaError('story_caption_limit', 'Terlalu banyak potongan subtitle. Pecah adegan menjadi bagian yang lebih pendek.')
    return cues


def align_audio(source, scratch, *, narration, duration_ms, settings, cancelled=None, progress=None):
    result = transcribe_clip(source, scratch, start_ms=0, end_ms=duration_ms, language='auto',
                             settings=settings, cancelled=cancelled, progress=progress)
    observed = _observed_words(result['segments'], duration_ms)
    words, text, warnings = aligned_words(narration, observed)
    recovery = result.get('runtime', {}).get('subtitle_recovery', {})
    if not narration.strip():
        if recovery.get('filtered_segments', 0):
            warnings.append('Ada bagian audio yang tidak cukup jelas untuk ditranskrip. Dengarkan ulang sebelum mengekspor.')
        if duration_ms - observed[-1]['end_ms'] > 2000:
            warnings.append('Tidak ada ucapan terverifikasi pada bagian akhir rekaman. Periksa apakah bagian itu memang hening; subtitle tidak diperpanjang secara otomatis.')
    if len(text) > 600:
        raise MediaError('story_narration_limit', 'Transkrip melebihi 600 karakter per adegan. Pecah audio menjadi beberapa adegan.')
    return {'narration': text, 'captions': word_cues(words), 'warnings': warnings,
            'language': result['language']}
