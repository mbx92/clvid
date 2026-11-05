import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import Field, model_validator
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.api.auth import current_user
from app.api.errors import AppError
from app.api.schemas import StrictModel
from app.config import get_settings
from app.db import get_db
from app.domain.models import Asset, Clip, ClipRevision, Export, Project, Publication, SocialAccount, SocialOAuthState, User, utcnow
from app.storage.local import LocalStorage
from . import oauth
from .security import PLATFORMS, callback_url, configured, media_signature, public_media_ready, seal, unseal

router=APIRouter(prefix='/social',tags=['calendar'])
ACTIVE=('uploading','processing')


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Options(StrictModel):
    privacy: str = Field(default='',max_length=40)
    audience: Literal['general','kids'] | None = None
    notify_subscribers: bool = False
    share_to_feed: bool = False
    allow_comment: bool = False
    allow_duet: bool = False
    allow_stitch: bool = False
    commercial_own: bool = False
    commercial_paid: bool = False
    aigc: bool = False
    music_consent: bool = False


class PostInput(StrictModel):
    export_id: str
    platform: Literal['youtube','instagram','tiktok']
    account_id: str | None = None
    title: str = Field(min_length=1,max_length=100)
    caption: str = Field(default='',max_length=5000)
    scheduled_at: datetime
    timezone: str = 'Asia/Makassar'
    status: Literal['draft','scheduled'] = 'draft'
    options: Options = Field(default_factory=Options)
    consent: bool = False
    request_key: str = Field(min_length=8,max_length=64)
    expected_version: int | None = None

    @model_validator(mode='after')
    def valid_time(self):
        if not self.scheduled_at.tzinfo: raise ValueError('Timezone required')
        try: ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError,ValueError): raise ValueError('Timezone invalid')
        return self


def account_data(account):
    return {k:getattr(account,k) for k in ('id','platform','name','connected')}


def post_data(db,post):
    result={k:getattr(post,k) for k in ('id','project_id','export_id','account_id','platform','title','caption','status','scheduled_at','timezone','version','remote_id','remote_url','error_message','created_at')}
    result['scheduled_at']=aware(post.scheduled_at)
    result['options']=post.options_json
    account=db.get(SocialAccount,post.account_id) if post.account_id else None
    result['account_name']=account.name if account else None
    export=db.get(Export,post.export_id) if post.export_id else None
    result['preview_url']=f'/api/v1/assets/{export.mp4_asset_id}/content' if export and export.mp4_asset_id else None
    return result


def own_account(db,user,account_id):
    row=db.get(SocialAccount,account_id)
    if not row or row.owner_id!=user.id: raise AppError(404,'SOCIAL_ACCOUNT','Akun tidak ditemukan.')
    return row


def own_post(db,user,post_id):
    row=db.scalar(select(Publication).where(Publication.id==post_id,Publication.owner_id==user.id).with_for_update())
    if not row: raise AppError(404,'POST_NOT_FOUND','Jadwal tidak ditemukan.')
    return row


@router.get('/accounts')
def accounts(user:User=Depends(current_user),db:Session=Depends(get_db)):
    s=get_settings()
    return {'items':[account_data(a) for a in db.scalars(select(SocialAccount).where(SocialAccount.owner_id==user.id,SocialAccount.connected.is_(True)))],
        'platforms':[{'id':p,'configured':configured(p),'callback_url':callback_url(p),
            'publishing_ready':configured(p) and (p!='instagram' or public_media_ready()) and (p!='tiktok' or s.tiktok_direct_post_enabled)} for p in PLATFORMS]}


@router.post('/oauth/{platform}/start')
def oauth_start(platform:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if platform not in PLATFORMS or not configured(platform): raise AppError(409,'SOCIAL_SETUP','Konfigurasi aplikasi developer belum lengkap. Lihat panduan koneksi di kalender.')
    state=secrets.token_urlsafe(32)
    db.execute(delete(SocialOAuthState).where(SocialOAuthState.expires_at < utcnow()))
    db.add(SocialOAuthState(id=hashlib.sha256(state.encode()).hexdigest(),owner_id=user.id,session_id=request.state.session.id,platform=platform,expires_at=utcnow()+timedelta(minutes=10)))
    db.commit()
    return {'url':oauth.authorization_url(platform,state)}


@router.get('/oauth/{platform}/callback')
def oauth_callback(platform:str,request:Request,state:str='',code:str='',error:str='',user:User=Depends(current_user),db:Session=Depends(get_db)):
    saved=db.scalar(select(SocialOAuthState).where(SocialOAuthState.id==hashlib.sha256(state.encode()).hexdigest()).with_for_update())
    if not saved or saved.owner_id!=user.id or saved.session_id!=request.state.session.id or saved.platform!=platform or aware(saved.expires_at)<utcnow():
        raise AppError(403,'OAUTH_STATE','Otorisasi kedaluwarsa atau tidak cocok. Mulai Hubungkan akun kembali.')
    db.delete(saved); db.commit()  # One use, including provider rejection.
    if error or not code: return RedirectResponse('/settings?section=accounts&connection=cancelled',status_code=303)
    try:
        connected=oauth.exchange(platform,code)
        reconnected=True
        for item in connected:
            row=db.scalar(select(SocialAccount).where(SocialAccount.owner_id==user.id,SocialAccount.platform==platform,SocialAccount.external_id==item['external_id']))
            if not row or not row.connected: reconnected=False
            if not row:
                row=SocialAccount(owner_id=user.id,platform=platform,external_id=item['external_id']); db.add(row)
            row.name=item['name']; row.token_ciphertext=seal(item['token']); row.connected=True
        db.commit()
    except Exception:
        db.rollback()
        return RedirectResponse('/settings?section=accounts&connection=failed',status_code=303)
    connection='reconnected' if reconnected else 'connected'
    return RedirectResponse(f'/settings?section=accounts&connection={connection}',status_code=303)


@router.delete('/accounts/{account_id}',status_code=204)
def disconnect(account_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    account=own_account(db,user,account_id)
    if db.scalar(select(Publication.id).where(Publication.account_id==account.id,Publication.status.in_(ACTIVE))):
        raise AppError(409,'POST_BUSY','Tunggu publikasi yang sedang dikirim selesai sebelum melepas koneksi.')
    account.connected=False; account.token_ciphertext=''
    for post in db.scalars(select(Publication).where(Publication.account_id==account.id,Publication.status=='scheduled')):
        post.status='cancelled'; post.error_message='Koneksi akun dilepas.'; post.version+=1
    db.commit()


@router.get('/accounts/{account_id}/creator-info')
def creator(account_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    account=own_account(db,user,account_id)
    if account.platform!='tiktok': raise AppError(422,'PLATFORM','Info kreator hanya untuk TikTok.')
    info=oauth.creator_info(oauth.access_token(db,account)); db.commit()
    return {k:info.get(k) for k in ('creator_nickname','privacy_level_options','comment_disabled','duet_disabled','stitch_disabled','max_video_post_duration_sec')}


@router.get('/exports')
def available_exports(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.execute(select(Export,ClipRevision,Project,Asset).join(ClipRevision,ClipRevision.id==Export.clip_revision_id).join(Clip,Clip.id==ClipRevision.clip_id).join(Project,Project.id==Clip.project_id).join(Asset,Asset.id==Export.mp4_asset_id).where(Project.owner_id==user.id,Project.lifecycle_state=='active',Export.status=='ready',Asset.state=='ready').order_by(Export.created_at.desc()).limit(200)).all()
    return {'items':[{'id':e.id,'project_id':p.id,'title':r.title,'project_name':p.name,'revision':r.revision,'duration_ms':r.end_ms-r.start_ms,'bytes':a.bytes,'preview_url':f'/api/v1/assets/{a.id}/content'} for e,r,p,a in rows]}


def export_for_post(db,user,export_id):
    row=db.execute(select(Export,ClipRevision,Project,Asset).join(ClipRevision,ClipRevision.id==Export.clip_revision_id).join(Clip,Clip.id==ClipRevision.clip_id).join(Project,Project.id==Clip.project_id).join(Asset,Asset.id==Export.mp4_asset_id).where(Export.id==export_id,Project.owner_id==user.id,Project.lifecycle_state=='active',Export.status=='ready',Asset.state=='ready')).first()
    if not row: raise AppError(404,'EXPORT_NOT_READY','Pilih hasil ekspor MP4 yang sudah selesai dari proyek Anda.')
    return row


def validate_schedule(db,user,body,revision,asset):
    account=own_account(db,user,body.account_id) if body.account_id else None
    if account and account.platform!=body.platform: raise AppError(422,'PLATFORM','Platform dan akun tujuan berbeda.')
    if body.status=='draft': return account
    if not body.consent: raise AppError(422,'POST_CONSENT','Setujui konten dan akun tujuan sebelum menjadwalkan.')
    if not utcnow()+timedelta(seconds=10) < body.scheduled_at < utcnow()+timedelta(days=366): raise AppError(422,'POST_TIME','Pilih waktu mendatang dalam satu tahun ke depan.')
    if not account or not account.connected or not configured(body.platform): raise AppError(409,'SOCIAL_SETUP','Hubungkan akun tujuan dan lengkapi konfigurasi platform terlebih dahulu.')
    opt=body.options
    if body.platform=='youtube':
        if opt.privacy not in ('private','unlisted','public') or opt.audience is None: raise AppError(422,'POST_OPTIONS','Pilih visibilitas dan audiens YouTube.')
        if '<' in body.title or '>' in body.title: raise AppError(422,'POST_TITLE','Judul YouTube tidak dapat memuat tanda < atau >.')
    elif body.platform=='instagram':
        if not public_media_ready(): raise AppError(409,'SOCIAL_PUBLIC_URL','Instagram memerlukan URL HTTPS publik untuk video. Kalender dapat disimpan sebagai draft.')
        if len(body.caption)>2200 or body.caption.count('#')>30 or asset.bytes>1_000_000_000 or revision.end_ms-revision.start_ms>900000:
            raise AppError(422,'INSTAGRAM_LIMIT','Periksa batas Instagram: caption 2200 karakter, 30 hashtag, video 1 GB / 15 menit.')
    else:
        if not get_settings().tiktok_direct_post_enabled: raise AppError(409,'TIKTOK_SETUP','Direct Post TikTok belum diaktifkan. Simpan draft kalender dan selesaikan persetujuan aplikasi terlebih dahulu.')
        info=oauth.creator_info(oauth.access_token(db,account))
        validate_tiktok(body.title,body.caption,opt.model_dump(),revision.end_ms-revision.start_ms,info)
    return account


def validate_tiktok(title,caption,opt,duration,info):
    if opt['privacy'] not in info.get('privacy_level_options',[]) or not opt['music_consent']:
        raise AppError(422,'TIKTOK_OPTIONS','Pilih privasi TikTok yang tersedia dan setujui konfirmasi penggunaan musik.')
    if duration>int(info.get('max_video_post_duration_sec',0))*1000: raise AppError(422,'TIKTOK_DURATION','Durasi video melewati batas akun TikTok ini.')
    if len((title+'\n'+caption).encode('utf-16-le'))//2>2200: raise AppError(422,'TIKTOK_CAPTION','Judul dan caption TikTok maksimal 2200 karakter.')
    if opt['commercial_paid'] and opt['privacy']=='SELF_ONLY': raise AppError(422,'TIKTOK_BRAND','Konten kemitraan berbayar tidak dapat memakai privasi Hanya saya.')
    for field in ('comment','duet','stitch'):
        if opt['allow_'+field] and info.get(field+'_disabled'): raise AppError(422,'TIKTOK_INTERACTION','Interaksi yang dipilih dinonaktifkan pada akun TikTok.')


@router.get('/posts')
def posts(start:datetime,end:datetime,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not start.tzinfo or not end.tzinfo or not start<end or end-start>timedelta(days=93): raise AppError(422,'CALENDAR_RANGE','Rentang kalender maksimal 93 hari dan harus menyertakan zona waktu.')
    rows=db.scalars(select(Publication).where(Publication.owner_id==user.id,Publication.scheduled_at>=start,Publication.scheduled_at<end).order_by(Publication.scheduled_at).limit(1000))
    return {'items':[post_data(db,row) for row in rows]}


def save_post(db,user,body,row=None):
    export,revision,project,asset=export_for_post(db,user,body.export_id)
    account=validate_schedule(db,user,body,revision,asset)
    if row:
        if row.status not in ('draft','scheduled') or row.version!=body.expected_version: raise AppError(409,'POST_CONFLICT','Jadwal berubah atau sudah mulai dikirim. Muat ulang kalender.')
        row.version+=1
    else:
        row=Publication(owner_id=user.id,request_key=body.request_key); db.add(row)
    row.project_id=project.id; row.export_id=export.id; row.account_id=account.id if account else None
    row.platform=body.platform; row.title=body.title; row.caption=body.caption
    row.scheduled_at=body.scheduled_at.astimezone(timezone.utc); row.timezone=body.timezone; row.status=body.status
    row.options_json=body.options.model_dump(); row.consent_at=utcnow() if body.status=='scheduled' else None
    row.error_message=None
    db.commit(); return post_data(db,row)


@router.post('/posts',status_code=201)
def create_post(body:PostInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    db.scalar(select(User).where(User.id==user.id).with_for_update())
    old=db.scalar(select(Publication).where(Publication.owner_id==user.id,Publication.request_key==body.request_key))
    if old:
        if any((old.export_id!=body.export_id,old.platform!=body.platform,old.title!=body.title,old.caption!=body.caption,aware(old.scheduled_at)!=body.scheduled_at,old.options_json!=body.options.model_dump(),old.account_id!=body.account_id,old.timezone!=body.timezone,bool(old.consent_at)!=(body.status=='scheduled'))):
            raise AppError(409,'IDEMPOTENCY_CONFLICT','Kunci permintaan sudah dipakai untuk jadwal lain.')
        return post_data(db,old)
    return save_post(db,user,body)


@router.patch('/posts/{post_id}')
def update_post(post_id:str,body:PostInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return save_post(db,user,body,own_post(db,user,post_id))


@router.post('/posts/{post_id}/cancel')
def cancel_post(post_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=own_post(db,user,post_id)
    if row.status in (*ACTIVE,'published','uncertain'): raise AppError(409,'POST_SENT','Konten sudah atau mungkin telah dikirim. Periksa platform tujuan; pembatalan lokal tidak menghapus posting di sana.')
    row.status='cancelled'; row.version+=1; db.commit()
    return post_data(db,row)


@router.get('/media/{post_id}')
@router.head('/media/{post_id}')
def public_media(post_id:str,expires:int,signature:str,db:Session=Depends(get_db)):
    if not get_settings().social_encryption_key or expires<time.time() or expires>time.time()+86460 or not hmac.compare_digest(signature,media_signature(post_id,expires)):
        raise AppError(403,'MEDIA_LINK','Tautan video kedaluwarsa atau tidak valid.')
    post=db.get(Publication,post_id)
    project=db.get(Project,post.project_id) if post else None
    export=db.get(Export,post.export_id) if post and post.export_id else None
    asset=db.get(Asset,export.mp4_asset_id) if export else None
    if not post or post.platform!='instagram' or post.status not in ACTIVE or not project or project.lifecycle_state!='active' or not asset or asset.state!='ready':
        raise AppError(404,'MEDIA_LINK','Video tidak tersedia untuk publikasi ini.')
    path=LocalStorage().path(f'social/{post.id}/upload.mp4')
    if not path.is_file(): raise AppError(404,'MEDIA_LINK','Video publikasi belum siap.')
    return FileResponse(path,media_type='video/mp4',headers={'Cache-Control':'private, no-store','Referrer-Policy':'no-referrer'})


@router.post('/posts/{post_id}/check')
def check_post(post_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=own_post(db,user,post_id)
    if row.status!='uncertain': raise AppError(409,'POST_STATUS','Pemeriksaan ulang hanya untuk hasil yang belum pasti.')
    state=unseal(row.remote_state_ciphertext)
    if not any(state.get(k) for k in ('upload_url','video_id','container_id','publish_id')):
        raise AppError(409,'POST_UNKNOWN','Platform belum mengembalikan nomor referensi. Periksa akun secara langsung sebelum membuat jadwal baru.')
    state['check_only']=True; row.remote_state_ciphertext=seal(state)
    row.status='processing'; row.version+=1; row.error_message=None; row.lease_expires_at=None
    db.commit(); return post_data(db,row)


@router.post('/posts/{post_id}/draft')
def retry_draft(post_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=own_post(db,user,post_id)
    if row.status not in ('failed','cancelled'): raise AppError(409,'POST_STATUS','Hanya jadwal gagal atau dibatalkan yang dapat dikembalikan ke draft.')
    row.status='draft'; row.version+=1; row.remote_state_ciphertext=''; row.remote_id=None; row.remote_url=None; row.error_message=None; row.consent_at=None
    db.commit(); return post_data(db,row)
