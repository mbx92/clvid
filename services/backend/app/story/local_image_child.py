"""Standalone offline inference runner; deliberately imports no backend modules."""
from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import re
import sys


def _needs_translation(text, language):
    if language == 'en':
        return False
    tokens = set(re.findall(r'[a-z]+', text.lower()))
    # Explicitly English prompts are common even in an Indonesian storyboard.
    english = {'the', 'with', 'white', 'black', 'photo', 'photograph', 'illustration', 'two', 'coffee', 'beans', 'on', 'of', 'and', 'background'}
    indonesian = {'yang', 'dan', 'dengan', 'di', 'sebuah', 'dua', 'satu', 'kopi', 'biji', 'piring', 'putih', 'merah', 'hitam', 'gambar', 'ilustrasi', 'latar', 'tampilkan', 'tangan', 'atas', 'samping', 'hangat'}
    id_hits, en_hits = len(tokens & indonesian), len(tokens & english)
    if en_hits >= 2 and id_hits == 0:
        return False
    return id_hits > 0 or language == 'id'


def _translation_terms(text):
    # Preserve the specialist terms used by the built-in coffee storyboards.
    # The small MT model otherwise confuses "kopi sangrai" with other crops or
    # translates "kopi lanang" literally as "male coffee".
    for source, target in (
        (r'\bbiji kopi (?:yang (?:sudah|telah) di)?sangrai\b', 'roasted coffee beans'),
        (r'\bbiji kopi lanang\b', 'peaberry coffee beans'),
        (r'\bkopi lanang\b', 'peaberry coffee'),
        (r'\bbuah kopi\b', 'coffee cherry'),
    ):
        text = re.sub(source, target, text, flags=re.IGNORECASE)
    return text


def _translate(texts, request, torch):
    selected = [i for i, value in enumerate(texts) if value and _needs_translation(value, request['prompt_language'])]
    if not selected:
        return texts, False
    directory = Path(request['translation_model'])
    if not (directory / 'pytorch_model.bin').is_file():
        raise RuntimeError('story_local_translation_missing')
    from transformers import MarianMTModel, MarianTokenizer
    tokenizer = MarianTokenizer.from_pretrained(str(directory), local_files_only=True)
    model = MarianMTModel.from_pretrained(str(directory), local_files_only=True).eval()
    result = list(texts)
    with torch.inference_mode():
        for index in selected:
            # Translate small sentences so useful visual directions do not vanish
            # at the tokenizer limit. SD's CLIP prompt is shortened afterwards.
            chunks = re.split(r'(?<=[.!?])\s+|\n+', _translation_terms(texts[index]))
            translated = []
            for chunk in chunks[:8]:
                encoded = tokenizer(chunk, return_tensors='pt', truncation=True, max_length=256)
                generated = model.generate(**encoded, max_new_tokens=256, num_beams=4)
                translated.append(tokenizer.decode(generated[0], skip_special_tokens=True))
            result[index] = ' '.join(translated)
    del model, tokenizer
    gc.collect()
    return result, True


def generate(request):
    import torch
    from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    device = request['device']
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('story_local_gpu_unavailable')
    (direction, style), translated = _translate([request['direction'], request['style']], request, torch)
    prompt = ', '.join(part for part in (direction, style, 'detailed image, clear subject, balanced composition') if part)
    dtype = torch.float16 if device == 'cuda' else torch.float32
    pipeline = StableDiffusionPipeline.from_pretrained(request['model'], torch_dtype=dtype,
                                                       variant='fp16', use_safetensors=True, local_files_only=True)
    if pipeline.safety_checker is None:
        raise RuntimeError('story_local_image_failed')
    pipeline.scheduler = DPMSolverMultistepScheduler.from_config(pipeline.scheduler.config)
    pipeline.set_progress_bar_config(disable=True)
    # PyTorch SDPA already uses memory-efficient attention. Slicing it slows down
    # inference. VAE slicing affects only the decode stage and is safe to enable.
    pipeline.enable_vae_slicing()
    pipeline.to(device)
    # Make the actual encoded prompt reproducible and keep it within CLIP's limit.
    encoded = pipeline.tokenizer(prompt, truncation=True, max_length=pipeline.tokenizer.model_max_length, return_tensors='pt')
    prompt = pipeline.tokenizer.decode(encoded['input_ids'][0], skip_special_tokens=True)
    generator = torch.Generator(device='cpu').manual_seed(request['seed'])
    with torch.inference_mode():
        result = pipeline(prompt=prompt, negative_prompt='text, captions, letters, watermark, logo, blurry, distorted, deformed',
                          num_inference_steps=request['steps'], guidance_scale=7.0,
                          width=request['width'], height=request['height'], generator=generator)
    if result.nsfw_content_detected and any(result.nsfw_content_detected):
        raise RuntimeError('story_local_image_filtered')
    output = Path(request['output'])
    temporary = output.with_name(output.name + '.partial')
    try:
        result.images[0].save(temporary, format='PNG')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'ok': True, 'device': device, 'prompt': prompt, 'prompt_translated': translated}


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    path = Path(request['result'])
    try:
        result = generate(request)
    except ImportError:
        result = {'ok': False, 'error_code': 'story_local_dependencies'}
    except Exception as error:
        code = str(error)
        if type(error).__name__ == 'OutOfMemoryError' or 'out of memory' in code.lower():
            code = 'story_local_out_of_memory'
        allowed = {'story_local_gpu_unavailable', 'story_local_image_filtered',
                   'story_local_translation_missing', 'story_local_out_of_memory'}
        result = {'ok': False, 'error_code': code if code in allowed else 'story_local_image_failed'}
        # Class only: avoid printing prompts, file contents, or credential-bearing URLs.
        print(type(error).__name__, file=sys.stderr)
    path.write_text(json.dumps(result), encoding='utf-8')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
