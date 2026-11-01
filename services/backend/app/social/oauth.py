import time
from urllib.parse import urlencode
import httpx
from sqlalchemy import select
from app.api.errors import AppError
from app.config import get_settings
from app.domain.models import SocialAccount
from .security import callback_url, seal, unseal


def json_response(response):
    # Never surface provider response bodies, codes, tokens or signed URLs.
    if not response.is_success:
        raise AppError(502,'SOCIAL_PROVIDER',f'Platform menolak permintaan (HTTP {response.status_code}). Periksa izin akun dan konfigurasi aplikasi.')
    data = response.json()
    error = data.get('error')
    if error and (not isinstance(error,dict) or error.get('code') not in (None,'ok')):
        raise AppError(502,'SOCIAL_PROVIDER','Platform menolak permintaan. Periksa izin, kuota, dan status akun.')
    return data


def graph():
    import re
    version = get_settings().meta_graph_version
    if not re.fullmatch(r'v\d+\.\d+',version):
        raise AppError(503,'META_VERSION','Isi versi Graph API yang didukung aplikasi Meta.')
    return 'https://graph.facebook.com/' + version


def authorization_url(platform, state):
    s = get_settings()
    params = {'response_type':'code','redirect_uri':callback_url(platform),'state':state}
    if platform == 'youtube':
        params.update(client_id=s.youtube_client_id,scope='https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly',access_type='offline',prompt='consent')
        base='https://accounts.google.com/o/oauth2/v2/auth'
    elif platform == 'instagram':
        params.update(client_id=s.meta_client_id,scope='pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish')
        base=f'https://www.facebook.com/{s.meta_graph_version}/dialog/oauth'
    else:
        params.update(client_key=s.tiktok_client_key,scope='user.info.basic,video.publish')
        base='https://www.tiktok.com/v2/auth/authorize/'
    return base+'?'+urlencode(params)


def exchange(platform, code):
    s = get_settings()
    with httpx.Client(timeout=30,follow_redirects=False) as client:
        if platform == 'youtube':
            token=json_response(client.post('https://oauth2.googleapis.com/token',data={'client_id':s.youtube_client_id,'client_secret':s.youtube_client_secret,'grant_type':'authorization_code','code':code,'redirect_uri':callback_url(platform)}))
            channels=json_response(client.get('https://www.googleapis.com/youtube/v3/channels',params={'part':'snippet','mine':'true'},headers={'Authorization':'Bearer '+token['access_token']}))
            token['expires_at']=time.time()+token.get('expires_in',3600)
            if not token.get('refresh_token'): raise AppError(409,'SOCIAL_OFFLINE','Otorisasi ulang akun dengan akses offline agar jadwal dapat berjalan.')
            result=[{'external_id':row['id'],'name':row['snippet']['title'],'token':token} for row in channels.get('items',[])]
        elif platform == 'instagram':
            token=json_response(client.get(graph()+'/oauth/access_token',params={'client_id':s.meta_client_id,'client_secret':s.meta_client_secret,'code':code,'redirect_uri':callback_url(platform)}))
            token=json_response(client.get(graph()+'/oauth/access_token',params={'client_id':s.meta_client_id,'client_secret':s.meta_client_secret,'grant_type':'fb_exchange_token','fb_exchange_token':token['access_token']}))
            pages=json_response(client.get(graph()+'/me/accounts',params={'fields':'id,name,access_token,instagram_business_account{id,username}','limit':100},headers={'Authorization':'Bearer '+token['access_token']}))
            result=[{'external_id':p['instagram_business_account']['id'],'name':p['instagram_business_account'].get('username',p['name']),'token':{'access_token':p['access_token'],'expires_at':0}} for p in pages.get('data',[]) if p.get('instagram_business_account') and p.get('access_token')]
        else:
            token=json_response(client.post('https://open.tiktokapis.com/v2/oauth/token/',data={'client_key':s.tiktok_client_key,'client_secret':s.tiktok_client_secret,'grant_type':'authorization_code','code':code,'redirect_uri':callback_url(platform)}))
            user=json_response(client.get('https://open.tiktokapis.com/v2/user/info/',params={'fields':'open_id,display_name'},headers={'Authorization':'Bearer '+token['access_token']}))['data']['user']
            token['expires_at']=time.time()+token.get('expires_in',86400)
            result=[{'external_id':user['open_id'],'name':user['display_name'],'token':token}]
    if not result: raise AppError(409,'SOCIAL_ACCOUNT','Tidak ada channel atau akun profesional yang dapat dihubungkan.')
    return result


def access_token(db, account):
    account=db.scalar(select(SocialAccount).where(SocialAccount.id==account.id).with_for_update())
    if not account or not account.connected: raise AppError(409,'SOCIAL_DISCONNECTED','Hubungkan kembali akun tujuan.')
    token=unseal(account.token_ciphertext)
    if not token.get('expires_at') or token['expires_at'] > time.time()+120: return token['access_token']
    s=get_settings()
    data={'grant_type':'refresh_token','refresh_token':token.get('refresh_token','')}
    if account.platform=='youtube':
        url='https://oauth2.googleapis.com/token'; data.update(client_id=s.youtube_client_id,client_secret=s.youtube_client_secret)
    elif account.platform=='tiktok':
        url='https://open.tiktokapis.com/v2/oauth/token/'; data.update(client_key=s.tiktok_client_key,client_secret=s.tiktok_client_secret)
    else: raise AppError(409,'SOCIAL_EXPIRED','Hubungkan ulang akun Instagram.')
    with httpx.Client(timeout=30) as client: fresh=json_response(client.post(url,data=data))
    token.update(fresh); token['expires_at']=time.time()+fresh.get('expires_in',3600)
    account.token_ciphertext=seal(token)
    db.flush()
    return token['access_token']


def creator_info(token):
    with httpx.Client(timeout=30) as client:
        return json_response(client.post('https://open.tiktokapis.com/v2/post/publish/creator_info/query/',headers={'Authorization':'Bearer '+token},json={}))['data']
