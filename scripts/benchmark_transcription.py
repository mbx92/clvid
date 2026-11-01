"""Isolated transcription benchmark; prints counts/timing, never speech text.

Use a read-only sample and a populated model cache. The benchmark refuses model
downloads so comparisons measure decoding rather than network availability.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

from faster_whisper import BatchedInferencePipeline, WhisperModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--compute-type", default="auto")
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--cache", default="/data/whisper")
    args = parser.parse_args()
    compute_type = args.compute_type if args.compute_type != "auto" else ("float16" if args.device == "cuda" else "int8")
    started = time.perf_counter()
    model = WhisperModel(args.model, device=args.device, compute_type=compute_type,
                         cpu_threads=args.cpu_threads, num_workers=1, download_root=args.cache,
                         local_files_only=True)
    loaded = time.perf_counter()
    options = {"language": None if args.language == "auto" else args.language,
               "vad_filter": True, "word_timestamps": True, "beam_size": args.beam_size,
               "condition_on_previous_text": False}
    decoder = BatchedInferencePipeline(model=model) if args.batch_size > 1 else model
    if args.batch_size > 1:
        options["batch_size"] = args.batch_size
    segments, info = decoder.transcribe(str(args.source), **options)
    segment_count = word_count = characters = 0
    digest = hashlib.sha256()
    for segment in segments:
        segment_count += 1
        word_count += len(segment.words or [])
        characters += len(segment.text)
        digest.update(segment.text.encode("utf-8"))
    finished = time.perf_counter()
    print(json.dumps({
        "model": args.model, "device": args.device, "compute_type": compute_type,
        "cpu_threads": args.cpu_threads, "batch_size": args.batch_size, "beam_size": args.beam_size,
        "source_duration_seconds": round(info.duration, 3), "language": info.language,
        "load_seconds": round(loaded - started, 3), "transcribe_seconds": round(finished - loaded, 3),
        "total_seconds": round(finished - started, 3), "segment_count": segment_count,
        "word_count": word_count, "characters": characters, "transcript_sha256": digest.hexdigest(),
        "faster_whisper": importlib.metadata.version("faster-whisper"),
        "ctranslate2": importlib.metadata.version("ctranslate2"),
    }))


if __name__ == "__main__":
    main()
