from datetime import datetime, timedelta, timezone
import httpx
import pytest
from sqlalchemy import select
from app.config import get_settings
from app.domain.models import Publication, SocialAccount, User, YouTubeSyncState, YouTubeVideo, utcnow
from app.social import youtube_sync

PERIOD = {'start': '2026-01-01T00:00:00Z', 'end': '2026-02-01T00:00:00Z'}


def video(id='AAAAAAAAAAA', **changes):
    value={'id':id,'snippet':{'channelId':'channel','title':'Video sudah tayang','description':'Deskripsi YouTube',
        'publishedAt':'2026-01-03T16:30:00Z','liveBroadcastContent':'none',
        'thumbnails':{'medium':{'url':'https://i.ytimg.com/vi/'+id+'/mqdefault.jpg'}}}, 'status':{'privacyStatus':'public'}}
    for section,fields in changes.items():
        value[section].update(fields)
    return value


@pytest.fixture
def yt(clients,database,monkeypatch):
    monkeypatch.setattr(get_settings(),'youtube_client_id','test-client')
    monkeypatch.setattr(get_settings(),'youtube_client_secret','test-secret')
    monkeypatch.setattr(youtube_sync.oauth,'access_token',lambda db,account:'test-token')
    with database() as db:
        user=db.scalar(select(User).where(User.email=='a@example.test'))
        account=SocialAccount(owner_id=user.id,platform='youtube',external_id='channel',name='Channel uji',token_ciphertext='')
        db.add(account); db.commit(); account_id=account.id
    fake={'pages':{'':{'items':[{'contentDetails':{'videoId':'AAAAAAAAAAA'}}]}},'videos':{'AAAAAAAAAAA':video()},'requests':[],'fail':False}
    def handler(request):
        assert request.method=='GET', 'History sync must never upload or edit videos'
        assert request.headers['Authorization']=='Bearer test-token'
        name=request.url.path.rsplit('/',1)[-1]; fake['requests'].append((name,dict(request.url.params)))
        if fake['fail']:
            return httpx.Response(403,json={'error':{'message':'private-provider-detail'}})
        if name=='channels':
            data={'items':[{'id':'channel','contentDetails':{'relatedPlaylists':{'uploads':'uploads-list'}}}]}
        elif name=='playlistItems':
            data=fake['pages'][request.url.params.get('pageToken','')]
        else:
            assert name=='videos'
            data={'items':[fake['videos'][id] for id in request.url.params['id'].split(',') if id in fake['videos']]}
        return httpx.Response(200,json=data)
    original_client=httpx.Client
    monkeypatch.setattr(youtube_sync.httpx,'Client',lambda **kwargs:original_client(transport=httpx.MockTransport(handler)))
    return account_id,fake


def test_sync_fills_calendar_with_actual_publication_time_and_deduplicates(clients,database,ready_project,yt):
    account_id,fake=yt
    assert youtube_sync.sync_once()
    owner,other=clients
    posts=owner.get('/api/v1/social/posts',params=PERIOD).json()['items']
    assert len(posts)==1
    post=posts[0]
    assert datetime.fromisoformat(post['scheduled_at'])==datetime(2026,1,3,16,30,tzinfo=timezone.utc)
    assert post['readonly'] and post['source']=='youtube' and post['status']=='published'
    assert post['thumbnail_url'].startswith('https://i.ytimg.com/')
    assert other.get('/api/v1/social/posts',params=PERIOD).json()['items']==[]
    assert owner.post('/api/v1/social/posts/'+post['id']+'/cancel').status_code==404
    with database() as db:
        account=db.get(SocialAccount,account_id)
        db.add(Publication(owner_id=account.owner_id,account_id=account_id,project_id=ready_project['project_id'],platform='youtube',
            title='Upload lokal',status='published',scheduled_at=datetime(2026,1,2,tzinfo=timezone.utc),
            remote_id='AAAAAAAAAAA',request_key='local-post',options_json={}))
        db.commit()
    assert owner.post('/api/v1/social/youtube/sync').status_code==202
    fake['videos']['AAAAAAAAAAA']['snippet']['title']='Judul diperbarui'
    assert youtube_sync.sync_once()
    posts=owner.get('/api/v1/social/posts',params=PERIOD).json()['items']
    assert len(posts)==1 and posts[0]['title']=='Judul diperbarui'
    with database() as db:
        assert len(list(db.scalars(select(YouTubeVideo))))==1
    assert not youtube_sync.sync_once() # Scheduled refresh is not due yet.


def test_pagination_resumes_without_hiding_older_rows_until_complete(clients,database,yt):
    account_id,fake=yt
    fake['pages']['']['nextPageToken']='second'
    fake['pages']['second']={'items':[{'contentDetails':{'videoId':'BBBBBBBBBBB'}}]}
    fake['videos']['BBBBBBBBBBB']=video('BBBBBBBBBBB')
    with database() as db:
        account=db.get(SocialAccount,account_id)
        state=YouTubeSyncState(account_id=account_id); db.add(state)
        with youtube_sync.httpx.Client() as client:
            youtube_sync.sync_account(db,account,state,client,max_pages=1)
        db.commit()
        assert state.cursor=='second' and state.last_synced_at is None
    clients[0].post('/api/v1/social/youtube/sync')
    youtube_sync.sync_once()
    with database() as db:
        state=db.get(YouTubeSyncState,account_id)
        assert state.cursor is None and state.last_synced_at
        assert len(list(db.scalars(select(YouTubeVideo).where(YouTubeVideo.available.is_(True)))))==2
    assert any(params.get('pageToken')=='second' for name,params in fake['requests'])


def test_private_upcoming_and_foreign_channel_videos_are_not_history(clients,database,yt):
    account_id,fake=yt
    fake['videos']={'AAAAAAAAAAA':video(status={'privacyStatus':'private'}),
        'BBBBBBBBBBB':video('BBBBBBBBBBB',snippet={'liveBroadcastContent':'upcoming'}),
        'CCCCCCCCCCC':video('CCCCCCCCCCC',snippet={'channelId':'other-channel'})}
    fake['pages']['']['items']=[{'contentDetails':{'videoId':id}} for id in fake['videos']]
    youtube_sync.sync_once()
    assert clients[0].get('/api/v1/social/posts',params=PERIOD).json()['items']==[]


def test_sync_failure_preserves_history_and_hides_provider_secrets(clients,database,yt):
    account_id,fake=yt
    youtube_sync.sync_once()
    fake['fail']=True
    clients[0].post('/api/v1/social/youtube/sync')
    youtube_sync.sync_once()
    status=clients[0].get('/api/v1/social/youtube/sync')
    assert status.json()['items'][0]['error_message']
    assert 'private-provider-detail' not in status.text and 'test-token' not in status.text
    assert len(clients[0].get('/api/v1/social/posts',params=PERIOD).json()['items'])==1
    assert clients[1].get('/api/v1/social/youtube/sync').json()['items']==[]
    assert clients[1].post('/api/v1/social/youtube/sync').status_code==409
    token=clients[0].headers.pop('X-CSRF-Token')
    assert clients[0].post('/api/v1/social/youtube/sync').status_code==403
    clients[0].headers['X-CSRF-Token']=token


@pytest.mark.parametrize('mode',['private','deleted'])
def test_successful_refresh_removes_unavailable_history(clients,database,yt,mode):
    account_id,fake=yt
    youtube_sync.sync_once()
    if mode=='private': fake['videos']['AAAAAAAAAAA']['status']['privacyStatus']='private'
    else: fake['pages']['']['items']=[]
    clients[0].post('/api/v1/social/youtube/sync'); youtube_sync.sync_once()
    assert clients[0].get('/api/v1/social/posts',params=PERIOD).json()['items']==[]


def test_disconnect_removes_imported_history(clients,database,yt):
    account_id,fake=yt
    youtube_sync.sync_once()
    assert clients[0].delete('/api/v1/social/accounts/'+account_id).status_code==204
    with database() as db:
        assert db.get(YouTubeSyncState,account_id) is None
        assert list(db.scalars(select(YouTubeVideo)))==[]
    assert not youtube_sync.sync_once()


def test_incomplete_scan_keeps_old_history_until_last_page_succeeds(clients,database,yt):
    account_id,fake=yt
    youtube_sync.sync_once()
    fake['pages']={'':{'items':[{'contentDetails':{'videoId':'BBBBBBBBBBB'}}],'nextPageToken':'second'},'second':{'items':[]}}
    fake['videos']['BBBBBBBBBBB']=video('BBBBBBBBBBB')
    with database() as db:
        account=db.get(SocialAccount,account_id); state=db.get(YouTubeSyncState,account_id)
        with youtube_sync.httpx.Client() as client:
            youtube_sync.sync_account(db,account,state,client,max_pages=1)
        db.commit()
        assert state.cursor=='second'
        assert len(list(db.scalars(select(YouTubeVideo).where(YouTubeVideo.available.is_(True)))))==2
    fake['fail']=True
    clients[0].post('/api/v1/social/youtube/sync'); youtube_sync.sync_once()
    assert len(clients[0].get('/api/v1/social/posts',params=PERIOD).json()['items'])==2
    fake['fail']=False
    clients[0].post('/api/v1/social/youtube/sync'); youtube_sync.sync_once()
    posts=clients[0].get('/api/v1/social/posts',params=PERIOD).json()['items']
    assert len(posts)==1 and posts[0]['remote_id']=='BBBBBBBBBBB'
