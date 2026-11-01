import subprocess
import sys

import pytest

from app.media.process import MediaError
from app.media.remote_guard import public_address, validate_url


@pytest.mark.parametrize('url', [
    'file:///etc/passwd', 'ftp://example.com/video.mp4', 'https://user:pass@example.com/v',
    'http://localhost/v', 'http://localhost./v', 'http://host.internal/v',
    'http://127.0.0.1/v', 'http://169.254.169.254/latest/meta-data',
    'http://[::1]/v', 'http://10.0.0.1/v', 'https://example.com:8000/v',
    'https://example.com/\nvideo', 'https://example.com\\@localhost/v',
])
def test_unsafe_url_rejected(url):
    with pytest.raises(MediaError, match='URL HTTP/HTTPS'):
        validate_url(url)


@pytest.mark.parametrize('address', ['127.0.0.1', '0.0.0.0', '192.168.1.1', '169.254.169.254',
                                    '100.64.0.1', '::1', 'fc00::1', 'ff02::1', '::ffff:127.0.0.1',
                                    '64:ff9b::7f00:1', '2002:7f00:1::'])
def test_nonpublic_addresses_rejected(address):
    assert not public_address(address)


def test_public_urls_and_addresses():
    assert validate_url('https://example.com/video.mp4?token=123#player') == 'https://example.com/video.mp4?token=123'
    assert public_address('1.1.1.1')
    assert public_address('2606:4700:4700::1111')


def test_network_guard_blocks_private_dns_redirect_targets_and_rebinding():
    # Audit hooks are process-wide and deliberately cannot be removed.
    script = '''
import socket
from app.media.remote_guard import install_network_guard
socket.getaddrinfo = lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 80))]
install_network_guard()
for call in (lambda: socket.getaddrinfo('redirect.example', 80),
             lambda: socket.socket().connect(('127.0.0.1', 80)),
             lambda: socket.socket().connect(('localhost', 80))):
    try: call()
    except PermissionError: pass
    else: raise AssertionError('Private target was allowed')
print('guarded')
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'guarded' in result.stdout


def test_external_media_process_cannot_fetch_network(tmp_path):
    script = '''
import pathlib, subprocess, sys
from app.media.import_child import install_process_guard
install_process_guard(pathlib.Path(sys.argv[1]).resolve())
for args in (['ffmpeg', '-i', 'https://example.com/input.m3u8', 'out.mp4'], ['curl', 'https://example.com']):
    try: subprocess.Popen(args)
    except PermissionError: pass
    else: raise AssertionError('External networking was allowed')
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_download_child_does_not_inherit_secrets_or_leave_signed_url(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from app.media.import_url import download_video
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-provider-secret')
    monkeypatch.setenv('DATABASE_URL', 'test-database-secret')
    monkeypatch.setenv('HTTPS_PROXY', 'http://private-proxy:8080')

    def process(args, **kwargs):
        environment = kwargs['env']
        assert not {'DEEPSEEK_API_KEY', 'DATABASE_URL', 'HTTPS_PROXY'} & environment.keys()
        (tmp_path / 'download-output.json').write_text(json.dumps({'error': {'code': 'url_download_failed', 'message': 'Unavailable'}}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr('app.media.import_url.run_process', process)
    settings = SimpleNamespace(max_upload_bytes=1000, max_video_seconds=60, max_video_width=1920,
                               max_video_height=1080, min_free_disk_bytes=0, ffmpeg_path='ffmpeg', media_timeout_seconds=10)
    with pytest.raises(MediaError):
        download_video('https://example.com/video?token=test', tmp_path, settings=settings)
    assert not (tmp_path / 'download-input.json').exists()
