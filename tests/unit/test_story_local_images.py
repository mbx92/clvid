import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from app.media.process import Cancelled, MediaError, ProcessResult
from app.story.local_images import (MODEL_FILES, MODEL_ID, generate_image, image_ready,
                                     image_request, translation_ready)
from app.story.local_image_child import _needs_translation, _translation_terms


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(story_models_root=tmp_path/'models', story_local_python='/isolated/bin/python',
                           story_local_image_steps=20, story_local_image_device='auto',
                           story_local_prompt_language='id', story_local_timeout_seconds=600)


def installed(settings):
    directory = settings.story_models_root/'images/sd15'
    for name in MODEL_FILES:
        path = directory/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')


def test_readiness_requires_full_local_pipeline_including_safety_checker(settings):
    assert not image_ready(settings)
    installed(settings)
    assert image_ready(settings)
    (settings.story_models_root/'images/sd15/safety_checker/model.fp16.safetensors').unlink()
    assert not image_ready(settings)
    assert not translation_ready(settings)


@pytest.mark.parametrize('aspect,size', [('portrait',(512,768)), ('landscape',(768,512)), ('square',(512,512))])
def test_bounded_request_is_reproducible_and_uses_visual_direction(settings, aspect, size):
    scene={'id':'beans','visual_note':'Dua biji kopi di piring putih.', 'title':'Ignored when visual exists'}
    doc={'aspect':aspect, 'style_prompt':'Editorial hangat'}
    request=image_request(scene,doc,settings)
    assert (request['width'],request['height']) == size
    assert request['seed'] == image_request(scene,doc,settings)['seed']
    assert request['direction'] == scene['visual_note']
    assert 0 <= request['seed'] <= 2**32-1
    assert request['seed'] != image_request({**scene,'visual_note':'Pohon kopi'},doc,settings)['seed']
    assert image_request({**scene,'_generation_seed':42},doc,settings)['seed'] == 42


@pytest.mark.parametrize('field,value',[('story_local_image_steps',100),('story_local_image_device','remote'),('story_local_prompt_language','jp')])
def test_invalid_worker_configuration_is_rejected(settings,field,value):
    setattr(settings,field,value)
    with pytest.raises(MediaError,match='tidak valid'):
        image_request({'title':'Coffee'}, {'aspect':'portrait'}, settings)


def test_missing_model_and_cancel_do_not_launch_inference(settings, tmp_path, monkeypatch):
    monkeypatch.setattr('app.story.local_images.run_process', lambda *a,**k: pytest.fail('must not launch'))
    with pytest.raises(MediaError,match='belum terpasang'):
        generate_image({'title':'Coffee'}, {}, tmp_path/'image.png', settings,lambda:False)
    with pytest.raises(Cancelled):
        generate_image({'title':'Coffee'}, {}, tmp_path/'image.png', settings,lambda:True)


def test_inference_uses_isolated_python_offline_environment_and_records_actual_prompt(settings,tmp_path,monkeypatch):
    installed(settings)
    monkeypatch.setenv('LD_LIBRARY_PATH','/backend/cuda/wrong-version')
    def child(args, **kwargs):
        assert args[0] == '/isolated/bin/python'
        assert Path(args[1]).name == 'local_image_child.py'
        assert kwargs['env']['HF_HUB_OFFLINE'] == '1' and kwargs['env']['TRANSFORMERS_OFFLINE'] == '1'
        assert 'LD_LIBRARY_PATH' not in kwargs['env'] and kwargs['timeout'] == 600
        request=json.loads(Path(args[2]).read_text())
        output=Path(request['output'])
        output.write_bytes(b'\x89PNG\r\n\x1a\n'+b'\0\0\0\rIHDR'+struct.pack('>II',512,768))
        Path(request['result']).write_text(json.dumps({'ok':True,'device':'cuda','prompt':'two coffee beans on a white plate','prompt_translated':True}))
        return ProcessResult('','',0)
    monkeypatch.setattr('app.story.local_images.run_process',child)
    output=tmp_path/'out.png'
    report=generate_image({'id':'one','visual_note':'Dua biji kopi di piring putih.'},{'aspect':'portrait'},output,settings,lambda:False)
    assert output.is_file() and report['provider'] == 'local' and report['model'] == MODEL_ID
    assert report['prompt_translated'] is True and report['device'] == 'cuda'
    assert not list(tmp_path.glob('*.json'))


@pytest.mark.parametrize('error_code,expected',[('story_local_out_of_memory','Memori GPU'),('story_local_image_filtered','pemeriksaan konten'),('story_local_translation_missing','penerjemah'),('leak the secret','Generator gambar lokal gagal')])
def test_worker_errors_are_safe_and_leave_no_image(settings,tmp_path,monkeypatch,error_code,expected):
    installed(settings)
    def child(args,**kwargs):
        request=json.loads(Path(args[2]).read_text())
        Path(request['output']).write_bytes(b'partial')
        Path(request['result']).write_text(json.dumps({'ok':False,'error_code':error_code}))
        return ProcessResult('','private-secret',1)
    monkeypatch.setattr('app.story.local_images.run_process',child)
    output=tmp_path/'out.png'
    with pytest.raises(MediaError,match=expected):
        generate_image({'title':'Coffee'},{},output,settings,lambda:False)
    assert not output.exists()


@pytest.mark.parametrize('text,language,want',[
    ('Dua biji kopi di piring putih.','id',True),
    ('Two coffee beans on a white plate.','id',False),
    ('Dua biji kopi','en',False),
    ('a colorful city skyline','auto',False),
    ('Pemandangan pegunungan','id',True),
])
def test_prompt_language_handling(text,language,want):
    assert _needs_translation(text,language) is want


def test_coffee_terms_survive_translation_without_changing_unrelated_text():
    assert _translation_terms('Dua biji kopi sangrai dan buah kopi merah.') == 'Dua roasted coffee beans dan coffee cherry merah.'
    assert _translation_terms('Biji kopi lanang tumbuh sendiri.') == 'peaberry coffee beans tumbuh sendiri.'
    assert _translation_terms('Langit berwarna biru.') == 'Langit berwarna biru.'
