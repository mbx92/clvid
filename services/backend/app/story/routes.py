from pathlib import Path
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.api.auth import current_user
from app.api.errors import AppError
from app.api.routes import own_project, queue_job
from app.api.serializers import asset_data, job_data
from app.config import get_settings
from app.db import get_db
from app.domain.models import Asset, Job, Project, Storyboard, StoryTemplate, User, utcnow
from app.media.process import MediaError
from app.storage.local import LocalStorage
from .schemas import Document, SaveInput, ActionInput, TemplateInput, PRESETS
from .script_input import parse_storyboard, table_document
from .visuals import fill_visuals
from .production import ProductionInput, plan
from .providers import capabilities

router = APIRouter(prefix="/studio", tags=["storyboard"])

def owned(db, user, id, lock=False):
    project = own_project(db, user, id, lock=lock)
    story = db.get(Storyboard, id)
    if not story:
        raise AppError(404, "STORY_NOT_FOUND", "Storyboard tidak ditemukan.")
    return project, story

def version_check(story, expected):
    if story.version != expected:
        raise AppError(409, "REVISION_CONFLICT", "Storyboard telah berubah. Muat ulang sebelum menyimpan atau memproses.")

def validate_assets(db, project_id, doc):
    for scene in doc.scenes:
        for id, kinds in [(scene.asset_id, ("image", "video")), (scene.audio_id, ("audio",))]:
            if not id:
                continue
            asset = db.get(Asset, id)
            if not asset or asset.project_id != project_id or asset.state != "ready" or asset.meta_json.get("story_kind") not in kinds:
                raise AppError(422, "INVALID_STORY_ASSET", "Pilih aset milik storyboard ini yang sudah selesai diunggah.")
            if asset.meta_json["story_kind"] == "video" and scene.media_start_ms + scene.duration_ms > asset.meta_json["duration_ms"]:
                raise AppError(422, "STORY_VIDEO_BOUNDS", "Durasi adegan melewati akhir video. Sesuaikan durasi atau titik mulai video.")

def detail(db, project, story):
    return {"id": project.id, "version": story.version, "document": story.document_json,
            "ai_available": bool(get_settings().deepseek_api_key),
            "capabilities": capabilities(get_settings()),
            "assets": [asset_data(a) for a in db.scalars(select(Asset).where(Asset.project_id == project.id, Asset.state == "ready", Asset.kind == "story_media").order_by(Asset.created_at))],
            "jobs": [job_data(j) for j in db.scalars(select(Job).where(Job.project_id == project.id).order_by(Job.created_at.desc()).limit(30))]}

@router.get("/templates")
def templates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": [*PRESETS, *[{"id": t.id, "name": t.name, "theme": t.theme_json, "custom": True} for t in db.scalars(select(StoryTemplate).where(StoryTemplate.owner_id == user.id).order_by(StoryTemplate.created_at.desc()))]]}

@router.post("/templates", status_code=201)
def save_template(body: TemplateInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    if db.scalar(select(func.count()).select_from(StoryTemplate).where(StoryTemplate.owner_id == user.id)) >= 100:
        raise AppError(422, "TEMPLATE_LIMIT", "Maksimal 100 template pribadi. Hapus template yang tidak dipakai.")
    t = StoryTemplate(owner_id=user.id, name=body.name, theme_json=body.theme.model_dump())
    db.add(t); db.commit()
    return {"id": t.id, "name": t.name, "theme": t.theme_json, "custom": True}

@router.delete("/templates/{id}", status_code=204)
def delete_template(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.scalar(select(StoryTemplate).where(StoryTemplate.id == id, StoryTemplate.owner_id == user.id))
    if not t:
        raise AppError(404, "TEMPLATE_NOT_FOUND", "Template tidak ditemukan.")
    db.delete(t); db.commit()

@router.get("")
def listing(page: int = Query(1, ge=1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Project, Storyboard).join(Storyboard).where(Project.owner_id == user.id, Project.lifecycle_state == "active")
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(Project.updated_at.desc()).offset((page - 1) * 24).limit(24)).all()
    return {"items": [{"id": p.id, "title": p.name, "version": s.version, "scene_count": len(s.document_json["scenes"]),
                       "theme": s.document_json["theme"], "updated_at": p.updated_at} for p, s in rows], "total": total}

@router.post("", status_code=201)
def create(body: Document, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if any(s.asset_id or s.audio_id for s in body.scenes):
        raise AppError(422, "INVALID_STORY_ASSET", "Unggah aset setelah membuat storyboard.")
    project = Project(owner_id=user.id, name=body.title, status="ready")
    db.add(project); db.flush()
    story = Storyboard(project_id=project.id, document_json=body.model_dump())
    db.add(story); db.commit()
    return detail(db, project, story)

@router.get("/{id}")
def get(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return detail(db, *owned(db, user, id))

@router.put("/{id}")
def save(id: str, body: SaveInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project, story = owned(db, user, id, lock=True)
    version_check(story, body.expected_version)
    validate_assets(db, id, body.document)
    story.document_json, story.version = body.document.model_dump(), story.version + 1
    project.name, project.updated_at = body.document.title, utcnow()
    db.commit()
    return detail(db, project, story)

@router.post("/{id}/generate", status_code=202)
def generate(id: str, body: ActionInput, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project, story = owned(db, user, id, lock=True)
    version_check(story, body.expected_version)
    if not get_settings().deepseek_api_key:
        raise AppError(422, "AI_NOT_CONFIGURED", "DeepSeek belum dikonfigurasi. Anda tetap dapat menyusun adegan dan gaya secara manual.")
    if body.mode != 'visuals' and not story.document_json["script" if body.mode == "storyboard" else "style_prompt"]:
        raise AppError(422, "PROMPT_EMPTY", "Isi naskah atau prompt gaya terlebih dahulu.")
    if body.mode == 'storyboard':
        try:
            parse_storyboard(story.document_json['script'])
        except MediaError as e:
            raise AppError(422, e.code, e.message) from e
    if body.scene_id and not any(s['id'] == body.scene_id for s in story.document_json['scenes']):
        raise AppError(422, 'STORY_SCENE_MISSING', 'Adegan tidak ditemukan.')
    if body.mode == 'visuals' and not any(not s.get('asset_id') and (not body.scene_id or s['id'] == body.scene_id) for s in story.document_json['scenes']):
        raise AppError(422, 'STORY_VISUAL_TARGETS', 'Pilih adegan tanpa unggahan gambar/video untuk membuat ilustrasi.')
    job = queue_job(db, project, "story_generate", {"version": story.version, "mode": body.mode, "scene_id": body.scene_id, "document": story.document_json, "schema_version": 3}, idempotency_key)
    db.commit()
    return job_data(job)

@router.post('/{id}/import-table')
def import_table(id: str, body: ActionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, story = owned(db, user, id)
    version_check(story, body.expected_version)
    try:
        parsed = parse_storyboard(story.document_json['script'])
        if not parsed:
            raise MediaError('story_table_missing', 'Tabel belum ditemukan. Gunakan kolom Waktu, Visual dan suara, serta Narasi siap rekam.')
        return {'document': table_document(story.document_json, parsed), 'base_version': story.version, 'mode': 'storyboard'}
    except MediaError as e:
        raise AppError(422, e.code, e.message) from e

@router.post('/{id}/visuals')
def suggest_visuals(id: str, body: ActionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, story = owned(db, user, id)
    version_check(story, body.expected_version)
    if body.scene_id and not any(s['id'] == body.scene_id for s in story.document_json['scenes']):
        raise AppError(422, 'STORY_SCENE_MISSING', 'Adegan tidak ditemukan.')
    return {'document': fill_visuals(story.document_json, body.scene_id), 'base_version':story.version, 'mode':'visuals'}

@router.post("/{id}/render", status_code=202)
def render(id: str, body: ActionInput, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project, story = owned(db, user, id, lock=True)
    version_check(story, body.expected_version)
    document = Document.model_validate(story.document_json)
    validate_assets(db, id, document)
    job = queue_job(db, project, "story_render", {"version": story.version, "document": document.model_dump(), "renderer_version": 3}, idempotency_key)
    db.commit()
    return job_data(job)

@router.post('/{id}/produce', status_code=202)
def produce(id: str, body: ProductionInput, idempotency_key: str | None = Header(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    project, story = owned(db, user, id, lock=True)
    version_check(story, body.expected_version)
    document = Document.model_validate(story.document_json)
    validate_assets(db, id, document)
    if body.scene_id and not any(s.id == body.scene_id for s in document.scenes):
        raise AppError(422, 'STORY_SCENE_MISSING', 'Adegan tidak ditemukan.')
    if body.replace_existing and not body.scene_id:
        raise AppError(422, 'STORY_REPLACE_SCENE', 'Pilih satu adegan untuk mengganti aset yang sudah ada.')
    targets = plan(document.model_dump(), body.mode, body.scene_id, body.replace_existing)
    if not targets:
        raise AppError(422, 'STORY_PRODUCTION_EMPTY', 'Tidak ada adegan yang perlu diproses. Isi narasi, pilih rekaman, atau pilih satu adegan untuk mengganti media.')
    available = capabilities(get_settings())
    if any(t[1] for t in targets) and not available['images'] or any(t[2] for t in targets) and not available['speech']:
        message = ('Model gambar atau suara lokal belum siap. Selesaikan pemasangan model Story Studio atau unggah media sendiri.'
                   if available['provider'] == 'local' else
                   'Layanan gambar atau suara belum aktif. Konfigurasikan OPENAI_API_KEY di server atau unggah media sendiri.')
        raise AppError(422, 'STORY_PROVIDER_NOT_CONFIGURED', message)
    voice = body.voice or available['default_voice']
    if any(t[2] for t in targets) and voice not in available['voices']:
        raise AppError(422, 'STORY_VOICE_INVALID', 'Pilih suara narator yang tersedia.')
    settings = get_settings()
    inputs = {'version': story.version, 'document': document.model_dump(), 'mode': body.mode,
              'scene_id': body.scene_id, 'voice': voice, 'replace_existing': body.replace_existing, 'producer_version': 2,
              'provider_config': {name: getattr(settings, name) for name in
                                  ('story_media_provider', 'openai_base_url', 'story_image_model', 'story_image_quality', 'story_speech_model',
                                   'story_local_image_steps', 'story_local_image_device', 'story_local_prompt_language')}}
    active = db.scalar(select(Job).where(Job.project_id == id, Job.kind == 'story_produce', Job.status.in_(('queued', 'running', 'cancel_requested'))))
    if active and active.input_json != inputs:
        raise AppError(409, 'STORY_PRODUCTION_ACTIVE', 'Produksi storyboard masih berjalan. Tunggu selesai atau batalkan proses sebelumnya.')
    job = queue_job(db, project, 'story_produce', inputs, idempotency_key)
    db.commit()
    return job_data(job)

@router.post("/{id}/assets", status_code=201)
async def upload(id: str, request: Request, filename: str = Query(max_length=200), user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned(db, user, id)
    suffix = Path(filename).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".mp4", ".mp3", ".wav", ".m4a"):
        raise AppError(422, "STORY_FILE_TYPE", "Gunakan PNG, JPG, MP4, MP3, WAV, atau M4A.")
    storage = LocalStorage()
    key = storage.new_key(id, suffix)
    temporary = storage.prepare(key + ".upload")
    output = None
    final_key = None
    committed = False
    try:
        size = 0
        with temporary.open("wb") as f:
            async for block in request.stream():
                size += len(block)
                if size > 60 * 1024 * 1024:
                    raise AppError(413, "STORY_FILE_SIZE", "Maksimal 60 MB per aset.")
                f.write(block)
        from .media import normalize_upload
        output, mime, metadata = await run_in_threadpool(normalize_upload, temporary, suffix, get_settings())
        project, _ = owned(db, user, id, lock=True)
        final_key = storage.new_key(id, output.suffix)
        final = storage.publish(output, final_key)
        asset = Asset(project_id=id, kind="story_media", storage_key=final_key, bytes=final.stat().st_size,
                      mime=mime, state="ready", meta_json={**metadata, "filename": Path(filename).name})
        db.add(asset); project.updated_at = utcnow(); db.commit()
        committed = True
        return asset_data(asset)
    except MediaError as e:
        raise AppError(422, e.code, e.message) from e
    finally:
        temporary.unlink(missing_ok=True)
        if output:
            output.unlink(missing_ok=True)
        if final_key and not committed:
            storage.remove(final_key)
