"""Offline narration adapters; model installation is separate from generation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import wave

from app.media.process import Cancelled, MediaError, run_process


POCKET_REVISION = '382fe85ca848546efb04bf1b7fdba78c6396e2ce'
POCKET_MODEL = 'anak10thn/pocket-tts-indonesian'
SPEECH_MODEL = POCKET_MODEL
DEFAULT_VOICE = 'pocket-id-1'
VOICE_LABELS = {
    'pocket-id-1': 'Indonesia · Suara 1 (lokal)',
    'pocket-id-2': 'Indonesia · Suara 2 (lokal)',
    'espeak-en': 'English · Suara dasar (lokal)',
}
PROMPTS = {'pocket-id-1': 'common_voice_id_19961910.mp3',
           'pocket-id-2': 'common_voice_id_20954552.mp3'}


def _number_words(number):
    units = ('nol', 'satu', 'dua', 'tiga', 'empat', 'lima', 'enam', 'tujuh', 'delapan', 'sembilan', 'sepuluh', 'sebelas')
    if number < 12:
        return units[number]
    if number < 20:
        return _number_words(number - 10) + ' belas'
    for scale, label in ((10**12, 'triliun'), (10**9, 'miliar'), (10**6, 'juta'), (1000, 'ribu'), (100, 'ratus'), (10, 'puluh')):
        if number >= scale:
            count, remainder = divmod(number, scale)
            head = 'seribu' if scale == 1000 and count == 1 else 'seratus' if scale == 100 and count == 1 else _number_words(count) + ' ' + label
            return head + (' ' + _number_words(remainder) if remainder else '')
    raise ValueError('number outside supported range')


def spoken_indonesian(text):
    """Expand plain numbers while leaving narration displayed in the editor intact."""
    if not any(char.isdigit() for char in text):
        return text
    # Dates, currencies, grouping separators and mixed IDs do not have one clear
    # pronunciation. Ask for words instead of silently changing their meaning.
    ambiguous = (r'\d\s*[/:+*-]\s*\d|\d[.,]\d{3}(?!\d)|\d[.,]\d+[.,]\d|'
                 r'(?:Rp\.?|IDR|USD|[$€£])\s*\d|\d\s*(?:Rp\.?|IDR|USD|[$€£])|'
                 r'[A-Za-z_]\d|\d[A-Za-z_]')
    if re.search(ambiguous, text, re.IGNORECASE):
        raise MediaError('story_local_speech_numbers', 'Tulis tanggal, mata uang, kode, atau angka berpemisah ribuan dengan kata agar narator Indonesia membacanya dengan benar.')
    def expand(match):
        value = match.group()
        prefix = 'minus ' if value.startswith('-') else 'plus ' if value.startswith('+') else ''
        value = value.lstrip('+-')
        parts = re.split(r'[.,]', value)
        if len(parts[0]) > 12:
            return prefix + ' '.join(_number_words(int(digit)) for digit in parts[0]) + (' koma ' + ' '.join(_number_words(int(digit)) for digit in parts[1]) if len(parts) == 2 else '')
        integer = int(parts[0])
        # Leading zeros normally denote a code rather than a quantity.
        spoken = ' '.join(_number_words(int(digit)) for digit in parts[0]) if len(parts[0]) > 1 and parts[0][0] == '0' else _number_words(integer)
        return prefix + spoken + (' koma ' + ' '.join(_number_words(int(digit)) for digit in parts[1]) if len(parts) == 2 else '')
    return re.sub(r'[+-]?\d+(?:[.,]\d+)?', expand, text).replace('%', ' persen')


def model_directory(settings):
    return Path(settings.story_models_root) / 'speech' / 'pocket-id'


def installed_voices(settings):
    directory = model_directory(settings)
    required = [('config.yaml', 100), ('model.safetensors', 100_000_000), ('tokenizer.model', 1000)]
    ready = all((directory / name).is_file() and (directory / name).stat().st_size >= size
                for name, size in required)
    voices = [voice for voice, filename in PROMPTS.items()
              if ready and (directory / 'voices' / filename).is_file()]
    if shutil.which(getattr(settings, 'story_espeak_path', 'espeak-ng')):
        voices.append('espeak-en')
    return voices


speech_voices = installed_voices


def _check(cancelled):
    if cancelled and cancelled():
        raise Cancelled()


def _validate_wav(path):
    try:
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError()
        with wave.open(str(path), 'rb') as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
            if not 8000 <= rate <= 48000 or wav.getnchannels() not in (1, 2) or wav.getsampwidth() != 2 or not 0 < frames / rate <= 180:
                raise ValueError()
            # Silent output is unusable even if the container and duration are valid.
            if not any(wav.readframes(frames)):
                raise ValueError()
            return round(frames / rate * 1000), rate
    except (OSError, EOFError, ValueError, wave.Error):
        raise MediaError('story_local_speech_invalid', 'Narator lokal tidak menghasilkan rekaman yang dapat dipakai. Coba narasi yang lebih singkat.') from None


def generate_speech(scene, voice, output_path, settings, cancelled):
    _check(cancelled)
    narration = scene.get('narration', '')
    if not isinstance(narration, str) or not narration.strip() or len(narration) > 600:
        raise MediaError('story_speech_input', 'Isi narasi 1 sampai 600 karakter sebelum membuat suara.')
    voice = voice or DEFAULT_VOICE
    if voice not in VOICE_LABELS:
        raise MediaError('story_speech_voice', 'Pilih suara lokal yang tersedia.')
    spoken_text = spoken_indonesian(narration) if voice in PROMPTS else narration
    if len(spoken_text) > 4000:
        raise MediaError('story_speech_input', 'Narasi angka terlalu panjang untuk satu adegan. Pecah menjadi beberapa adegan.')
    if voice not in installed_voices(settings):
        raise MediaError('story_local_speech_missing', 'Model suara lokal belum terpasang. Jalankan pemasangan model Story Studio pada server.')
    output = Path(output_path)
    temporary = output.with_name(output.name + '.partial.wav')
    request = output.with_name(output.name + '.request.json')
    text_file = output.with_name(output.name + '.text.txt')
    error_file = output.with_name(output.name + '.error.json')
    timeout = getattr(settings, 'story_local_timeout_seconds', 600)
    metadata = {'provider': 'local', 'generated': True, 'ai_voice': True, 'voice': voice,
                'input_characters': len(narration), 'usage': {}, 'offline': True}
    if spoken_text != narration:
        metadata['spoken_text'] = spoken_text
        metadata['source_narration'] = narration
    try:
        if voice == 'espeak-en':
            text_file.write_text(narration, encoding='utf-8')
            result = run_process([getattr(settings, 'story_espeak_path', 'espeak-ng'), '-v', 'en-us', '-s', '160',
                                  '-b', '1', '-w', str(temporary), '-f', str(text_file)],
                                 timeout=timeout, cancelled=cancelled)
            metadata.update(model='espeak-ng/en-us', language='en', quality='basic')
        else:
            directory = model_directory(settings).resolve()
            request.write_text(json.dumps({'model_root': str(directory),
                                           'voice': str(directory / 'voices' / PROMPTS[voice]),
                                           'text': spoken_text, 'output': str(temporary.resolve()),
                                           'error': str(error_file.resolve()),
                                           'threads': max(1, min(8, getattr(settings, 'whisper_cpu_threads', 4)))}, ensure_ascii=False), encoding='utf-8')
            env = os.environ.copy()
            # The isolated Torch runtime must not pick the backend's CUDA libraries.
            env.pop('LD_LIBRARY_PATH', None)
            env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                       CUDA_VISIBLE_DEVICES='', PYTHONNOUSERSITE='1')
            result = run_process([settings.story_local_python, str(Path(__file__).with_name('speech_child.py')),
                                  str(request.resolve())], timeout=timeout, cancelled=cancelled, env=env)
            metadata.update(model=POCKET_MODEL, model_revision=POCKET_REVISION, language='id', quality='neural',
                            attribution='Pocket TTS Indonesian by anak10thn; Kyutai Pocket TTS; LEMAS Project. Model CC BY 4.0. Voice prompt: Common Voice 22.0, CC0.',
                            license_url='https://creativecommons.org/licenses/by/4.0/',
                            source_url='https://huggingface.co/anak10thn/pocket-tts-indonesian')
        _check(cancelled)
        if result.returncode:
            code = 'story_local_speech_failed'
            if error_file.is_file():
                try:
                    if json.loads(error_file.read_text(encoding='utf-8')).get('code') == 'dependency_missing':
                        code = 'story_local_dependency_missing'
                except (ValueError, OSError):
                    pass
            raise MediaError(code, 'Narator lokal gagal dijalankan. Periksa runtime lokal dan model suara pada worker.')
        duration, rate = _validate_wav(temporary)
        _check(cancelled)
        temporary.replace(output)
        return {**metadata, 'duration_ms': duration, 'sample_rate': rate}
    except FileNotFoundError:
        raise MediaError('story_local_dependency_missing', 'Runtime narator lokal belum terpasang pada worker.') from None
    finally:
        for path in (temporary, request, text_file, error_file):
            path.unlink(missing_ok=True)
