"""Offline SD1.5 generation in a short-lived process so Whisper can reuse VRAM."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys

from app.media.process import Cancelled, MediaError, run_process


MODEL_ID = 'stable-diffusion-v1-5/stable-diffusion-v1-5'
IMAGE_MODEL = MODEL_ID
MODEL_REVISION = '451f4fe16113bff5a5d2269ed5ad43b0592e9a14'
TRANSLATION_ID = 'Helsinki-NLP/opus-mt-id-en'
TRANSLATION_REVISION = '9a7f1b0d0dfe0a92ba691030b01d6f23f966e7ec'
MODEL_FILES = (
    'model_index.json', 'feature_extractor/preprocessor_config.json',
    'safety_checker/config.json', 'safety_checker/model.fp16.safetensors',
    'scheduler/scheduler_config.json', 'text_encoder/config.json',
    'text_encoder/model.fp16.safetensors', 'tokenizer/merges.txt',
    'tokenizer/special_tokens_map.json', 'tokenizer/tokenizer_config.json',
    'tokenizer/vocab.json', 'unet/config.json',
    'unet/diffusion_pytorch_model.fp16.safetensors', 'vae/config.json',
    'vae/diffusion_pytorch_model.fp16.safetensors',
)
TRANSLATION_FILES = ('config.json', 'generation_config.json', 'pytorch_model.bin',
                     'source.spm', 'target.spm', 'tokenizer_config.json', 'vocab.json')
SIZES = {'portrait': (512, 768), 'landscape': (768, 512), 'square': (512, 512)}
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def model_ready(settings):
    directory = Path(settings.story_models_root) / 'images' / 'sd15'
    return all((directory / name).is_file() and (directory / name).stat().st_size > 0 for name in MODEL_FILES)


image_ready = model_ready


def translation_ready(settings):
    directory = Path(settings.story_models_root) / 'translation' / 'id-en'
    return all((directory / name).is_file() and (directory / name).stat().st_size > 0 for name in TRANSLATION_FILES)


def image_request(scene, document, settings):
    aspect = document.get('aspect', 'portrait')
    if aspect not in SIZES:
        raise MediaError('story_image_input', 'Format gambar tidak valid.')
    direction = (scene.get('visual_note') or scene.get('title') or scene.get('narration') or '').strip()
    if not direction:
        raise MediaError('story_image_input', 'Isi arahan visual, judul, atau narasi sebelum membuat gambar.')
    style = (document.get('style_prompt') or '').strip()
    steps = getattr(settings, 'story_local_image_steps', 20)
    device = getattr(settings, 'story_local_image_device', 'auto')
    language = getattr(settings, 'story_local_prompt_language', 'id')
    if type(steps) is not int or not 4 <= steps <= 50 or device not in ('auto', 'cuda', 'cpu') or language not in ('auto', 'id', 'en'):
        raise MediaError('story_local_configuration', 'Pengaturan generator gambar lokal tidak valid.')
    seed = int.from_bytes(hashlib.sha256(json.dumps(
        {'id': scene.get('id'), 'direction': direction, 'style': style, 'aspect': aspect},
        sort_keys=True, ensure_ascii=False).encode()).digest()[:4], 'big')
    supplied_seed = scene.get('_generation_seed')
    if supplied_seed is not None:
        if type(supplied_seed) is not int or not 0 <= supplied_seed <= 2**32 - 1:
            raise MediaError('story_local_configuration', 'Seed gambar lokal tidak valid.')
        seed = supplied_seed
    width, height = SIZES[aspect]
    return {'model': str((Path(settings.story_models_root) / 'images' / 'sd15').resolve()),
            'translation_model': str((Path(settings.story_models_root) / 'translation' / 'id-en').resolve()),
            'direction': direction[:600], 'style': style[:2000], 'prompt_language': language,
            'width': width, 'height': height, 'steps': steps, 'device': device, 'seed': seed}


def generate_image(scene, document, output_path, settings, cancelled):
    if cancelled():
        raise Cancelled()
    if not model_ready(settings):
        raise MediaError('story_local_image_missing', 'Model gambar lokal belum terpasang. Jalankan pemasangan model Story Studio di server.')
    request = image_request(scene, document, settings)
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    request_path = output.with_name(output.name + '.request.json')
    result_path = output.with_name(output.name + '.result.json')
    request.update(output=str(output), result=str(result_path))
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
    result_path.unlink(missing_ok=True)
    env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
           'HF_HUB_DISABLE_TELEMETRY': '1', 'DO_NOT_TRACK': '1', 'TOKENIZERS_PARALLELISM': 'false'}
    env.pop('LD_LIBRARY_PATH', None)
    # The inference virtualenv is separate from the backend to avoid CUDA version
    # conflicts. Executing this file's sibling needs no app dependency in that venv.
    python = getattr(settings, 'story_local_python', '') or sys.executable
    child = Path(__file__).with_name('local_image_child.py')
    timeout = getattr(settings, 'story_local_timeout_seconds', 600)
    try:
        process = run_process([python, str(child), str(request_path)], timeout=timeout, cancelled=cancelled, env=env)
        try:
            result = json.loads(result_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            result = {}
        if process.returncode or not result.get('ok'):
            code = result.get('error_code', 'story_local_image_failed')
            messages = {
                'story_local_gpu_unavailable': 'GPU untuk gambar lokal tidak tersedia. Periksa Docker GPU atau pilih mode CPU pada server.',
                'story_local_out_of_memory': 'Memori GPU tidak cukup. Tutup aplikasi GPU lain atau pilih mode CPU, lalu coba lagi.',
                'story_local_image_filtered': 'Gambar lokal tidak lolos pemeriksaan konten. Ubah arahan visual lalu coba lagi.',
                'story_local_dependencies': 'Paket generator gambar lokal belum lengkap. Jalankan pemasangan runtime lokal di server.',
                'story_local_translation_missing': 'Model penerjemah arahan belum terpasang. Pasang model lokal atau gunakan arahan bahasa Inggris.',
            }
            raise MediaError(code if code in messages else 'story_local_image_failed', messages.get(code, 'Generator gambar lokal gagal. Periksa model dan runtime lokal, lalu coba lagi.'))
        with output.open('rb') as handle:
            header = handle.read(24)
        if (output.stat().st_size > 20 * 1024**2 or len(header) != 24 or
                not header.startswith(PNG_SIGNATURE) or header[12:16] != b'IHDR' or
                struct.unpack('>II', header[16:24]) != (request['width'], request['height'])):
            raise MediaError('story_local_image_invalid', 'Hasil gambar lokal tidak valid. Coba kembali dengan arahan visual lain.')
        if cancelled():
            raise Cancelled()
        return {'provider': 'local', 'model': MODEL_ID, 'model_revision': MODEL_REVISION,
                'generated': True, 'width': request['width'], 'height': request['height'],
                'seed': request['seed'], 'steps': request['steps'], 'device': result['device'],
                'prompt': result['prompt'][:2000], 'prompt_translated': bool(result.get('prompt_translated')),
                'translation_model': TRANSLATION_ID if result.get('prompt_translated') else None,
                'usage': {}}
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    finally:
        request_path.unlink(missing_ok=True)
        result_path.unlink(missing_ok=True)
