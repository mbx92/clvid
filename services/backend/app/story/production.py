"""Versioned media proposals. Successful provider assets survive a failed retry."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
from copy import deepcopy
from pathlib import Path
from typing import Literal

from pydantic import Field
from sqlalchemy import select

from app.db import session_scope
from app.domain.models import Asset, ProviderUsage, Storyboard, utcnow
from app.media.process import MediaError
from app.storage.local import LocalStorage
from .schemas import Document, Strict


class ProductionInput(Strict):
    expected_version: int = Field(ge=1)
    mode: Literal['images', 'speech', 'captions', 'complete'] = 'complete'
    scene_id: str | None = Field(default=None, min_length=1, max_length=64)
    voice: str | None = Field(default=None, max_length=40)
    replace_existing: bool = False


def plan(document, mode, scene_id=None, replace_existing=False):
    """Keep billing targets identical in API preflight and worker execution."""
    result = []
    for scene in document['scenes']:
        if scene_id and scene['id'] != scene_id:
            continue
        image = mode in ('images', 'complete') and (replace_existing or not scene.get('asset_id'))
        if mode == 'complete' and not replace_existing and scene.get('visual', {}).get('kind', 'none') != 'none':
            image = False
        speech = mode in ('speech', 'complete') and bool(scene['narration'].strip()) and (replace_existing or not scene.get('audio_id'))
        captions = speech or mode in ('captions', 'complete') and bool(scene.get('audio_id'))
        if image or speech or captions:
            result.append((scene['id'], image, speech, captions))
    return result


def _checked(ctx, db, version):
    job, project = ctx.check(db)
    story = db.get(Storyboard, project.id)
    if not story or story.version != version:
        raise MediaError('revision_conflict', 'Storyboard sudah berubah. Jalankan produksi dari versi terbaru; aset yang selesai tetap tersedia.')
    return job, project


def _ready_asset(ctx, asset_id, kind):
    with session_scope() as db:
        _, project = ctx.check(db)
        asset = db.get(Asset, asset_id)
        if not asset or asset.project_id != project.id or asset.state != 'ready' or asset.meta_json.get('story_kind') != kind:
            raise MediaError('story_asset_missing', 'Aset adegan tidak tersedia. Pilih ulang media adegan.')
        return asset


def _generated_asset(ctx, scene, document, inputs, operation, directory):
    from .media import normalize_upload
    from .providers import generate_image, generate_speech
    settings = ctx.settings.model_copy(update=inputs.get('provider_config', {}))
    model = settings.story_image_model if operation == 'image' else settings.story_speech_model
    if settings.story_media_provider == 'local':
        from .local_images import IMAGE_MODEL
        from .local_speech import SPEECH_MODEL
        model = IMAGE_MODEL if operation == 'image' else ('espeak-ng' if inputs['voice'] == 'espeak-en' else SPEECH_MODEL)
    signature = hashlib.sha256(json.dumps({
        'job': ctx.job_id, 'scene': scene['id'], 'operation': operation, 'model': model,
        'voice': inputs['voice'], 'version': inputs['version'], 'provider': settings.story_media_provider,
    }, sort_keys=True).encode()).hexdigest()
    raw_asset = None
    storage = LocalStorage()
    with session_scope() as db:
        _, project = _checked(ctx, db, inputs['version'])
        # Assets are scoped to this job, preventing reuse after intentional regeneration.
        assets = db.scalars(select(Asset).where(Asset.project_id == project.id, Asset.kind.in_(('story_media', 'story_raw'))))
        for asset in assets:
            if asset.meta_json.get('generation_key') == signature and storage.path(asset.storage_key).is_file():
                if asset.kind == 'story_media' and asset.state == 'ready':
                    return asset
                if asset.kind == 'story_raw':
                    raw_asset = asset
    ctx.stage('story_images' if operation == 'image' else 'story_speech')
    source = directory / ('generated.png' if operation == 'image' else 'generated.wav')
    # A different suffix is needed because normalization writes a canonical .png/.m4a.
    source = source.with_name(source.stem + '.source' + source.suffix)
    if raw_asset:
        shutil.copyfile(storage.path(raw_asset.storage_key), source)
        report = raw_asset.meta_json['provider_report']
    else:
        report, outcome, started = {}, 'failed', time.monotonic()
        try:
            if operation == 'image':
                seeded_scene = {**scene, '_generation_seed': int(signature[:8], 16)}
                report = generate_image(seeded_scene, document, source, settings, ctx.cancelled)
            else:
                report = generate_speech(scene, inputs['voice'], source, settings, ctx.cancelled)
            outcome = 'succeeded'
        finally:
            with session_scope() as db:
                usage = report.get('usage') or {}
                db.add(ProviderUsage(job_attempt_id=ctx.attempt_id, provider=report.get('provider', settings.story_media_provider), model=model,
                                     input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'),
                                     latency_ms=round((time.monotonic() - started) * 1000), outcome=outcome))
        # Persist the original response before FFmpeg. A failed normalization can
        # resume without purchasing the same scene a second time.
        with session_scope() as db:
            _, project = ctx.check(db)
            raw_key = storage.new_key(project.id, source.suffix)
            final = storage.publish(source, raw_key)
            raw_asset = Asset(project_id=project.id, kind='story_raw', storage_key=raw_key,
                              bytes=final.stat().st_size, state='pending',
                              meta_json={'generation_key': signature, 'provider_report': report})
            db.add(raw_asset)
            db.flush()
        shutil.copyfile(storage.path(raw_key), source)
    normalized_input = source.with_suffix('.upload')
    source.replace(normalized_input)
    output, mime, metadata = normalize_upload(normalized_input, source.suffix, settings)
    filename = f"{scene['id']}-{'gambar' if operation == 'image' else 'narasi'}{output.suffix}"
    key = None
    committed = False
    try:
        with session_scope() as db:
            # Keep the generated asset if the user edited the document while the
            # provider ran; only applying its proposal requires the old version.
            _, project = ctx.check(db)
            key = storage.new_key(project.id, output.suffix)
            final = storage.publish(output, key)
            asset = Asset(project_id=project.id, kind='story_media', storage_key=key,
                          bytes=final.stat().st_size, mime=mime, state='ready',
                          meta_json={**metadata, 'filename': filename, 'generated': True,
                                     'generation_key': signature, 'scene_id': scene['id'],
                                     'provider': report.get('provider', settings.story_media_provider), 'model': model,
                                     'voice': inputs['voice'] if operation == 'speech' else None,
                                     'usage': report.get('usage'), 'ai_generated_voice': operation == 'speech',
                                     'speech_narration': scene['narration'] if operation == 'speech' else None,
                                     **{k: report[k] for k in ('seed', 'steps', 'model_revision', 'license', 'license_url', 'source_url',
                                                             'attribution', 'prompt', 'prompt_translated', 'translation_model',
                                                             'spoken_text', 'device') if k in report}})
            db.add(asset)
            raw_row = db.get(Asset, raw_asset.id)
            db.delete(raw_row)
            project.updated_at = utcnow()
            db.flush()
        committed = True
        storage.remove(raw_asset.storage_key)
        return asset
    finally:
        if key and not committed:
            storage.remove(key)


def _fit_audio(scene, asset, assets, warnings):
    duration = asset.meta_json.get('duration_ms', 0)
    required = max(1000, math.ceil(duration / 100) * 100)
    if not duration or required > 30000:
        raise MediaError('story_speech_too_long', 'Rekaman adegan melebihi 30 detik. Pecah narasi menjadi beberapa adegan atau unggah potongan audio yang lebih pendek.')
    if required > scene['duration_ms']:
        video = assets.get(scene.get('asset_id'))
        if video and video.meta_json.get('story_kind') == 'video' and scene['media_start_ms'] + required > video.meta_json['duration_ms']:
            raise MediaError('story_voice_video_bounds', 'Rekaman lebih panjang dari video adegan. Pilih video lebih panjang atau ganti dengan gambar.')
        scene['duration_ms'] = required
        warnings.append(f"Adegan {scene['id']}: durasi diperpanjang menjadi {required / 1000:g} detik agar narasi selesai.")
    return duration


def produce(ctx, scratch: Path):
    from app.jobs.tasks import _complete
    from .alignment import align_audio
    from .providers import capabilities
    from app.media.render import check_disk
    with session_scope() as db:
        job, project = ctx.check(db)
        inputs = deepcopy(job.input_json)
        _checked(ctx, db, inputs['version'])
        assets = {a.id: a for a in db.scalars(select(Asset).where(Asset.project_id == project.id, Asset.state == 'ready'))}
    if inputs.get('producer_version') != 2:
        raise MediaError('story_version_changed', 'Versi produksi berubah. Jalankan produksi baru.')
    document = Document.model_validate(inputs['document']).model_dump()
    targets = plan(document, inputs['mode'], inputs.get('scene_id'), inputs.get('replace_existing', False))
    available = capabilities(ctx.settings.model_copy(update=inputs.get('provider_config', {})))
    if any(t[1] for t in targets) and not available['images'] or any(t[2] for t in targets) and not available['speech']:
        raise MediaError('story_provider_not_configured', 'Layanan gambar atau suara belum dikonfigurasi di server.')
    check_disk(scratch, max(1, len(targets)) * 64 * 1024**2, ctx.settings.min_free_disk_bytes)
    warnings = []
    scenes = {s['id']: s for s in document['scenes']}
    for index, (scene_id, image, speech, captions) in enumerate(targets):
        with session_scope() as db:
            _checked(ctx, db, inputs['version'])
        scene = scenes[scene_id]
        directory = scratch / scene_id
        directory.mkdir(parents=True, exist_ok=True)
        if image:
            asset = _generated_asset(ctx, scene, document, inputs, 'image', directory)
            assets[asset.id] = asset
            scene['asset_id'], scene['media_start_ms'] = asset.id, 0
        if speech:
            asset = _generated_asset(ctx, scene, document, inputs, 'speech', directory)
            assets[asset.id] = asset
            scene['audio_id'] = asset.id
            scene.update(captions=[], caption_audio_id=None, caption_narration='')
        if captions:
            audio = _ready_asset(ctx, scene['audio_id'], 'audio')
            duration = _fit_audio(scene, audio, assets, warnings)
            if sum(s['duration_ms'] for s in document['scenes']) > 180000:
                raise MediaError('story_duration_limit', 'Narasi membuat video lebih dari 3 menit. Pendekkan naskah atau bagi menjadi beberapa video. Aset selesai tetap tersedia.')
            ctx.stage('story_captions')
            spoken = audio.meta_json.get('spoken_text') if audio.meta_json.get('speech_narration') == scene['narration'] else None
            aligned = align_audio(LocalStorage().path(audio.storage_key), directory / 'alignment',
                                  narration=spoken or scene['narration'], duration_ms=duration, settings=ctx.settings,
                                  cancelled=ctx.cancelled, progress=ctx.progress)
            narration = scene['narration'] if spoken else aligned['narration']
            scene.update(narration=narration, captions=aligned['captions'],
                         caption_audio_id=scene['audio_id'], caption_narration=narration)
            if spoken and spoken != narration:
                warnings.append(f"Adegan {scene_id}: angka dibaca sebagai kata oleh narator lokal. Naskah asli tetap disimpan; subtitle mengikuti ucapan.")
            warnings.extend(f"Adegan {scene_id}: {warning}" for warning in aligned.get('warnings', []))
        ctx.progress((index + 1) / max(1, len(targets)))
    document = Document.model_validate(document).model_dump()
    with session_scope() as db:
        _checked(ctx, db, inputs['version'])
        _complete(db, ctx, {'document': document, 'base_version': inputs['version'], 'mode': inputs['mode'],
                            'warnings': warnings, 'message': 'Aset dan subtitle siap ditinjau. Draft belum diubah.'})
