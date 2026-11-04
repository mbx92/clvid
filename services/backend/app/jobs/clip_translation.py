from sqlalchemy import select
from app.ai.translate_subtitles import translate_cues
from app.db import session_scope
from app.domain.models import Clip, ClipRevision, SubtitleCue, ProviderUsage
from app.media.process import MediaError


def _revision(db, ctx):
    job, project = ctx.check(db)
    clip = db.get(Clip, job.input_json['clip_id'])
    revision = db.get(ClipRevision, job.input_json['clip_revision_id'])
    if not clip or clip.project_id != project.id or not revision or revision.clip_id != clip.id:
        raise MediaError('clip_missing','Klip tidak tersedia untuk terjemahan.')
    if clip.active_revision_id != revision.id:
        raise MediaError('revision_conflict','Klip sudah berubah. Terjemahkan kembali dari revisi terbaru.')
    return clip, revision


def translate_subtitles(ctx, scratch):
    from app.jobs.tasks import _complete
    with session_scope() as db:
        _, revision = _revision(db,ctx)
        cues = [{'start_ms':c.start_ms,'end_ms':c.end_ms,'text':c.text} for c in db.scalars(
            select(SubtitleCue).where(SubtitleCue.clip_revision_id == revision.id).order_by(SubtitleCue.start_ms,SubtitleCue.id))]
    if not cues:
        raise MediaError('subtitles_empty','Buat subtitle dari audio terlebih dahulu.')
    def usage(report):
        with session_scope() as db:
            ctx.check(db)
            db.add(ProviderUsage(job_attempt_id=ctx.attempt_id,**report))
    ctx.stage('subtitle_translate')
    translated = translate_cues(cues,ctx.settings,ctx.cancelled,usage,ctx.progress)
    with session_scope() as db:
        clip, revision = _revision(db,ctx)
        _complete(db,ctx,{'clip_id':clip.id,'base_revision':revision.revision,'target_language':'id',
                          'translated_cues':translated,'message':'Terjemahan siap ditinjau. Subtitle asli belum diubah.'})
