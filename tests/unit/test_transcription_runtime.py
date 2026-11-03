import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.transcribe import transcribe
from app.ai.whisper_child import runtime_plan, transcribe_with_runtime
from app.media.process import Cancelled, ProcessResult, ProgressParser, run_process


def config(**overrides):
    return {"source": "private.mp4", "output": "output.json", "model": "small", "device": "auto",
            "compute_type": "auto", "language": "id", "cache_dir": "cache",
            "cpu_threads": 4, "batch_size": 8, "beam_size": 5, **overrides}


def segment(start=0, end=2, text="Ucapan uji"):
    return SimpleNamespace(start=start, end=end, text=text, words=[SimpleNamespace(start=start, end=end, word=text, probability=.9)])


INFO = SimpleNamespace(language="id", language_probability=.99, duration=10)


def test_auto_device_preserves_quality_defaults_and_cpu_bounds():
    cpu = runtime_plan(config(), 0)
    gpu = runtime_plan(config(), 1)
    assert (cpu["device"], cpu["compute_type"], cpu["batch_size"], cpu["fallback_reason"]) == ("cpu", "int8", 1, "cuda_unavailable")
    assert (gpu["device"], gpu["compute_type"], gpu["batch_size"], gpu["beam_size"]) == ("cuda", "float16", 8, 5)
    assert runtime_plan(config(device="cpu"), 1)["fallback_reason"] is None


def test_cuda_uses_batch_and_only_reports_real_timestamps():
    calls, reported = [], []
    class Model:
        def __init__(self, name, **kwargs):
            calls.append(("model", kwargs))
    class Batched:
        def __init__(self, model): pass
        def transcribe(self, source, **kwargs):
            calls.append(("transcribe", kwargs))
            return iter([segment(0, 2), segment(4, 7)]), INFO
    result = transcribe_with_runtime(config(), model_factory=Model, batched_factory=Batched,
                                     cuda_device_count=lambda: 1, report=reported.append)
    assert calls[0][1]["device"] == "cuda" and calls[0][1]["cpu_threads"] == 4
    assert calls[1][1]["batch_size"] == 8 and calls[1][1]["beam_size"] == 5
    assert calls[1][1]["word_timestamps"] is True
    assert reported == ["segment_end_ms=2000", "segment_end_ms=7000"]
    assert result["segments"][1]["words_json"][0]["start_ms"] == 4000
    assert result["runtime"]["device"] == "cuda" and result["runtime"]["fallback_reason"] is None


def test_gpu_failure_discards_partial_output_and_records_cpu_fallback():
    devices, reported = [], []
    class Model:
        def __init__(self, name, **kwargs):
            self.device = kwargs["device"]
            devices.append(kwargs)
        def transcribe(self, source, **kwargs):
            assert "batch_size" not in kwargs
            return iter([segment(text="Hasil CPU utuh")]), INFO
    class BrokenBatch:
        def __init__(self, model): pass
        def transcribe(self, source, **kwargs):
            def iterator():
                yield segment(text="Hasil GPU parsial")
                raise RuntimeError("CUDA failure containing private diagnostic")
            return iterator(), INFO
    result = transcribe_with_runtime(config(), model_factory=Model, batched_factory=BrokenBatch,
                                     cuda_device_count=lambda: 1, report=reported.append)
    assert [d["device"] for d in devices] == ["cuda", "cpu"]
    assert devices[1]["compute_type"] == "int8"
    assert [s["text"] for s in result["segments"]] == ["Hasil CPU utuh"]
    assert result["runtime"]["fallback_reason"] == "cuda_execution_failed"
    assert result["runtime"]["batch_size"] == 1
    assert "progress_reset=1" in reported
    assert "private diagnostic" not in json.dumps(result["runtime"])


def test_explicit_cuda_does_not_silently_run_cpu():
    class BrokenModel:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("CUDA unavailable")
    with pytest.raises(RuntimeError):
        transcribe_with_runtime(config(device="cuda"), model_factory=BrokenModel, batched_factory=object,
                                cuda_device_count=lambda: 0, report=lambda _: None)


def test_clip_vad_options_and_quality_evidence_survive_child_output():
    observed = []
    class Model:
        def __init__(self, *a, **kw): pass
        def transcribe(self, source, **kwargs):
            observed.append(kwargs)
            item = segment()
            item.avg_logprob, item.no_speech_prob = -.25, .1
            return iter([item]), INFO
    vad = {"threshold": .35, "min_silence_duration_ms": 300, "speech_pad_ms": 200}
    result = transcribe_with_runtime(config(device="cpu", vad_parameters=vad), model_factory=Model,
                                     batched_factory=object, cuda_device_count=lambda: 0, report=lambda _: None)
    assert observed[0]["vad_filter"] is True and observed[0]["vad_parameters"] == vad
    assert result["segments"][0]["avg_logprob"] == -.25
    assert result["segments"][0]["no_speech_prob"] == .1


def test_native_cuda_abort_retries_cpu_once_and_preserves_cancel_boundary(tmp_path, monkeypatch):
    calls = []
    def child(args, **kwargs):
        request = json.loads(Path(args[-1]).read_text())
        calls.append((request, kwargs))
        if request["device"] == "auto":
            (tmp_path / "transcription-runtime.json").write_text(json.dumps({"device": "cuda"}))
            return ProcessResult("", "private CUDA diagnostic", -6)
        Path(request["output"]).write_text(json.dumps({"language": "id", "segments": [], "runtime": {"device": "cpu", "fallback_reason": request["fallback_reason"]}}))
        return ProcessResult("", "", 0)
    monkeypatch.setattr("app.ai.transcribe.run_process", child)
    result = transcribe(tmp_path / "source.mp4", tmp_path, duration_ms=10000)
    assert [call[0]["device"] for call in calls] == ["auto", "cpu"]
    assert all(call[1]["duration_ms"] == 10000 for call in calls)
    assert result["runtime"]["fallback_reason"] == "cuda_process_failed"
    def cancelled(*args, **kwargs):
        raise Cancelled()
    monkeypatch.setattr("app.ai.transcribe.run_process", cancelled)
    with pytest.raises(Cancelled):
        transcribe(tmp_path / "source.mp4", tmp_path, duration_ms=10000)


def test_progress_parser_handles_fragmented_lines_microseconds_and_restart():
    parser = ProgressParser(10000)
    assert parser.feed("segment_end_ms=2") is None
    assert parser.feed("500\nignored=1\n") == .25
    assert parser.feed("out_time_ms=5000000\n") == .5
    assert parser.feed("segment_end_ms=4000\n") == .5
    assert parser.feed("progress_reset=1\nsegment_end_ms=1000\n") == .1
    assert parser.feed("segment_end_ms=10000", final=True) == .99
    assert ProgressParser(None).feed("segment_end_ms=1000\n") is None


def test_run_process_reads_final_real_progress_for_short_process():
    values = []
    result = run_process([sys.executable, "-c", "print('segment_end_ms=4000', flush=True)"], duration_ms=10000, progress=values.append)
    assert result.returncode == 0 and values[-1] == .4
    assert all(v is None or 0 <= v <= .4 for v in values)
