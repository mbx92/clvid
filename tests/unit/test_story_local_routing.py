from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.media.process import MediaError
from app.story.providers import capabilities, generate_image, generate_speech


def test_local_default_never_uses_configured_cloud_key(monkeypatch, tmp_path):
    settings = Settings(_env_file=None, openai_api_key='must-not-use', story_local_enabled=False)
    assert settings.story_media_provider == 'local'
    requests = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: requests.append(r))) as client:
        with pytest.raises(MediaError, match='lokal belum siap'):
            generate_image({'title':'Test'}, {}, tmp_path/'out.png', settings, lambda:False, client)
        with pytest.raises(MediaError, match='lokal belum siap'):
            generate_speech({'narration':'Test'}, None, tmp_path/'out.wav', settings, lambda:False, client)
    assert requests == [] and list(tmp_path.iterdir()) == []


def test_capabilities_follow_installed_models_and_default_indonesian(monkeypatch, tmp_path):
    settings = Settings(_env_file=None, story_local_enabled=True, story_models_root=tmp_path)
    monkeypatch.setattr('app.story.local_images.image_ready', lambda s:True)
    monkeypatch.setattr('app.story.local_speech.speech_voices', lambda s:['pocket-id-1','pocket-id-2','espeak-en'])
    result = capabilities(settings)
    assert result['provider'] == 'local' and result['images'] and result['speech']
    assert result['default_voice'] == 'pocket-id-1' and result['missing_models'] == []
    assert 'Indonesia' in result['voice_labels']['pocket-id-1']


def test_local_generation_dispatches_without_http(monkeypatch, tmp_path):
    settings = Settings(_env_file=None, story_local_enabled=True)
    calls = []
    monkeypatch.setattr('app.story.local_images.generate_image', lambda *a: calls.append('image') or {'provider':'local'})
    monkeypatch.setattr('app.story.local_speech.generate_speech', lambda *a: calls.append('speech') or {'provider':'local'})
    assert generate_image({}, {}, tmp_path/'a.png', settings, lambda:False)['provider'] == 'local'
    assert generate_speech({}, 'pocket-id-1', tmp_path/'a.wav', settings, lambda:False)['provider'] == 'local'
    assert calls == ['image','speech']
