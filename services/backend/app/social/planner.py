"""Prepare reviewable drafts only. Approval remains an explicit user action."""
import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.db import session_scope
from app.domain.models import Asset, Clip, ClipRevision, Export, Project, Publication, PublicationAutomation, SocialAccount, User, utcnow

DEFAULTS = {'enabled': True, 'timezone': 'Asia/Makassar', 'times': ['18:00'], 'account_ids': []}


def preferences(db, owner_id):
    row = db.get(PublicationAutomation, owner_id)
    return {**DEFAULTS, **(row.settings_json if row else {})}


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def next_slot(settings, occupied, now):
    zone = ZoneInfo(settings['timezone'])
    start = now.astimezone(zone).date()
    for offset in range(365):
        day = start + timedelta(days=offset)
        for clock in sorted(settings['times']):
            candidate = datetime.combine(day, datetime.strptime(clock, '%H:%M').time(), zone).astimezone(timezone.utc)
            if candidate > now + timedelta(minutes=15) and all(abs((candidate - value).total_seconds()) >= 1800 for value in occupied):
                return candidate
    return None


def plan_owner(db, owner_id):
    # Serialize planner and preference changes across API requests / worker replicas.
    db.scalar(select(User).where(User.id == owner_id).with_for_update())
    settings = preferences(db, owner_id)
    if not settings['enabled']:
        return 0
    accounts = list(db.scalars(select(SocialAccount).where(SocialAccount.owner_id == owner_id, SocialAccount.connected.is_(True)).order_by(SocialAccount.id)))
    if settings['account_ids']:
        accounts = [a for a in accounts if a.id in settings['account_ids']]
    if not accounts:
        return 0
    rows = db.execute(select(Export, ClipRevision, Project).join(ClipRevision, ClipRevision.id == Export.clip_revision_id)
        .join(Clip, Clip.id == ClipRevision.clip_id).join(Project, Project.id == Clip.project_id)
        .join(Asset, Asset.id == Export.mp4_asset_id).where(Project.owner_id == owner_id,
            Project.lifecycle_state == 'active', Export.status == 'ready', Asset.state == 'ready',
            Asset.mime == 'video/mp4', Clip.active_revision_id == ClipRevision.id)
        .order_by(Export.created_at.desc(), Export.id)).all()
    # One finished export per clip; repeated renders must not cause repeated uploads.
    latest = {}
    for export, revision, project in rows:
        latest.setdefault(revision.clip_id, (export, revision, project))
    existing = list(db.scalars(select(Publication).where(Publication.owner_id == owner_id)))
    represented = set()
    for post in existing:
        export = db.get(Export, post.export_id) if post.export_id else None
        revision = db.get(ClipRevision, export.clip_revision_id) if export else None
        if revision:
            represented.add((revision.clip_id, post.account_id))
    keys = {p.request_key for p in existing}
    now = utcnow()
    created = 0
    for account in accounts:
        occupied = [aware(p.scheduled_at) for p in existing if p.account_id == account.id and p.status not in ('cancelled', 'failed')]
        for export, revision, project in reversed(list(latest.values())):
            key = 'auto:' + hashlib.sha256(f'{revision.clip_id}:{account.id}'.encode()).hexdigest()[:59]
            if key in keys or (revision.clip_id, account.id) in represented:
                continue
            slot = next_slot(settings, occupied, now)
            if slot is None or created >= 100:
                break
            title = (revision.title or project.name).replace('<', '').replace('>', '').strip()[:100] or 'Video baru'
            options = {'privacy': 'public', 'audience': 'general'} if account.platform == 'youtube' else {}
            db.add(Publication(owner_id=owner_id, project_id=project.id, export_id=export.id, account_id=account.id,
                platform=account.platform, title=title, caption=(revision.topic or title)[:2200],
                status='draft', scheduled_at=slot, timezone=settings['timezone'], options_json=options, request_key=key))
            occupied.append(slot)
            keys.add(key)
            created += 1
    db.flush()
    return created


def plan_once():
    with session_scope() as db:
        owners = list(db.scalars(select(User.id)))
    for owner_id in owners:
        with session_scope() as db:
            plan_owner(db, owner_id)
