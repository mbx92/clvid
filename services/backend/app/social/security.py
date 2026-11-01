import hashlib
import hmac
import json
import time
from urllib.parse import urlparse
from cryptography.fernet import Fernet
from app.config import get_settings
from app.api.errors import AppError

PLATFORMS = ('youtube', 'instagram', 'tiktok')


def cipher():
    try:
        return Fernet(get_settings().social_encryption_key.encode())
    except (ValueError, TypeError):
        raise AppError(503,'SOCIAL_KEY','Kunci penyimpanan koneksi sosial belum dikonfigurasi.')


def seal(data):
    return cipher().encrypt(json.dumps(data).encode()).decode()


def unseal(data):
    return json.loads(cipher().decrypt(data.encode())) if data else {}


def callback_url(platform):
    return get_settings().app_origin.rstrip('/') + f'/api/v1/social/oauth/{platform}/callback'


def configured(platform):
    s = get_settings()
    try: cipher()
    except AppError: return False
    if platform == 'youtube': return bool(s.youtube_client_id and s.youtube_client_secret)
    if platform == 'instagram': return bool(s.meta_client_id and s.meta_client_secret and s.meta_graph_version)
    if platform == 'tiktok': return bool(s.tiktok_client_key and s.tiktok_client_secret)
    return False


def public_media_ready():
    p = urlparse(get_settings().social_public_base_url)
    return p.scheme == 'https' and bool(p.hostname) and p.hostname not in ('localhost','127.0.0.1') and not p.username and not p.query and not p.fragment


def media_signature(post_id, expires):
    return hmac.new(get_settings().social_encryption_key.encode(),f'{post_id}:{expires}'.encode(),hashlib.sha256).hexdigest()


def media_url(post_id):
    if not public_media_ready():
        raise AppError(409,'SOCIAL_PUBLIC_URL','Instagram memerlukan URL HTTPS publik untuk mengambil video.')
    expires = int(time.time()) + 86400
    return f'{get_settings().social_public_base_url.rstrip("/")}/api/v1/social/media/{post_id}?expires={expires}&signature={media_signature(post_id,expires)}'


def trusted_upload_url(url, platform):
    p = urlparse(url)
    host = p.hostname or ''
    allowed = host == 'www.googleapis.com' if platform == 'youtube' else host.endswith('.tiktokapis.com')
    if p.scheme != 'https' or not allowed or p.username or p.port not in (None,443):
        raise AppError(502,'UPLOAD_HOST','Alamat upload dari platform tidak valid.')
    return url
