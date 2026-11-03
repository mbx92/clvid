"""Isolated, killable transcription. Only timing/runtime metadata goes to stdout."""
from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path


def runtime_plan(config: dict, cuda_count: int) -> dict:
    requested = config.get("device", "auto")
    if requested not in ("auto", "cpu", "cuda"):
        raise ValueError("Unsupported transcription device")
    device = "cuda" if requested == "auto" and cuda_count > 0 else ("cpu" if requested == "auto" else requested)
    compute = config.get("compute_type", "auto")
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return {
        "model": config["model"],
        "requested_device": config.get("requested_device", requested),
        "device": device, "compute_type": compute,
        "cpu_threads": int(config.get("cpu_threads", 4)),
        "batch_size": int(config.get("batch_size", 8)) if device == "cuda" else 1,
        "beam_size": int(config.get("beam_size", 5)),
        "fallback_reason": config.get("fallback_reason") or ("cuda_unavailable" if requested == "auto" and device == "cpu" else None),
    }


def write_json(path: Path, data: dict):
    temporary = path.with_suffix(".partial.json")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def transcribe_with_runtime(config: dict, *, model_factory=None, batched_factory=None,
                            cuda_device_count=None, report=None, runtime_update=None) -> dict:
    """Use batched CUDA inference with one explicit, observable auto→CPU fallback."""
    if model_factory is None or batched_factory is None:
        from faster_whisper import BatchedInferencePipeline, WhisperModel
        model_factory, batched_factory = WhisperModel, BatchedInferencePipeline
    if cuda_device_count is None:
        from ctranslate2 import get_cuda_device_count
        cuda_device_count = get_cuda_device_count
    report = report or (lambda line: print(line, flush=True))
    runtime_update = runtime_update or (lambda runtime: None)
    try:
        count = cuda_device_count() if config.get("device", "auto") == "auto" else 0
    except RuntimeError:
        count = 0
    runtime = runtime_plan(config, count)
    started = time.monotonic()

    for attempt in range(2):
        model = pipeline = segments = None
        runtime["phase"] = "loading_model"
        runtime_update(runtime.copy())
        try:
            loading = time.monotonic()
            model = model_factory(config["model"], device=runtime["device"], compute_type=runtime["compute_type"],
                                  download_root=config["cache_dir"], cpu_threads=runtime["cpu_threads"], num_workers=1)
            runtime["model_load_ms"] = round((time.monotonic() - loading) * 1000)
            runtime["phase"] = "transcribing"
            runtime_update(runtime.copy())
            transcribing = time.monotonic()
            options = {"language": None if config["language"] == "auto" else config["language"],
                       "vad_filter": True, "word_timestamps": True, "beam_size": runtime["beam_size"],
                       "condition_on_previous_text": False}
            if config.get("vad_parameters") is not None:
                options["vad_parameters"] = config["vad_parameters"]
            if runtime["device"] == "cuda" and runtime["batch_size"] > 1:
                pipeline = batched_factory(model=model)
                segments, info = pipeline.transcribe(config["source"], batch_size=runtime["batch_size"], **options)
            else:
                segments, info = model.transcribe(config["source"], **options)
            result = []
            for segment in segments:
                if not segment.text.strip() or segment.end <= segment.start:
                    continue
                result.append({"start_ms": max(0, round(segment.start * 1000)), "end_ms": round(segment.end * 1000),
                               "text": segment.text.strip(),
                               "avg_logprob": getattr(segment, "avg_logprob", None),
                               "no_speech_prob": getattr(segment, "no_speech_prob", None),
                               "words_json": [{"start_ms": round(word.start * 1000), "end_ms": round(word.end * 1000),
                                               "word": word.word, "probability": word.probability} for word in segment.words or []]})
                report(f"segment_end_ms={round(segment.end * 1000)}")
            runtime.update(phase="complete", transcribe_ms=round((time.monotonic() - transcribing) * 1000),
                           total_ms=round((time.monotonic() - started) * 1000))
            runtime_update(runtime.copy())
            return {"language": info.language, "language_probability": info.language_probability,
                    "duration": info.duration, "segments": result, "runtime": runtime}
        except (RuntimeError, ValueError):
            if config.get("device", "auto") != "auto" or runtime["device"] != "cuda" or attempt:
                raise
            # Discard partial GPU output. Error strings, paths and transcript
            # text never become fallback metadata or operational logs.
            reason = "cuda_initialization_failed" if runtime["phase"] == "loading_model" else "cuda_execution_failed"
            pipeline = model = segments = None
            gc.collect()
            runtime.update(device="cpu", compute_type="int8", batch_size=1, fallback_reason=reason)
            report("progress_reset=1")
    raise RuntimeError("Transcription did not complete")


def main() -> None:
    request = Path(sys.argv[1])
    config = json.loads(request.read_text(encoding="utf-8"))
    runtime_path = request.with_name("transcription-runtime.json")
    result = transcribe_with_runtime(config, runtime_update=lambda runtime: write_json(runtime_path, runtime))
    write_json(Path(config["output"]), result)


if __name__ == "__main__":
    main()
