import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from app.media.process import Cancelled, MediaError, ProcessResult
from app.story import local_speech


def settings(tmp_path):
    return SimpleNamespace(story_models_root=tmp_path / 'models', story_local_python='/isolated/python',
                           story_local_timeout_seconds=600, whisper_cpu_threads=4, story_espeak_path='espeak-ng')


def wav(path, silent=False):
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        output.writeframes((b'\x00\x00' if silent else b'\x10\x00') * 2400)


def ready(monkeypatch):
    monkeypatch.setattr(local_speech, 'installed_voices', lambda s: list(local_speech.VOICE_LABELS))


def test_neural_speech_runs_isolated_offline_process(monkeypatch, tmp_path):
    ready(monkeypatch)
    monkeypatch.setenv('LD_LIBRARY_PATH', '/backend/cuda')
    called = []
    def run(args, **kwargs):
        called.append((args, kwargs))
        request = json.loads(Path(args[-1]).read_text(encoding='utf-8'))
        assert request['text'] == 'Dua biji kopi di atas piring.'
        assert request['voice'].endswith('common_voice_id_19961910.mp3')
        assert request['threads'] == 4
        assert kwargs['env']['HF_HUB_OFFLINE'] == '1'
        assert kwargs['env']['CUDA_VISIBLE_DEVICES'] == ''
        assert 'LD_LIBRARY_PATH' not in kwargs['env']
        wav(Path(request['output']))
        return ProcessResult('', '', 0)
    monkeypatch.setattr(local_speech, 'run_process', run)
    output = tmp_path / 'voice.wav'
    report = local_speech.generate_speech({'narration':'Dua biji kopi di atas piring.'}, 'pocket-id-1', output, settings(tmp_path), lambda:False)
    assert output.is_file() and report['duration_ms'] == 100
    assert report['provider'] == 'local' and report['offline'] is True
    assert report['model'] == local_speech.SPEECH_MODEL and report['language'] == 'id'
    assert 'CC BY 4.0' in report['attribution']
    assert called[0][0][0] == '/isolated/python'
    assert list(tmp_path.glob('voice.wav.*')) == []


def test_english_uses_text_file_without_shell_interpolation(monkeypatch, tmp_path):
    ready(monkeypatch)
    text = 'Hello $(command) `text` --help.'
    def run(args, **kwargs):
        assert args[:3] == ['espeak-ng','-v','en-us']
        assert Path(args[-1]).read_text() == text
        wav(Path(args[args.index('-w') + 1]))
        return ProcessResult('', '', 0)
    monkeypatch.setattr(local_speech, 'run_process', run)
    report = local_speech.generate_speech({'narration':text}, 'espeak-en', tmp_path/'voice.wav', settings(tmp_path), lambda:False)
    assert report['model'] == 'espeak-ng/en-us' and report['quality'] == 'basic'


@pytest.mark.parametrize('text, voice, code', [('', 'pocket-id-1', 'story_speech_input'),
    ('a'*601,'pocket-id-1','story_speech_input'), ('hello','../../secret','story_speech_voice'),
    ('Harganya Rp2.000.','pocket-id-1','story_local_speech_numbers')])
def test_invalid_input_never_starts_process(monkeypatch, tmp_path, text, voice, code):
    monkeypatch.setattr(local_speech, 'run_process', lambda *a,**k:pytest.fail('process must not start'))
    with pytest.raises(MediaError) as exc:
        local_speech.generate_speech({'narration':text},voice,tmp_path/'voice.wav',settings(tmp_path),lambda:False)
    assert exc.value.code == code


@pytest.mark.parametrize('source, expected', [('0','nol'),('1','satu'),('2','dua'),('10','sepuluh'),('11','sebelas'),
    ('20','dua puluh'),('100','seratus'),('101','seratus satu'),('1000','seribu'),('2000','dua ribu'),
    ('1000000','satu juta'),('2,5','dua koma lima'),('3.14','tiga koma satu empat'),('01','nol satu'),
    ('-2,5','minus dua koma lima'), ('2%','dua persen')])
def test_indonesian_number_normalization(source, expected):
    assert local_speech.spoken_indonesian(source) == expected


@pytest.mark.parametrize('text', ['01/02/2026','1.000 biji','1,000 biji','Rp 100','IDR 100','A1','12:30'])
def test_ambiguous_number_forms_require_explicit_words(text):
    with pytest.raises(MediaError, match='Tulis tanggal'):
        local_speech.spoken_indonesian(text)


def test_numeric_narration_reports_actual_spoken_text(monkeypatch, tmp_path):
    ready(monkeypatch)
    def run(args, **kwargs):
        request = json.loads(Path(args[-1]).read_text(encoding='utf-8'))
        assert request['text'] == 'Ada dua biji kopi.'
        wav(Path(request['output']))
        return ProcessResult('', '', 0)
    monkeypatch.setattr(local_speech, 'run_process', run)
    scene = {'narration':'Ada 2 biji kopi.'}
    report = local_speech.generate_speech(scene,'pocket-id-1',tmp_path/'voice.wav',settings(tmp_path),lambda:False)
    assert scene['narration'] == 'Ada 2 biji kopi.'
    assert report['spoken_text'] == 'Ada dua biji kopi.'
    assert report['source_narration'] == 'Ada 2 biji kopi.'


def test_missing_models_and_english_readiness(monkeypatch, tmp_path):
    monkeypatch.setattr(local_speech.shutil,'which',lambda name:'/bin/espeak-ng')
    assert local_speech.speech_voices(settings(tmp_path)) == ['espeak-en']
    with pytest.raises(MediaError) as exc:
        local_speech.generate_speech({'narration':'Halo.'},'pocket-id-1',tmp_path/'voice.wav',settings(tmp_path),lambda:False)
    assert exc.value.code == 'story_local_speech_missing'


def test_cancellation_discards_partial_audio(monkeypatch, tmp_path):
    ready(monkeypatch)
    def run(args, **kwargs):
        request = json.loads(Path(args[-1]).read_text())
        wav(Path(request['output']))
        raise Cancelled()
    monkeypatch.setattr(local_speech,'run_process',run)
    output=tmp_path/'voice.wav'
    with pytest.raises(Cancelled):
        local_speech.generate_speech({'narration':'Halo.'},'pocket-id-1',output,settings(tmp_path),lambda:False)
    assert not output.exists() and list(tmp_path.glob('voice.wav.*')) == []


@pytest.mark.parametrize('failure', ['silent','missing','error'])
def test_invalid_output_never_publishes_audio(monkeypatch, tmp_path, failure):
    ready(monkeypatch)
    def run(args, **kwargs):
        request = json.loads(Path(args[-1]).read_text())
        if failure == 'silent': wav(Path(request['output']), silent=True)
        if failure == 'error': Path(request['error']).write_text('{"code":"dependency_missing"}')
        return ProcessResult('', 'sensitive error details', 1 if failure == 'error' else 0)
    monkeypatch.setattr(local_speech,'run_process',run)
    output = tmp_path/'voice.wav'
    with pytest.raises(MediaError) as exc:
        local_speech.generate_speech({'narration':'Halo.'},'pocket-id-1',output,settings(tmp_path),lambda:False)
    assert 'sensitive' not in str(exc.value)
    assert not output.exists()
