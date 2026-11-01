"""Durable publisher. Ambiguous writes stop; they are never blindly repeated."""
import logging
import time
import shutil
from datetime import timedelta
import httpx
from sqlalchemy import select
from app.api.errors import AppError
from app.db import session_scope
from app.domain.models import Asset, ClipRevision, Export, Project, Publication, SocialAccount, utcnow
from app.storage.local import LocalStorage
from .oauth import access_token, creator_info, graph, json_response
from .routes import aware, validate_tiktok
from .security import configured, media_url, seal, trusted_upload_url, unseal

log=logging.getLogger('clipper.publisher')
CHUNK=10*1024*1024


def claim():
    with session_scope() as db:
        for stale in db.scalars(select(Publication).where(Publication.status.in_(('uploading','processing')),Publication.lease_expires_at < utcnow()).with_for_update(skip_locked=True)):
            stale.status='uncertain'; stale.version+=1; stale.lease_expires_at=None
            stale.error_message='Koneksi worker terputus. Periksa status platform sebelum mengulang agar tidak terunggah dua kali.'
        post=db.scalar(select(Publication).where(
            ((Publication.status=='scheduled') & (Publication.scheduled_at<=utcnow())) |
            ((Publication.status=='processing') & Publication.lease_expires_at.is_(None))
        ).order_by(Publication.updated_at).with_for_update(skip_locked=True).limit(1))
        if not post: return None
        if post.status=='scheduled': post.status='uploading'
        post.lease_expires_at=utcnow()+timedelta(minutes=3); post.version+=1
        return post.id,post.version


class Work:
    def __init__(self,post_id,version):
        self.id,self.version=post_id,version
        with session_scope() as db:
            p=db.get(Publication,post_id)
            self.state=unseal(p.remote_state_ciphertext)
            self.platform=p.platform; self.title=p.title; self.caption=p.caption; self.options=p.options_json
            self.account_id=p.account_id; self.project_id=p.project_id
            e=db.get(Export,p.export_id) if p.export_id else None
            a=db.get(Asset,e.mp4_asset_id) if e else None
            r=db.get(ClipRevision,e.clip_revision_id) if e else None
            if not a or a.state!='ready' or not r: raise AppError(409,'EXPORT_MISSING','Hasil ekspor sudah tidak tersedia.')
            self.path=LocalStorage().path(a.storage_key); self.size=self.path.stat().st_size
            self.duration=r.end_ms-r.start_ms
            account=db.get(SocialAccount,p.account_id) if p.account_id else None
            if not account or account.owner_id!=p.owner_id or account.platform!=p.platform: raise AppError(409,'ACCOUNT','Akun tujuan tidak tersedia.')
            self.external_id=account.external_id; self.name=account.name
            if not configured(p.platform): raise AppError(409,'SETUP','Konfigurasi platform belum lengkap.')
            self.token=access_token(db,account)
        self.headers={'Authorization':'Bearer '+self.token}

    def save(self,*,status=None,remote_id=None,remote_url=None,message=None,release=False):
        with session_scope() as db:
            p=db.scalar(select(Publication).where(Publication.id==self.id).with_for_update())
            project=db.get(Project,self.project_id)
            if not p or p.version!=self.version or p.status not in ('uploading','processing') or project.lifecycle_state!='active':
                raise AppError(409,'POST_FENCED','Publikasi sudah berubah atau proyek tidak aktif.')
            p.remote_state_ciphertext=seal(self.state)
            if status: p.status=status
            if remote_id: p.remote_id=remote_id
            if remote_url: p.remote_url=remote_url
            p.error_message=message
            p.lease_expires_at=None if release else utcnow()+timedelta(minutes=3)

    def youtube(self,client):
        if self.state.get('video_id'): return self.youtube_status(client)
        if not self.state.get('upload_url'):
            self.state={'phase':'initializing'}; self.save()
            data={'snippet':{'title':self.title,'description':self.caption,'categoryId':'22'},
                  'status':{'privacyStatus':self.options['privacy'],'selfDeclaredMadeForKids':self.options['audience']=='kids','containsSyntheticMedia':self.options.get('aigc',False)}}
            response=client.post('https://www.googleapis.com/upload/youtube/v3/videos',params={'uploadType':'resumable','part':'snippet,status','notifySubscribers':str(self.options.get('notify_subscribers',False)).lower()},
                headers={**self.headers,'X-Upload-Content-Length':str(self.size),'X-Upload-Content-Type':'video/mp4'},json=data)
            if not response.is_success: json_response(response)
            self.state={'phase':'uploading','upload_url':trusted_upload_url(response.headers['Location'],'youtube')}; self.save()
        url=trusted_upload_url(self.state['upload_url'],'youtube')
        if self.state.get('check_only'):
            response=client.put(url,headers={**self.headers,'Content-Length':'0','Content-Range':f'bytes */{self.size}'},content=b'')
            if response.status_code in (200,201):
                self.state['video_id']=json_response(response)['id']; self.state['phase']='processing'
                self.save(status='processing',remote_id=self.state['video_id'],release=True); return
            self.save(status='uncertain',message='Upload belum terkonfirmasi selesai. Periksa YouTube Studio; tidak ada unggahan baru yang dikirim.',release=True); return
        offset=0
        with self.path.open('rb') as stream:
            while offset<self.size:
                self.save()
                stream.seek(offset); chunk=stream.read(min(CHUNK,self.size-offset))
                response=client.put(url,headers={**self.headers,'Content-Type':'video/mp4','Content-Length':str(len(chunk)),'Content-Range':f'bytes {offset}-{offset+len(chunk)-1}/{self.size}'},content=chunk)
                if response.status_code in (200,201):
                    self.state['video_id']=json_response(response)['id']; self.state['phase']='processing'
                    self.save(status='processing',remote_id=self.state['video_id'],remote_url='https://www.youtube.com/watch?v='+self.state['video_id'],release=True); return
                if response.status_code!=308: json_response(response)
                received=response.headers.get('Range','')
                next_offset=int(received.rsplit('-',1)[-1])+1 if received else 0
                if not offset<next_offset<=offset+len(chunk): raise AppError(502,'UPLOAD_RANGE','Platform mengembalikan posisi upload yang tidak valid.')
                offset=next_offset
        raise AppError(502,'UPLOAD_UNKNOWN','Upload selesai dikirim tetapi platform belum mengonfirmasi hasil.')

    def youtube_status(self,client):
        data=json_response(client.get('https://www.googleapis.com/youtube/v3/videos',params={'part':'status,processingDetails','id':self.state['video_id']},headers=self.headers))
        items=data.get('items',[])
        if not items:
            self.save(status='uncertain',message='Video belum ditemukan di YouTube. Periksa YouTube Studio.',release=True); return
        status=items[0].get('status',{}); processing=items[0].get('processingDetails',{}).get('processingStatus')
        if processing in ('failed','terminated') or status.get('uploadStatus') in ('failed','rejected','deleted'):
            self.save(status='failed',message='YouTube menolak atau gagal memproses video. Periksa YouTube Studio.',release=True)
        elif processing=='succeeded' or status.get('uploadStatus')=='processed':
            self.state['actual_privacy']=status.get('privacyStatus')
            self.save(status='published',remote_url='https://www.youtube.com/watch?v='+self.state['video_id'],message='Visibilitas aktual berbeda dari permintaan; periksa YouTube Studio.' if status.get('privacyStatus')!=self.options['privacy'] else None,release=True)
        else: self.save(status='processing',release=True)

    def instagram(self,client):
        if not self.state.get('container_id'):
            # Instagram's AAC publishing profile uses 128 kbps; keep video intact.
            from app.media.process import ffmpeg
            from app.config import get_settings
            target=LocalStorage().path(f'social/{self.id}/upload.mp4')
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():
                partial=target.with_name('preparing.mp4')
                ffmpeg(['-i',str(self.path),'-map','0:v:0','-map','0:a:0','-c:v','copy','-c:a','aac','-b:a','128k','-ar','48000','-movflags','+faststart',str(partial)],binary=get_settings().ffmpeg_path,timeout=900,progress=lambda _:self.save())
                partial.replace(target)
            self.state={'phase':'initializing'}; self.save()
            data=json_response(client.post(graph()+f'/{self.external_id}/media',headers=self.headers,data={'media_type':'REELS','video_url':media_url(self.id),'caption':self.caption,'share_to_feed':str(self.options.get('share_to_feed',False)).lower()}))
            self.state={'phase':'processing','container_id':data['id']}; self.save(status='processing',release=True); return
        container=self.state['container_id']
        status=json_response(client.get(graph()+f'/{container}',headers=self.headers,params={'fields':'status_code'})).get('status_code')
        if status in ('ERROR','EXPIRED'):
            self.save(status='failed',message='Instagram gagal memproses video atau kontainer kedaluwarsa.',release=True); return
        if status=='PUBLISHED':
            self.save(status='published',remote_url=f'https://www.instagram.com/{self.name}/',release=True); return
        if status!='FINISHED': self.save(status='processing',release=True); return
        if self.state.get('check_only'):
            self.save(status='uncertain',message='Video siap di Instagram tetapi penerbitan belum terkonfirmasi. Periksa akun; permintaan publish tidak diulang otomatis.',release=True); return
        self.state['phase']='publishing'; self.save()
        data=json_response(client.post(graph()+f'/{self.external_id}/media_publish',headers=self.headers,data={'creation_id':container}))
        self.state['media_id']=data['id']; self.state['phase']='published'
        url=f'https://www.instagram.com/{self.name}/'
        try:
            result=json_response(client.get(graph()+f'/{data["id"]}',headers=self.headers,params={'fields':'permalink'}))
            if result.get('permalink','').startswith('https://www.instagram.com/'): url=result['permalink']
        except Exception: pass  # The publish ID already confirms success.
        self.save(status='published',remote_id=data['id'],remote_url=url,release=True)

    def tiktok(self,client):
        from app.config import get_settings
        if self.state.get('publish_id'):
            data=json_response(client.post('https://open.tiktokapis.com/v2/post/publish/status/fetch/',headers=self.headers,json={'publish_id':self.state['publish_id']}))['data']
            status=data.get('status')
            if status=='PUBLISH_COMPLETE':
                ids=data.get('publicaly_available_post_id') or data.get('publicly_available_post_id') or []
                self.save(status='published',remote_id=str(ids[0]) if ids else self.state['publish_id'],release=True)
            elif status=='FAILED': self.save(status='failed',message='TikTok gagal memproses publikasi. Periksa status dan izin akun di TikTok.',release=True)
            else: self.save(status='processing',release=True)
            return
        if not get_settings().tiktok_direct_post_enabled: raise AppError(409,'TIKTOK_SETUP','Direct Post TikTok belum diaktifkan.')
        info=creator_info(self.token); validate_tiktok(self.title,self.caption,self.options,self.duration,info)
        chunk_size=min(CHUNK,self.size); count=max(1,self.size//chunk_size)
        self.state={'phase':'initializing'}; self.save()
        opt=self.options
        data=json_response(client.post('https://open.tiktokapis.com/v2/post/publish/video/init/',headers=self.headers,json={
            'post_info':{'title':self.title+'\n'+self.caption,'privacy_level':opt['privacy'],
                'disable_comment':not opt['allow_comment'],'disable_duet':not opt['allow_duet'],'disable_stitch':not opt['allow_stitch'],
                'brand_content_toggle':opt['commercial_paid'],'brand_organic_toggle':opt['commercial_own'],'is_aigc':opt.get('aigc',False)},
            'source_info':{'source':'FILE_UPLOAD','video_size':self.size,'chunk_size':chunk_size,'total_chunk_count':count}}))['data']
        url=trusted_upload_url(data['upload_url'],'tiktok')
        self.state={'phase':'uploading','publish_id':data['publish_id']}; self.save()
        with self.path.open('rb') as stream:
            for index in range(count):
                self.save()
                offset=stream.tell(); chunk=stream.read(self.size-offset if index==count-1 else chunk_size)
                response=client.put(url,headers={'Content-Type':'video/mp4','Content-Length':str(len(chunk)),'Content-Range':f'bytes {offset}-{offset+len(chunk)-1}/{self.size}'},content=chunk)
                if not response.is_success: raise AppError(502,'TIKTOK_UPLOAD','Transfer video TikTok belum terkonfirmasi.')
        self.state['phase']='processing'; self.save(status='processing',release=True)


def run_one(post_id,version):
    try:
        work=Work(post_id,version)
        with httpx.Client(timeout=httpx.Timeout(120,connect=20),follow_redirects=False) as client:
            getattr(work,work.platform)(client)
    except Exception as exc:
        with session_scope() as db:
            p=db.scalar(select(Publication).where(Publication.id==post_id).with_for_update())
            if not p or p.version!=version or p.status not in ('uploading','processing'): return
            # Any persisted remote phase means a side effect may have happened.
            try:
                remote_started=bool(unseal(p.remote_state_ciphertext).get('phase'))
            except Exception:
                remote_started=bool(p.remote_state_ciphertext)
            p.status='uncertain' if remote_started else 'failed'
            p.error_message=(exc.message if isinstance(exc,AppError) else 'Koneksi publikasi terputus. Periksa status platform sebelum mengulang.')
            p.lease_expires_at=None


def main():
    logging.basicConfig(level=logging.WARNING)
    while True:
        try:
            item=claim()
            if item: run_one(*item)
            cleanup_once()
        except Exception:
            log.warning('Publisher unavailable; no new upload started')
        time.sleep(15)


def cleanup_once():
    root=LocalStorage().path('social')
    if not root.exists(): return
    with session_scope() as db:
        active=set(db.scalars(select(Publication.id).where(Publication.status.in_(('uploading','processing','uncertain')))))
    for directory in root.iterdir():
        if directory.is_dir() and not directory.is_symlink() and directory.name not in active and time.time()-directory.stat().st_mtime>86400:
            shutil.rmtree(directory)


if __name__=='__main__': main()
