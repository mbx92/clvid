from types import SimpleNamespace
import pytest

from app.media.process import MediaError
from app.story.alignment import aligned_words, word_cues, align_audio


def words(text, start=100, step=400):
    return [{'text': token, 'start_ms': start + i * step, 'end_ms': start + i * step + 250}
            for i, token in enumerate(text.split())]


def test_exact_narration_preserves_punctuation_and_audio_silence():
    observed = words('kopi ini tumbuh sendirian') + words('yang b', start=5000)
    aligned, narration, warnings = aligned_words('Kopi ini tumbuh sendirian. Yang B!', observed)
    cues = word_cues(aligned)
    assert narration == 'Kopi ini tumbuh sendirian. Yang B!'
    assert cues == [{'start_ms': 100, 'end_ms': 1550, 'text': 'Kopi ini tumbuh sendirian.'},
                    {'start_ms': 5000, 'end_ms': 5650, 'text': 'Yang B!'}]
    assert warnings == []


@pytest.mark.parametrize('narration, spoken', [
    ('satu dua tiga empat lima enam tujuh delapan sembilan sepuluh', 'satu dua tiga empat lima enam tujuh delapan sembilan'),
    ('satu dua tiga empat lima enam tujuh delapan sembilan sepuluh', 'dua tiga empat lima enam tujuh delapan sembilan sepuluh'),
    ('kopi segar harum', 'kalimat lain sama sekali'),
])
def test_missing_start_tail_or_mismatched_audio_is_never_stretched(narration, spoken):
    with pytest.raises(MediaError):
        aligned_words(narration, words(spoken))


def test_small_spelling_difference_uses_observed_span_and_warns():
    aligned, narration, warnings = aligned_words('ini satu contoh kata kopi lanang', words('ini satu contoh kata kopi lanag'))
    assert aligned[-1]['text'] == 'lanang' and aligned[-1]['start_ms'] == 2100
    assert narration.endswith('lanang') and warnings


def test_empty_narration_transcribes_and_no_speech_errors():
    observed = words('Kopi lanang tumbuh sendiri.')
    assert aligned_words('', observed)[1] == 'Kopi lanang tumbuh sendiri.'
    with pytest.raises(MediaError, match='Tidak ditemukan'):
        aligned_words('Kopi', [])


def test_audio_pipeline_reads_entire_asset_and_never_overruns(monkeypatch, tmp_path):
    calls = []
    def decode(source, scratch, **kwargs):
        calls.append(kwargs)
        return {'language':'id', 'segments':[{'words_json':[
            {'word':' Halo', 'start_ms':120, 'end_ms':400},
            {'word':' dunia.', 'start_ms':800, 'end_ms':1200}]}]}
    monkeypatch.setattr('app.story.alignment.transcribe_clip', decode)
    result = align_audio(tmp_path/'audio.m4a', tmp_path/'scratch', narration='Halo dunia.', duration_ms=1000, settings=SimpleNamespace())
    assert calls[0]['end_ms'] == 1000
    assert result['captions'] == [{'start_ms':120, 'end_ms':1000, 'text':'Halo dunia.'}]


def test_new_transcript_warns_about_unverified_tail_without_extending_text(monkeypatch, tmp_path):
    monkeypatch.setattr('app.story.alignment.transcribe_clip', lambda *a, **k: {
        'language':'id', 'segments':[{'words_json':[{'word':' Halo', 'start_ms':100, 'end_ms':800}]}],
        'runtime':{'subtitle_recovery':{'filtered_segments':1}}})
    result = align_audio(tmp_path/'audio.m4a', tmp_path/'scratch', narration='', duration_ms=8000, settings=SimpleNamespace())
    assert result['captions'][-1]['end_ms'] == 800 and len(result['warnings']) == 2
