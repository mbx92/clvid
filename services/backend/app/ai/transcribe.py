from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from app.media.process import MediaError, run_process


def transcribe(source: Path, directory: Path, *, model="small", device="auto", compute_type="auto",
               language="auto", cache_dir="/data/whisper", cpu_threads=4, batch_size=8, beam_size=5,
               duration_ms: int | None = None, timeout=14400, cancelled=None, progress=None) -> dict:
    if model.endswith(".en") and language != "en":
        raise MediaError("invalid_whisper_model", "Model English-only tidak dapat digunakan untuk bahasa Indonesia atau deteksi otomatis.")
    directory.mkdir(parents=True, exist_ok=True)
    request = directory / "transcription-input.json"
    output = directory / "transcription-output.json"
    started = time.monotonic()
    config = {"source": str(source.resolve()), "output": str(output.resolve()),
              "model": model, "device": device, "compute_type": compute_type,
              "language": language, "cache_dir": cache_dir, "cpu_threads": cpu_threads,
              "batch_size": batch_size, "beam_size": beam_size}
    request.write_text(json.dumps(config), encoding="utf-8")
    result = run_process([sys.executable, "-m", "app.ai.whisper_child", str(request.resolve())],
                         timeout=timeout, cancelled=cancelled, progress=progress, duration_ms=duration_ms)
    runtime_path = directory / "transcription-runtime.json"
    if result.returncode and device == "auto" and runtime_path.exists():
        # Some native CUDA library failures abort instead of raising Python
        # exceptions. Only retry a child known to have selected CUDA, once.
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            runtime = {}
        if runtime.get("device") == "cuda":
            config.update(device="cpu", compute_type="int8", requested_device="auto", fallback_reason="cuda_process_failed")
            request.write_text(json.dumps(config), encoding="utf-8")
            if progress:
                progress(0.0 if duration_ms else None)
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise MediaError("process_timeout", "Transkripsi melewati batas waktu yang dikonfigurasi.")
            result = run_process([sys.executable, "-m", "app.ai.whisper_child", str(request.resolve())],
                                 timeout=remaining, cancelled=cancelled, progress=progress, duration_ms=duration_ms)
    if result.returncode or not output.exists():
        raise MediaError("transcription_failed", "Transkripsi gagal. Periksa ketersediaan model, memori, dan konfigurasi worker.")
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(data.get("segments"), list) or not data.get("language"):
            raise ValueError()
        data.setdefault("runtime", {})["total_ms"] = round((time.monotonic() - started) * 1000)
        return data
    except (ValueError, KeyError) as exc:
        raise MediaError("transcription_invalid", "Hasil transkripsi tidak dapat dibaca.") from exc
