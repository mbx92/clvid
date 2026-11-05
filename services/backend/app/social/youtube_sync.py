"""Read-only history import, paginated independently of the upload worker."""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import httpx
from sqlalchemy import or_, select, update
from app.api.errors import AppError
from app.db import session_scope
from app.domain.models import SocialAccount, YouTubeSyncState, YouTubeVideo, utcnow
from . import oauth
from .security import configured

log = logging.getLogger('clipper.youtube_sync')
BASE = 'https://www.googleapis.com/youtube/v3/'


def read(client, resource, token, **params):
    response = client.get(BASE + resource, headers={'Authorization': 'Bearer ' + token}, params=params)
    if response.status_code == 401:
        raise AppError(409, 'YOUTUBE_AUTH', 'Hubungkan ulang akun YouTube untuk memperbarui izin baca.')
    if response.status_code == 403:
        raise AppError(409, 'YOUTUBE_ACCESS', 'YouTube menolak akses baca. Periksa izin akun atau kuota API, lalu coba lagi.')
    if response.status_code == 400 and params.get('pageToken'):
        raise AppError(409, 'YOUTUBE_CURSOR', 'Halaman YouTube berubah. Sinkronisasi akan diulang dari awal.')
    return oauth.json_response(response)


def store_page(db, account, videos, now):
    for item in videos:
        video_id = item.get('id', '')
        snippet = item.get('snippet', {})
        if not re.fullmatch(r'[\w-]{11}', video_id) or snippet.get('channelId') != account.external_id:
            continue
        row = db.scalar(select(YouTubeVideo).where(YouTubeVideo.account_id == account.id, YouTubeVideo.video_id == video_id))
        public = item.get('status', {}).get('privacyStatus') == 'public' and snippet.get('liveBroadcastContent') != 'upcoming'
        published = datetime.fromisoformat(snippet['publishedAt'].replace('Z', '+00:00'))
        if published.tzinfo is None:
            raise ValueError('YouTube publication timestamp must include timezone')
        public = public and published <= now
        if not row and not public:
            continue
        if not row:
            row = YouTubeVideo(owner_id=account.owner_id, account_id=account.id, video_id=video_id)
            db.add(row)
        row.title = snippet.get('title', 'Video YouTube')[:200]
        row.caption = snippet.get('description', '')[:5000]
        row.published_at = published.astimezone(timezone.utc)
        row.available = public
        row.last_seen_at = now
        thumbnails = snippet.get('thumbnails', {})
        thumbnail = (thumbnails.get('medium') or thumbnails.get('default') or {}).get('url', '')
        parsed = urlparse(thumbnail)
        row.thumbnail_url = thumbnail if parsed.scheme == 'https' and (parsed.hostname or '').endswith('.ytimg.com') else None


def sync_account(db, account, state, client, max_pages=4):
    if not configured('youtube'):
        raise AppError(409, 'YOUTUBE_SETUP', 'Lengkapi konfigurasi koneksi YouTube di Pengaturan.')
    token = oauth.access_token(db, account)
    if not state.cycle_started_at:
        state.cycle_started_at = utcnow()
    if not state.uploads_playlist_id:
        channels = read(client, 'channels', token, part='contentDetails', id=account.external_id).get('items', [])
        channel = next((c for c in channels if c.get('id') == account.external_id), None)
        if not channel:
            raise AppError(409, 'YOUTUBE_CHANNEL', 'Channel YouTube tidak ditemukan. Periksa koneksi akun.')
        state.uploads_playlist_id = channel['contentDetails']['relatedPlaylists']['uploads']
    for _ in range(max_pages):
        params = {'part': 'contentDetails', 'playlistId': state.uploads_playlist_id, 'maxResults': 50}
        if state.cursor:
            params['pageToken'] = state.cursor
        page = read(client, 'playlistItems', token, **params)
        if not isinstance(page.get('items'), list):
            raise ValueError('Invalid YouTube playlist response')
        ids = [i.get('contentDetails', {}).get('videoId') for i in page.get('items', [])]
        ids = [i for i in ids if i and re.fullmatch(r'[\w-]{11}', i)]
        if ids:
            details = read(client, 'videos', token, part='snippet,status', id=','.join(ids)).get('items')
            if not isinstance(details, list):
                raise ValueError('Invalid YouTube videos response')
            store_page(db, account, details, utcnow())
        state.cursor = page.get('nextPageToken') or None
        state.error_message = None
        db.flush()
        if not state.cursor:
            # Only a complete successful pass may hide removed/unavailable videos.
            db.execute(update(YouTubeVideo).where(YouTubeVideo.account_id == account.id,
                YouTubeVideo.last_seen_at < state.cycle_started_at).values(available=False))
            state.last_synced_at = utcnow()
            state.cycle_started_at = None
            state.next_sync_at = utcnow() + timedelta(hours=6)
            return
    state.next_sync_at = utcnow() + timedelta(seconds=15)


def sync_once():
    with session_scope() as db:
        account = db.scalar(select(SocialAccount).outerjoin(YouTubeSyncState, YouTubeSyncState.account_id == SocialAccount.id)
            .where(SocialAccount.platform == 'youtube', SocialAccount.connected.is_(True),
                or_(YouTubeSyncState.account_id.is_(None), YouTubeSyncState.next_sync_at <= utcnow()))
            .order_by(YouTubeSyncState.next_sync_at.asc().nullsfirst(), SocialAccount.id)
            .with_for_update(of=SocialAccount, skip_locked=True).limit(1))
        if not account:
            return False
        state = db.get(YouTubeSyncState, account.id)
        if not state:
            state = YouTubeSyncState(account_id=account.id)
            db.add(state)
        try:
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                sync_account(db, account, state, client)
        except Exception as exc:
            state.error_message = exc.message if isinstance(exc, AppError) else 'Sinkronisasi YouTube gagal. Data sebelumnya tetap tersedia; coba lagi nanti.'
            state.next_sync_at = utcnow() + timedelta(minutes=15)
            if isinstance(exc, AppError) and exc.code == 'YOUTUBE_CURSOR':
                state.cursor = None
                state.cycle_started_at = None
        return True


def main():
    logging.basicConfig(level=logging.WARNING)
    while True:
        try:
            sync_once()
        except Exception:
            log.warning('YouTube synchronization unavailable; retrying later')
        time.sleep(15)


if __name__ == '__main__':
    main()
