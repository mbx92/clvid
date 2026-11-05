import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from app.config import get_settings
from app.domain.models import Asset, Clip, ClipRevision, Export, Job, Project, Publication, SocialAccount, SocialOAuthState, User, utcnow
from app.social import oauth, publisher
from app.social.security import seal, unseal, media_signature


@pytest.fixture
def social(clients,database,ready_project,monkeypatch):
    s=get_settings()
    monkeypatch.setattr(s,'social_encryption_key',Fernet.generate_key().decode())
    monkeypatch.setattr(s,'youtube_client_id','test-client')
    monkeypatch.setattr(s,'youtube_client_secret','test-secret')
    owner=clients[0]
    clip=owner.post(f"/api/v1/projects/{ready_project['project_id']}/clips",json={'start_ms':0,'end_ms':6000}).json()
    response=owner.post(f"/api/v1/clips/{clip['id']}/exports",json={'revision':1,'resolution':720})
    with database() as db:
        job=db.get(Job,response.json()['id']); job.status='succeeded'
        export=db.scalar(select(Export).where(Export.job_id==job.id)); export.status='ready'; export.mp4_asset_id=ready_project['asset_id']
        account=SocialAccount(owner_id=db.get(Project,ready_project['project_id']).owner_id,platform='youtube',external_id='channel',name='Test channel',token_ciphertext=seal({'access_token':'private-token','refresh_token':'private-refresh','expires_at':0}))
        db.add(account); db.commit()
        return {'export_id':export.id,'account_id':account.id,'project_id':ready_project['project_id']}


def post_body(social,**changes):
    return {'export_id':social['export_id'],'account_id':social['account_id'],'platform':'youtube','title':'Video uji','caption':'Deskripsi uji',
            'scheduled_at':(utcnow()+timedelta(days=1)).isoformat(),'timezone':'Asia/Makassar','request_key':'calendar-test-001','options':{'privacy':'private','audience':'general'},**changes}


def test_calendar_ownership_timezone_drafts_and_idempotency(clients,database,social):
    owner,other=clients
    body=post_body(social,scheduled_at='2027-01-02T08:00:00+08:00')
    result=owner.post('/api/v1/social/posts',json=body)
    assert result.status_code==201,result.text
    post=result.json(); assert post['status']=='draft'
    assert 'token' not in result.text and 'remote_state' not in result.text
    repeated=owner.post('/api/v1/social/posts',json=body)
    assert repeated.json()['id']==post['id']
    assert owner.post('/api/v1/social/posts',json={**body,'title':'Different'}).status_code==409
    assert owner.post('/api/v1/social/posts',json={**body,'status':'scheduled','consent':True}).status_code==409
    period={'start':'2027-01-02T00:00:00Z','end':'2027-01-03T00:00:00Z'}
    assert len(owner.get('/api/v1/social/posts',params=period).json()['items'])==1
    assert other.get('/api/v1/social/posts',params=period).json()['items']==[]
    assert other.post('/api/v1/social/posts',json=body).status_code==404
    assert other.post(f"/api/v1/social/posts/{post['id']}/cancel").status_code==404
    assert owner.patch(f"/api/v1/social/posts/{post['id']}",json={**body,'expected_version':1,'title':'Edited'}).status_code==200
    assert owner.patch(f"/api/v1/social/posts/{post['id']}",json={**body,'expected_version':1}).status_code==409
    assert owner.post('/api/v1/social/posts',json={**body,'scheduled_at':'2027-01-02T08:00:00'}).status_code==422
    token=owner.headers.pop('X-CSRF-Token')
    assert owner.post('/api/v1/social/posts',json=body).status_code==403
    owner.headers['X-CSRF-Token']=token


def test_schedule_requires_consent_and_configuration_and_freezes_export(clients,database,social,monkeypatch):
    owner=clients[0]; body=post_body(social,status='scheduled')
    assert owner.post('/api/v1/social/posts',json=body).status_code==422
    body['consent']=True
    result=owner.post('/api/v1/social/posts',json=body)
    assert result.status_code==201,result.text
    post=result.json()
    with database() as db:
        row=db.get(Publication,post['id']); assert row.export_id==social['export_id'] and row.consent_at
        row.scheduled_at=utcnow()-timedelta(minutes=1); db.commit()
    claimed=publisher.claim(); assert claimed[0]==post['id']
    assert publisher.claim() is None
    assert owner.post(f"/api/v1/social/posts/{post['id']}/cancel").status_code==409
    assert owner.delete(f"/api/v1/projects/{social['project_id']}").status_code==409
    with database() as db:
        db.get(Publication,post['id']).lease_expires_at=utcnow()-timedelta(seconds=1); db.commit()
    assert publisher.claim() is None
    with database() as db: assert db.get(Publication,post['id']).status=='uncertain'
    assert owner.post(f"/api/v1/social/posts/{post['id']}/draft").status_code==409
    monkeypatch.setattr(get_settings(),'youtube_client_id','')
    assert owner.post('/api/v1/social/posts',json={**body,'request_key':'other-request'}).status_code==409


def test_oauth_state_bound_to_session_and_tokens_never_returned(clients,database,social,monkeypatch):
    owner,other=clients
    result=owner.post('/api/v1/social/oauth/youtube/start')
    assert result.status_code==200
    state=parse_qs(urlparse(result.json()['url']).query)['state'][0]
    monkeypatch.setattr(oauth,'exchange',lambda platform,code:[{'external_id':'new-channel','name':'Authorized','token':{'access_token':'sensitive-access','refresh_token':'sensitive-refresh'}}])
    url='/api/v1/social/oauth/youtube/callback'
    assert other.get(url,params={'state':state,'code':'code'}).status_code==403
    result=owner.get(url,params={'state':state,'code':'code'},follow_redirects=False)
    assert result.status_code==303 and result.headers['location']=='/settings?section=accounts&connection=connected'
    assert owner.get(url,params={'state':state,'code':'code'},follow_redirects=False).status_code==403
    assert 'sensitive' not in owner.get('/api/v1/social/accounts').text
    with database() as db:
        row=db.scalar(select(SocialAccount).where(SocialAccount.external_id=='new-channel'))
        assert 'sensitive' not in row.token_ciphertext
        assert unseal(row.token_ciphertext)['access_token']=='sensitive-access'


def youtube_callback(owner,**params):
    result=owner.post('/api/v1/social/oauth/youtube/start')
    assert result.status_code==200
    state=parse_qs(urlparse(result.json()['url']).query)['state'][0]
    return owner.get('/api/v1/social/oauth/youtube/callback',params={'state':state,**params},follow_redirects=False)


def test_youtube_oauth_requests_account_choice_with_offline_upload_access(clients,social):
    result=clients[0].post('/api/v1/social/oauth/youtube/start')
    assert result.status_code==200
    url=urlparse(result.json()['url']); query=parse_qs(url.query)
    assert url.scheme=='https' and url.netloc=='accounts.google.com'
    assert query['prompt']==['consent select_account']
    assert query['access_type']==['offline'] and query['response_type']==['code']
    assert set(query['scope'][0].split())=={'https://www.googleapis.com/auth/youtube.upload','https://www.googleapis.com/auth/youtube.readonly'}
    assert query['redirect_uri']==['http://testserver/api/v1/social/oauth/youtube/callback']
    assert query['state'][0]


def test_youtube_second_channel_preserves_first_token_and_scheduled_destination(clients,database,social,monkeypatch):
    owner,other=clients
    post=owner.post('/api/v1/social/posts',json=post_body(social,status='scheduled',consent=True)).json()
    with database() as db:
        original_ciphertext=db.get(SocialAccount,social['account_id']).token_ciphertext
    second_token={'access_token':'second-channel-access','refresh_token':'second-channel-refresh'}
    monkeypatch.setattr(oauth,'exchange',lambda platform,code:[{'external_id':'second-channel','name':'Second channel','token':second_token}])
    result=youtube_callback(owner,code='second-code')
    assert result.status_code==303 and result.headers['location'].endswith('connection=connected')
    with database() as db:
        first=db.get(SocialAccount,social['account_id'])
        second=db.scalar(select(SocialAccount).where(SocialAccount.external_id=='second-channel'))
        assert first.connected and first.token_ciphertext==original_ciphertext
        assert second.id!=first.id and second.connected
        assert unseal(second.token_ciphertext)==second_token
        scheduled=db.get(Publication,post['id'])
        assert scheduled.account_id==first.id and scheduled.status=='scheduled'
    accounts=owner.get('/api/v1/social/accounts')
    assert {row['name'] for row in accounts.json()['items']}=={'Test channel','Second channel'}
    assert 'second-channel-access' not in accounts.text and 'second-channel-refresh' not in accounts.text
    assert other.get('/api/v1/social/accounts').json()['items']==[]


@pytest.mark.parametrize('previously_connected',[True,False])
def test_youtube_reconnect_updates_only_selected_channel_without_duplicates(clients,database,social,monkeypatch,previously_connected):
    owner=clients[0]
    with database() as db:
        first=db.get(SocialAccount,social['account_id'])
        original_ciphertext=first.token_ciphertext
        second=SocialAccount(owner_id=first.owner_id,platform='youtube',external_id='second-channel',name='Previous name',
            token_ciphertext=seal({'access_token':'previous-second-access'}),connected=previously_connected)
        db.add(second); db.commit(); second_id=second.id
    post=owner.post('/api/v1/social/posts',json=post_body(social,account_id=second_id,status='scheduled' if previously_connected else 'draft',consent=True)).json()
    new_token={'access_token':'renewed-second-access','refresh_token':'renewed-second-refresh'}
    monkeypatch.setattr(oauth,'exchange',lambda platform,code:[{'external_id':'second-channel','name':'Renewed channel','token':new_token}])
    result=youtube_callback(owner,code='renew-code')
    expected='reconnected' if previously_connected else 'connected'
    assert result.status_code==303 and result.headers['location'].endswith('connection='+expected)
    with database() as db:
        assert len(list(db.scalars(select(SocialAccount))))==2
        first=db.get(SocialAccount,social['account_id']); second=db.get(SocialAccount,second_id)
        assert first.token_ciphertext==original_ciphertext and first.name=='Test channel' and first.connected
        assert second.name=='Renewed channel' and second.connected and unseal(second.token_ciphertext)==new_token
        saved_post=db.get(Publication,post['id'])
        assert saved_post.account_id==second_id
        assert saved_post.status==('scheduled' if previously_connected else 'draft')


@pytest.mark.parametrize('outcome',['cancelled','failed'])
def test_unsuccessful_youtube_connection_preserves_existing_channel(clients,database,social,monkeypatch,outcome):
    from app.api.errors import AppError
    owner=clients[0]
    post=owner.post('/api/v1/social/posts',json=post_body(social,status='scheduled',consent=True)).json()
    with database() as db:
        original_ciphertext=db.get(SocialAccount,social['account_id']).token_ciphertext
    def exchange(platform,code):
        assert outcome=='failed', 'Cancelled authorization must not exchange a code'
        raise AppError(502,'SOCIAL_PROVIDER','Provider rejected authorization')
    monkeypatch.setattr(oauth,'exchange',exchange)
    result=youtube_callback(owner,**({'error':'access_denied'} if outcome=='cancelled' else {'code':'rejected-code'}))
    assert result.status_code==303 and result.headers['location'].endswith('connection='+outcome)
    with database() as db:
        rows=list(db.scalars(select(SocialAccount)))
        assert len(rows)==1 and rows[0].id==social['account_id']
        assert rows[0].connected and rows[0].token_ciphertext==original_ciphertext
        scheduled=db.get(Publication,post['id'])
        assert scheduled.account_id==social['account_id'] and scheduled.status=='scheduled'


def test_instagram_signed_media_scoped_to_active_post(clients,database,social):
    import time
    from app.storage.local import LocalStorage
    result=clients[0].post('/api/v1/social/posts',json=post_body(social,platform='instagram',account_id=None)).json()
    post_id=result['id']; expires=int(time.time())+60
    with database() as db:
        db.get(Publication,post_id).status='processing'; db.commit()
    path=LocalStorage().path(f'social/{post_id}/upload.mp4'); path.parent.mkdir(parents=True); path.write_bytes(b'valid fixture bytes')
    url=f'/api/v1/social/media/{post_id}'
    params={'expires':expires,'signature':media_signature(post_id,expires)}
    assert clients[1].get(url,params=params).content==b'valid fixture bytes'
    assert clients[1].get(url,params={**params,'signature':'wrong'}).status_code==403
    assert clients[1].get(url,params={'expires':0,'signature':media_signature(post_id,0)}).status_code==403
    with database() as db: db.get(Publication,post_id).status='published'; db.commit()
    assert clients[1].get(url,params=params).status_code==404


def test_disconnect_cancels_pending_and_project_deletion_removes_calendar(clients,database,social):
    owner=clients[0]
    post=owner.post('/api/v1/social/posts',json=post_body(social,status='scheduled',consent=True)).json()
    assert owner.delete(f"/api/v1/social/accounts/{social['account_id']}").status_code==204
    with database() as db:
        assert db.get(Publication,post['id']).status=='cancelled'
        assert db.get(SocialAccount,social['account_id']).token_ciphertext==''
    job=owner.delete(f"/api/v1/projects/{social['project_id']}").json()
    from app.jobs.tasks import run_job
    run_job(job['id'])
    with database() as db: assert db.get(Publication,post['id']) is None


def due_post(clients,database,social,platform='youtube'):
    body=post_body(social,platform=platform,account_id=social['account_id'] if platform=='youtube' else None)
    post=clients[0].post('/api/v1/social/posts',json=body).json()
    with database() as db:
        row=db.get(Publication,post['id']); row.status='scheduled'; row.scheduled_at=utcnow()-timedelta(seconds=1); row.consent_at=utcnow(); row.account_id=social['account_id']
        db.get(SocialAccount,social['account_id']).platform=platform
        db.commit()
    return post['id']


def test_youtube_resumable_upload_and_processing_confirmation(clients,database,social,monkeypatch):
    import httpx
    calls=[]
    class Client:
        def __init__(self,**kw): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def post(self,url,**kw):
            calls.append((url,kw))
            assert kw['json']['status']['privacyStatus']=='private'
            assert kw['json']['status']['selfDeclaredMadeForKids'] is False
            return httpx.Response(200,headers={'Location':'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test'},content=b'')
        def put(self,url,**kw):
            assert kw['headers']['Content-Range']=='bytes 0-15/16'
            assert len(kw['content'])==16
            return httpx.Response(200,json={'id':'yt-video'})
        def get(self,url,**kw):
            return httpx.Response(200,json={'items':[{'status':{'uploadStatus':'processed','privacyStatus':'private'}}]})
    monkeypatch.setattr(publisher.httpx,'Client',Client)
    post_id=due_post(clients,database,social)
    publisher.run_one(*publisher.claim())
    with database() as db: assert db.get(Publication,post_id).status=='processing'
    publisher.run_one(*publisher.claim())
    with database() as db:
        row=db.get(Publication,post_id)
        assert row.status=='published' and row.remote_url=='https://www.youtube.com/watch?v=yt-video'
    assert len(calls)==1


def test_ambiguous_upload_never_reinitializes_and_check_is_read_only(clients,database,social,monkeypatch):
    import httpx
    starts=[]
    class Client:
        def __init__(self,**kw): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def post(self,url,**kw):
            starts.append(url)
            return httpx.Response(200,headers={'Location':'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test'})
        def put(self,url,**kw):
            if kw['content']: raise httpx.ReadTimeout('private URL must not leak')
            assert kw['headers']['Content-Range']=='bytes */16'
            return httpx.Response(200,json={'id':'recovered'})
    monkeypatch.setattr(publisher.httpx,'Client',Client)
    post_id=due_post(clients,database,social)
    publisher.run_one(*publisher.claim())
    with database() as db:
        row=db.get(Publication,post_id); assert row.status=='uncertain' and 'private URL' not in row.error_message
    assert publisher.claim() is None
    assert clients[0].post(f'/api/v1/social/posts/{post_id}/check').status_code==200
    publisher.run_one(*publisher.claim())
    with database() as db: assert db.get(Publication,post_id).remote_id=='recovered'
    assert len(starts)==1


def test_instagram_waits_for_container_before_publish(clients,database,social,monkeypatch):
    import httpx
    from app.storage.local import LocalStorage
    s=get_settings()
    for key,value in {'meta_client_id':'client','meta_client_secret':'secret','meta_graph_version':'v26.0','social_public_base_url':'https://clipper.example.test'}.items(): monkeypatch.setattr(s,key,value)
    post_id=due_post(clients,database,social,'instagram')
    path=LocalStorage().path(f'social/{post_id}/upload.mp4'); path.parent.mkdir(parents=True); path.write_bytes(b'profiled')
    published=[]
    class Client:
        def __init__(self,**kw): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def post(self,url,**kw):
            if url.endswith('/media'):
                assert kw['data']['media_type']=='REELS' and 'signature=' in kw['data']['video_url']
                return httpx.Response(200,json={'id':'container'})
            published.append(url); assert kw['data']=={'creation_id':'container'}
            return httpx.Response(200,json={'id':'ig-media'})
        def get(self,url,**kw):
            return httpx.Response(200,json={'status_code':'FINISHED'} if 'container' in url else {'permalink':'https://www.instagram.com/reel/test/'})
    monkeypatch.setattr(publisher.httpx,'Client',Client)
    publisher.run_one(*publisher.claim()); assert not published
    publisher.run_one(*publisher.claim()); assert len(published)==1
    with database() as db: assert db.get(Publication,post_id).status=='published'


def test_tiktok_direct_post_upload_then_status(clients,database,social,monkeypatch):
    import httpx
    s=get_settings()
    for key,value in {'tiktok_client_key':'client','tiktok_client_secret':'secret','tiktok_direct_post_enabled':True}.items(): monkeypatch.setattr(s,key,value)
    post_id=due_post(clients,database,social,'tiktok')
    with database() as db:
        row=db.get(Publication,post_id); row.options_json={**row.options_json,'privacy':'SELF_ONLY','music_consent':True}; db.commit()
    monkeypatch.setattr(publisher,'creator_info',lambda token:{'privacy_level_options':['SELF_ONLY'],'max_video_post_duration_sec':60})
    class Client:
        def __init__(self,**kw): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def post(self,url,**kw):
            if url.endswith('/init/'):
                assert kw['json']['source_info']=={'source':'FILE_UPLOAD','video_size':16,'chunk_size':16,'total_chunk_count':1}
                assert kw['json']['post_info']['privacy_level']=='SELF_ONLY'
                assert kw['json']['post_info']['disable_comment'] is True
                return httpx.Response(200,json={'data':{'upload_url':'https://open-upload.tiktokapis.com/upload/test','publish_id':'tt-publish'},'error':{'code':'ok'}})
            assert kw['json']=={'publish_id':'tt-publish'}
            return httpx.Response(200,json={'data':{'status':'PUBLISH_COMPLETE'},'error':{'code':'ok'}})
        def put(self,url,**kw):
            assert kw['headers']['Content-Range']=='bytes 0-15/16'
            assert 'Authorization' not in kw['headers']
            return httpx.Response(201)
    monkeypatch.setattr(publisher.httpx,'Client',Client)
    publisher.run_one(*publisher.claim()); publisher.run_one(*publisher.claim())
    with database() as db: assert db.get(Publication,post_id).status=='published'


def test_instagram_local_preparation_failure_does_not_claim_remote_upload(clients,database,social,monkeypatch):
    from app.media import process
    s=get_settings()
    for key,value in {'meta_client_id':'client','meta_client_secret':'secret','meta_graph_version':'v26.0','social_public_base_url':'https://clipper.example.test'}.items(): monkeypatch.setattr(s,key,value)
    post_id=due_post(clients,database,social,'instagram')
    def fail_preparation(*args,**kwargs):
        kwargs['progress'](None)
        raise RuntimeError('local encoding failed')
    monkeypatch.setattr(process,'ffmpeg',fail_preparation)
    publisher.run_one(*publisher.claim())
    with database() as db:
        row=db.get(Publication,post_id)
        assert row.status=='failed'
        assert not unseal(row.remote_state_ciphertext)
