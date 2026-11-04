import base64
import io
import json
import wave

import httpx
import pytest

from app.config import Settings
from app.media.process import Cancelled, MediaError
from app.story import providers


# A real 1px PNG, decoded locally; no remote assets or API keys are used.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aVZsAAAAASUVORK5CYII=")


def settings(**values):
    return Settings(_env_file=None, openai_api_key="test-only", story_media_provider='openai', **values)


def wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(24000)
        f.writeframes(b"\0\0" * 240)
    return output.getvalue()


def image_response(**extra):
    return {"data": [{"b64_json": base64.b64encode(PNG).decode()}], **extra}


def scene():
    return {"id": "scene-1", "title": "Kopi lanang", "narration": "Dua biji di atas piring.",
            "visual_note": "Dua biji kopi di piring putih"}


@pytest.mark.parametrize("aspect,size", [("portrait", "1024x1536"), ("landscape", "1536x1024"), ("square", "1024x1024")])
def test_image_request_uses_brief_and_returns_local_png(tmp_path, aspect, size):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=image_response(usage={"input_tokens": 12, "output_tokens": 34, "total_tokens": 46,
                                                           "untrusted": "must not persist"}))
    output = tmp_path / "scene.png"
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        meta = providers.generate_image(scene(), {"title": "Kuis kopi", "style_prompt": "Ilustrasi cat air", "aspect": aspect},
                                        output, settings(), lambda: False, client=client)
    request = requests[0]
    body = json.loads(request.content)
    assert request.url == "https://api.openai.com/v1/images/generations"
    assert request.headers["Authorization"] == "Bearer test-only"
    assert body["n"] == 1 and body["size"] == size and body["output_format"] == "png"
    assert body["model"] == "gpt-image-1-mini" and "response_format" not in body
    assert "Ilustrasi cat air" in body["prompt"] and scene()["visual_note"] in body["prompt"]
    assert output.read_bytes() == PNG and not (tmp_path / "scene.png.partial").exists()
    assert meta["usage"] == {"input_tokens": 12, "output_tokens": 34, "total_tokens": 46}
    assert meta["width"] == meta["height"] == 1


@pytest.mark.parametrize("response", [
    {"data": [{"url": "https://private.invalid/image.png"}]},
    {"data": []}, {"data": [{"b64_json": "not-base64"}]},
    {"data": [{"b64_json": base64.b64encode(b"not-png").decode()}]},
    {"data": [{"b64_json": None}]}, {"data": [{"b64_json": ""}, {"b64_json": ""}]},
    [], None,
])
def test_invalid_images_do_not_download_urls_or_create_assets(tmp_path, response):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=response)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises(MediaError) as error:
        providers.generate_image(scene(), {}, tmp_path / "bad.png", settings(), lambda: False, client=client)
    assert error.value.code == "story_image_invalid"
    assert len(requests) == 1 and not list(tmp_path.iterdir())


def test_speech_preserves_exact_narration_and_writes_wav(tmp_path):
    text = "  Bahasa Indonesia: kopi, bukan teh.\n\nA atau B?  "
    requests = []
    audio = wav()
    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=audio)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        metadata = providers.generate_speech({"narration": text}, "coral", tmp_path / "narration.wav",
                                             settings(), lambda: False, client=client)
    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/audio/speech"
    assert body["input"] == text and body["response_format"] == "wav"
    assert body["voice"] == "coral" and body["speed"] == 1.0
    assert (tmp_path / "narration.wav").read_bytes() == audio
    assert metadata["ai_voice"] is True and metadata["input_characters"] == len(text)
    assert "duration_ms" not in metadata


def test_legacy_speech_model_omits_unsupported_instructions(tmp_path):
    def respond(request):
        assert "instructions" not in json.loads(request.content)
        return httpx.Response(200, content=wav())
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        providers.generate_speech(scene(), None, tmp_path / "audio.wav", settings(story_speech_model="tts-1"), lambda: False, client=client)


@pytest.mark.parametrize("narration,voice", [("", "coral"), ("a" * 601, "coral"), ("hello", "made-up-voice")])
def test_bad_speech_inputs_fail_before_provider(tmp_path, narration, voice):
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected provider call"))) as client, pytest.raises(MediaError):
        providers.generate_speech({"narration": narration}, voice, tmp_path / "audio.wav", settings(), lambda: False, client=client)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("status,code", [(401, "story_provider_auth"), (403, "story_provider_auth"),
                                        (429, "story_provider_rate_limit"), (400, "story_provider_rejected"),
                                        (500, "story_provider_unavailable")])
def test_http_errors_are_redacted_and_not_retried(tmp_path, status, code):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "secret-test-key private user text"}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises(MediaError) as error:
        providers.generate_speech(scene(), "coral", tmp_path / "audio.wav", settings(), lambda: False, client=client)
    assert error.value.code == code
    assert "secret-test-key" not in str(error.value) and "private user text" not in str(error.value)
    assert len(calls) == 1 and not list(tmp_path.iterdir())


def test_network_timeout_not_retried_or_leaked(tmp_path):
    calls = []
    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret-test-key", request=request)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises(MediaError) as error:
        providers.generate_speech(scene(), "coral", tmp_path / "audio.wav", settings(), lambda: False, client=client)
    assert error.value.code == "story_provider_connection" and "secret-test-key" not in str(error.value)
    assert len(calls) == 1 and not list(tmp_path.iterdir())


def test_redirect_never_forwards_credentials(tmp_path):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(307, headers={"location": "https://different.invalid/receive"})
    with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=True) as client, pytest.raises(MediaError):
        providers.generate_speech(scene(), "coral", tmp_path / "audio.wav", settings(), lambda: False, client=client)
    assert len(calls) == 1 and calls[0].url.host == "api.openai.com"


@pytest.mark.parametrize("headers", [{}, {"Content-Length": "999999999"}, {"Content-Length": "invalid"}])
def test_oversize_response_is_bounded_and_not_published(tmp_path, monkeypatch, headers):
    monkeypatch.setattr(providers, "MAX_ASSET_BYTES", 100)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=wav(), headers=headers))) as client, pytest.raises(MediaError) as error:
        providers.generate_speech(scene(), "coral", tmp_path / "audio.wav", settings(), lambda: False, client=client)
    assert error.value.code == "story_provider_too_large" and not list(tmp_path.iterdir())


def test_cancel_before_request_has_no_side_effects(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected provider call"))) as client, pytest.raises(Cancelled):
        providers.generate_speech(scene(), "coral", tmp_path / "audio.wav", settings(), lambda: True, client=client)
    assert not list(tmp_path.iterdir())


def test_cancel_after_response_does_not_replace_existing_output(tmp_path):
    output = tmp_path / "audio.wav"
    output.write_bytes(b"existing recording")
    cancelled = False
    def respond(request):
        nonlocal cancelled
        cancelled = True
        return httpx.Response(200, content=wav())
    with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises(Cancelled):
        providers.generate_speech(scene(), "coral", output, settings(), lambda: cancelled, client=client)
    assert output.read_bytes() == b"existing recording" and len(list(tmp_path.iterdir())) == 1


def test_wrong_speech_format_is_rejected(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"MP3" * 100))) as client, pytest.raises(MediaError) as error:
        providers.generate_speech(scene(), "coral", tmp_path / "audio.wav", settings(), lambda: False, client=client)
    assert error.value.code == "story_speech_invalid" and not list(tmp_path.iterdir())


@pytest.mark.parametrize("url", ["http://public.invalid/v1", "https://user:password@api.openai.com/v1", "https://api.openai.com/v1?key=secret"])
def test_invalid_provider_configuration_stops_before_request(tmp_path, url):
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected provider call"))) as client, pytest.raises(MediaError) as error:
        providers.generate_speech(scene(), "coral", tmp_path / "audio.wav", settings(openai_base_url=url), lambda: False, client=client)
    assert error.value.code == "story_provider_configuration"


def test_capabilities_disclose_configuration_without_secrets():
    configured = providers.capabilities(settings())
    missing = providers.capabilities(Settings(_env_file=None, openai_api_key=""))
    assert configured["images"] and configured["speech"] and configured["alignment"]
    assert not missing["images"] and not missing["speech"] and missing["alignment"]
    assert "test-only" not in json.dumps(configured)
    assert "marin" in configured["voices"]
    assert "marin" not in providers.capabilities(settings(story_speech_model="tts-1"))["voices"]
