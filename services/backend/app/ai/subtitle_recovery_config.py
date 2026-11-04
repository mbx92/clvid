"""Version the recovery policy and snapshot only its non-secret ASR settings."""
from __future__ import annotations

from app.media.process import MediaError


ALGORITHM_VERSION = "clip-speech-v4"
ASR_FIELDS = ("model", "device", "compute_type", "beam_size", "cpu_threads", "batch_size")


def recovery_signature(settings) -> dict:
    # These inputs affect model selection/decoding, so a previous empty result
    # must not be reused when they change. Secrets and local paths stay out.
    asr = {name: getattr(settings, f"whisper_{name}") for name in ASR_FIELDS}
    asr["model"] = getattr(settings, "whisper_subtitle_model", None) or settings.whisper_model
    # Clip recovery uses phrase-level sequential decoding even on CUDA.
    asr["batch_size"] = 1
    return {"algorithm": ALGORITHM_VERSION, "asr": asr}


def settings_for_recovery(settings, signature: dict | None):
    # Older queued requests have no snapshot. Explicitly versioned requests
    # must run on a compatible worker, with the settings requested at enqueue.
    signature = signature or recovery_signature(settings)
    if signature.get("algorithm") != ALGORITHM_VERSION:
        raise MediaError("subtitle_pipeline_changed", "Versi pemrosesan subtitle berubah. Buat permintaan subtitle baru dari editor.")
    asr = signature.get("asr", {})
    if any(name not in asr for name in ASR_FIELDS):
        raise MediaError("subtitle_config_invalid", "Konfigurasi pemrosesan subtitle tidak lengkap. Buat permintaan baru dari editor.")
    snapshot = {f"whisper_{name}": asr[name] for name in ASR_FIELDS}
    # Pin both fields: a later server override must not bypass the queued model.
    snapshot["whisper_subtitle_model"] = asr["model"]
    return settings.model_copy(update=snapshot), signature
