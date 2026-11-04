from types import SimpleNamespace

import pytest

from app.ai.clip_transcribe import transcribe_clip
from app.media.process import Cancelled, MediaError


@pytest.fixture
def settings():
    return SimpleNamespace(ffmpeg_path="ffmpeg", media_timeout_seconds=90, whisper_model="small",
                           whisper_device="cpu", whisper_compute_type="int8", whisper_download_root="/models",
                           whisper_cpu_threads=2, whisper_batch_size=1, whisper_beam_size=5, job_timeout_seconds=300)


def segment(**changes):
    return {"start_ms": 1000, "end_ms": 6000, "text": "Sebelum Awas boss menang setelah",
            "avg_logprob": -.2, "no_speech_prob": .05,
            "words_json": [{"word": " Sebelum", "start_ms": 1000, "end_ms": 1900, "probability": .9},
                           {"word": " Awas", "start_ms": 1900, "end_ms": 2400, "probability": .9},
                           {"word": " boss", "start_ms": 2500, "end_ms": 2800, "probability": .9},
                           {"word": " menang", "start_ms": 4000, "end_ms": 5500, "probability": .9},
                           {"word": " setelah", "start_ms": 5500, "end_ms": 6000, "probability": .9}], **changes}


def prepare(monkeypatch, segments):
    calls = []
    def extract(args, **kwargs):
        calls.append((args, kwargs))
        args[-1].write_bytes(b"audio")
    def recognize(source, directory, **kwargs):
        assert source.exists()
        assert kwargs["vad_parameters"]["threshold"] == .35
        return {"language": "id", "segments": segments, "runtime": {"device": "cpu"}}
    monkeypatch.setattr("app.ai.clip_transcribe.ffmpeg", extract)
    monkeypatch.setattr("app.ai.clip_transcribe.transcribe", recognize)
    return calls


def test_recovery_translates_and_clamps_word_timing_to_source(monkeypatch, tmp_path, settings):
    calls = prepare(monkeypatch, [segment()])
    result = transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=10000, end_ms=13000,
                             language="id", settings=settings)
    assert calls[0][0][1] == "8.000"
    assert calls[0][0][5] == "7.000"
    assert result["segments"] == [{"start_ms": 10000, "end_ms": 13000, "text": "Awas boss menang",
        "words_json": [{"word": " Awas", "start_ms": 10000, "end_ms": 10400, "probability": .9},
                       {"word": " boss", "start_ms": 10500, "end_ms": 10800, "probability": .9},
                       {"word": " menang", "start_ms": 12000, "end_ms": 13000, "probability": .9}]}]
    assert not (tmp_path / "clip-speech.wav").exists()


@pytest.mark.parametrize("candidate", [segment(no_speech_prob=.8, avg_logprob=-2), segment(avg_logprob=-2),
    segment(words_json=[{"word": " noise", "start_ms": 100, "end_ms": 500, "probability": .1}]),
    segment(words_json=[]), segment(no_speech_prob=float("nan"))])
def test_noise_and_missing_word_timing_do_not_become_fake_dialogue(monkeypatch, tmp_path, settings, candidate):
    prepare(monkeypatch, [candidate])
    assert transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=0, end_ms=9000,
                           language="id", settings=settings)["segments"] == []


@pytest.mark.parametrize("silence,likelihood", [(.5263, -.4939), (.6113, -.5709), (.95, -.2)])
def test_decoder_window_silence_score_does_not_erase_clear_phrases(monkeypatch, tmp_path, settings, silence, likelihood):
    # First two pairs reproduce actual combat windows where every valid phrase
    # inherited one score and the old .5 cutoff erased the entire clip.
    prepare(monkeypatch, [segment(no_speech_prob=silence, avg_logprob=likelihood)])
    result = transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=10000, end_ms=13000,
                             language="id", settings=settings)
    assert result["segments"][0]["text"] == "Awas boss menang"
    stats = result["runtime"]["subtitle_recovery"]
    assert (stats["recognized_segments"], stats["accepted_segments"], stats["filtered_segments"]) == (2, 1, 0)
    assert [p["preprocessing"] for p in stats["passes"]] == ["original", "speech_normalized"]


def test_unaligned_lexical_tokens_cannot_be_removed_to_create_a_partial_caption(monkeypatch, tmp_path, settings):
    # Regression: dropping the first two zero-duration words used to publish
    # "telah menonton", despite the complete sentence having invalid timing.
    candidate = segment(start_ms=2000, end_ms=11400, text="Terima kasih telah menonton", no_speech_prob=.95,
                        words_json=[{"word": " Terima", "start_ms": 2000, "end_ms": 2000, "probability": .9},
                                    {"word": " kasih", "start_ms": 2000, "end_ms": 2000, "probability": .9},
                                    {"word": " telah", "start_ms": 2000, "end_ms": 10620, "probability": .9},
                                    {"word": " menonton", "start_ms": 10620, "end_ms": 11400, "probability": .9}])
    prepare(monkeypatch, [candidate])
    result = transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=0, end_ms=16000,
                             language="id", settings=settings)
    assert result["segments"] == []
    assert result["runtime"]["subtitle_recovery"]["filtered_segments"] == 2


@pytest.mark.parametrize("invalid_start,invalid_end", [(1500, 1500), (6000, 6000), (1900, 1800)])
def test_unaligned_word_outside_cut_does_not_erase_in_window_speech(monkeypatch, tmp_path, settings, invalid_start, invalid_end):
    candidate = segment(no_speech_prob=.95)
    candidate["words_json"].append({"word": " outside", "start_ms": invalid_start, "end_ms": invalid_end, "probability": .1})
    prepare(monkeypatch, [candidate])
    result = transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=10000, end_ms=13000,
                             language="id", settings=settings)
    assert result["segments"][0]["text"] == "Awas boss menang"


@pytest.mark.parametrize("token", [".", "…", "!!!"])
def test_zero_duration_punctuation_preserves_short_reaction(monkeypatch, tmp_path, settings, token):
    candidate = segment(start_ms=2200, end_ms=2380, text="Nice!", no_speech_prob=.95,
                        words_json=[{"word": " Nice!", "start_ms": 2200, "end_ms": 2380, "probability": .9},
                                    {"word": token, "start_ms": 2380, "end_ms": 2380, "probability": .9}])
    prepare(monkeypatch, [candidate])
    result = transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=10000, end_ms=13000,
                             language="id", settings=settings)
    assert result["segments"][0]["text"] == "Nice!"
    assert result["segments"][0]["end_ms"] - result["segments"][0]["start_ms"] == 180


def test_inverted_word_timing_crossing_clip_boundary_rejects_segment(monkeypatch, tmp_path, settings):
    candidate = segment()
    candidate["words_json"].append({"word": " broken", "start_ms": 2100, "end_ms": 1900, "probability": .9})
    prepare(monkeypatch, [candidate])
    assert transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=10000, end_ms=13000,
                           language="id", settings=settings)["segments"] == []


@pytest.mark.parametrize("error", [Cancelled(), MediaError("transcription_failed", "failed")])
def test_recovery_cleans_audio_and_propagates_failures(monkeypatch, tmp_path, settings, error):
    prepare(monkeypatch, [])
    def fail(*a, **kw):
        raise error
    monkeypatch.setattr("app.ai.clip_transcribe.transcribe", fail)
    with pytest.raises(type(error)):
        transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=0, end_ms=9000,
                        language="id", settings=settings)
    assert not (tmp_path / "clip-speech.wav").exists()


def test_normalization_recovers_quiet_speech_without_touching_the_source(monkeypatch, tmp_path, settings):
    calls = prepare(monkeypatch, [])
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original soundtrack")
    def recognize(path, directory, **kwargs):
        return {"language": "id", "segments": [segment()] if "normalized" in path.name else []}
    monkeypatch.setattr("app.ai.clip_transcribe.transcribe", recognize)
    result = transcribe_clip(source, tmp_path, start_ms=10000, end_ms=13000, language="id", settings=settings)
    assert result["segments"][0]["text"] == "Awas boss menang"
    assert result["runtime"]["subtitle_recovery"]["preferred_pass"] == "speech_normalized"
    assert "speechnorm=" in calls[1][0][3]
    assert source.read_bytes() == b"original soundtrack"
    assert not list(tmp_path.glob("*.wav"))


def test_pass_combination_keeps_missing_reactions_without_duplicate_words():
    from app.ai.clip_transcribe import combine_passes
    def phrase(start, end, text):
        return {"start_ms": start, "end_ms": end, "text": text,
                "words_json": [{"start_ms": start, "end_ms": end, "word": w} for w in text.split()]}
    original = [phrase(0, 900, "Awas"), phrase(3000, 3200, "Nice!")]
    normalized = [phrase(20, 950, "Awas boss"), phrase(2000, 2400, "Lari sekarang")]
    rows, chosen = combine_passes(original, normalized)
    assert chosen == "speech_normalized"
    assert [s["text"] for s in rows] == ["Awas boss", "Lari sekarang", "Nice!"]
    assert len(original) == len(normalized) == 2


def test_cancellation_between_passes_does_not_publish_partial_subtitles(monkeypatch, tmp_path, settings):
    prepare(monkeypatch, [segment()])
    with pytest.raises(Cancelled):
        transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=10000, end_ms=13000,
                        language="id", settings=settings, cancelled=lambda: True)
    assert not list(tmp_path.glob("*.wav"))


def test_optional_normalization_failure_keeps_valid_original_speech(monkeypatch, tmp_path, settings):
    prepare(monkeypatch, [segment()])
    def recognize(path, directory, **kwargs):
        if "normalized" in path.name:
            raise MediaError("transcription_failed", "unavailable")
        return {"language": "id", "segments": [segment()]}
    monkeypatch.setattr("app.ai.clip_transcribe.transcribe", recognize)
    result = transcribe_clip(tmp_path / "source.mp4", tmp_path, start_ms=10000, end_ms=13000,
                             language="id", settings=settings)
    assert result["segments"][0]["text"] == "Awas boss menang"
    assert result["runtime"]["subtitle_recovery"]["passes"][-1]["error_code"] == "transcription_failed"


def test_recovery_uses_sequential_decoding_and_retains_speech_to_clip_end(monkeypatch,tmp_path,settings):
    prepare(monkeypatch,[])
    settings.whisper_batch_size=8
    batches=[]
    def recognize(path,directory,**kwargs):
        batches.append(kwargs['batch_size'])
        # A batch returns a 30s segment with one unaligned word, which must
        # never erase an otherwise correctly decoded second half of the clip.
        if kwargs['batch_size']>1:
            return {'language':'en','segments':[segment(words_json=[{'word':'bad','start_ms':32000,'end_ms':32000}])]}
        rows=[]
        for start,end in [(2200,2500),(31000,32000),(61000,61800),(62000,63500)]:
            rows.append(segment(start_ms=start,end_ms=end,text=' Speech',words_json=[
                {'word':' Speech','start_ms':start,'end_ms':end,'probability':.95}]))
        return {'language':'en','segments':rows}
    monkeypatch.setattr('app.ai.clip_transcribe.transcribe',recognize)
    result=transcribe_clip(tmp_path/'source.mp4',tmp_path,start_ms=10000,end_ms=70000,language='en',settings=settings)
    assert batches==[1,1]
    assert result['segments'][-1]['end_ms']==69800
    assert len(result['segments'])==3
    assert all(10000<=s['start_ms']<s['end_ms']<=70000 for s in result['segments'])
