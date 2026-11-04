"""Run Pocket TTS in an isolated CPU process without backend dependencies."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main(request):
    import soundfile as sf
    import torch
    from pocket_tts import TTSModel

    # Read local files only. Network URLs must be removed during model install.
    directory = Path(request['model_root']).resolve()
    config = directory / 'config.yaml'
    data = json.loads(config.read_text(encoding='utf-8'))
    weights = (directory / data['weights_path']).resolve()
    tokenizer = (directory / data['flow_lm']['lookup_table']['tokenizer_path']).resolve()
    prompt = Path(request['voice']).resolve()
    if any(not path.is_relative_to(directory) or not path.is_file() for path in (weights, tokenizer, prompt)):
        raise ValueError('Model files must be installed inside the local model directory.')
    torch.set_num_threads(request['threads'])
    torch.set_num_interop_threads(1)
    torch.manual_seed(731)
    data['weights_path'] = str(weights)
    data['flow_lm']['lookup_table']['tokenizer_path'] = str(tokenizer)
    runtime_config = Path(request['output']).with_name('pocket-runtime-config.yaml')
    runtime_config.write_text(json.dumps(data), encoding='utf-8')
    try:
        model = TTSModel.load_model(config=runtime_config, temp=.3, eos_threshold=-6.0)
    finally:
        runtime_config.unlink(missing_ok=True)
    state = model.get_state_for_audio_prompt(str(prompt))
    # Pocket spawns a generation thread and updates its KV cache there. Wrapping
    # this call in inference_mode creates tensors the other thread cannot update;
    # the library applies no_grad inside its own generation methods instead.
    audio = model.generate_audio(state, request['text'])
    sf.write(request['output'], audio.detach().cpu().numpy(), model.sample_rate, subtype='PCM_16', format='WAV')


if __name__ == '__main__':
    payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    try:
        main(payload)
    except Exception as exc:
        Path(payload['error']).write_text(json.dumps({'code': 'dependency_missing' if isinstance(exc, ImportError) else 'generation_failed'}), encoding='utf-8')
        raise SystemExit(1) from None
