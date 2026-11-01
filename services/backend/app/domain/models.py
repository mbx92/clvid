from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessingSettings(Base):
    __tablename__ = "processing_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    max_video_seconds: Mapped[int] = mapped_column(Integer)
    max_upload_bytes: Mapped[int] = mapped_column(BigInteger)
    max_clip_ms: Mapped[int] = mapped_column(Integer)


class LegacyScriptDraft(Base):
    """Schema-only compatibility for drafts created before the feature was retired."""
    __tablename__ = "script_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    options_json: Mapped[dict] = mapped_column(JSON)
    sources_json: Mapped[list] = mapped_column(JSON, default=list)
    topics_json: Mapped[list] = mapped_column(JSON, default=list)
    videos_json: Mapped[list] = mapped_column(JSON, default=list)
    selection_json: Mapped[dict] = mapped_column(JSON, default=dict)
    notes_json: Mapped[list] = mapped_column(JSON, default=list)
    usage_json: Mapped[list] = mapped_column(JSON, default=list)
    script: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="retired")
    error_message: Mapped[str | None] = mapped_column(Text)
    run_token: Mapped[str] = mapped_column(String(36), default=new_id)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("owner_id", "platform", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    token_ciphertext: Mapped[str] = mapped_column(Text)
    connected: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SocialOAuthState(Base):
    __tablename__ = "social_oauth_states"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (UniqueConstraint("owner_id", "request_key"), Index("ix_publications_due", "status", "scheduled_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    export_id: Mapped[str | None] = mapped_column(ForeignKey("exports.id", ondelete="SET NULL"))
    account_id: Mapped[str | None] = mapped_column(ForeignKey("social_accounts.id", ondelete="SET NULL"))
    platform: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(100))
    caption: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Makassar")
    options_json: Mapped[dict] = mapped_column(JSON, default=dict)
    request_key: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remote_state_ciphertext: Mapped[str] = mapped_column(Text, default="")
    remote_id: Mapped[str | None] = mapped_column(String(200))
    remote_url: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_owner_status_updated", "owner_id", "status", "updated_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    source_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", use_alter=True, name="fk_projects_source"))
    preview_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", use_alter=True, name="fk_projects_preview"))
    lifecycle_state: Mapped[str] = mapped_column(String(24), default="active", index=True)
    status: Mapped[str] = mapped_column(String(24), default="empty", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    mime: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    checksum: Mapped[str | None] = mapped_column(String(64))
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transcript(Base):
    __tablename__ = "transcripts"
    __table_args__ = (UniqueConstraint("project_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(128))
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("transcript_id", "order"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    transcript_id: Mapped[str] = mapped_column(ForeignKey("transcripts.id"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    words_json: Mapped[list | None] = mapped_column(JSON)


class Clip(Base):
    __tablename__ = "clips"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    origin: Mapped[str] = mapped_column(String(24), default="manual")
    active_revision_id: Mapped[str | None] = mapped_column(ForeignKey("clip_revisions.id", use_alter=True, name="fk_clips_active_revision"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClipRevision(Base):
    __tablename__ = "clip_revisions"
    __table_args__ = (UniqueConstraint("clip_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    clip_id: Mapped[str] = mapped_column(ForeignKey("clips.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    transcript_id: Mapped[str | None] = mapped_column(ForeignKey("transcripts.id"))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text, default="")
    topic: Mapped[str] = mapped_column(String(500), default="")
    crop_json: Mapped[dict] = mapped_column(JSON, default=lambda: {"mode": "fill", "x": 0.5, "y": 0.5})
    subtitle_style_json: Mapped[dict] = mapped_column(JSON, default=lambda: {"enabled": True, "font_size": 52, "position": "bottom", "background": True, "safe_margin": 0.15})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SubtitleCue(Base):
    __tablename__ = "subtitle_cues"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    clip_revision_id: Mapped[str] = mapped_column(ForeignKey("clip_revisions.id"), index=True)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("project_id", "input_fingerprint"), UniqueConstraint("project_id", "kind", "idempotency_key"), Index("ix_jobs_status_lease", "status", "lease_expires_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(30))
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    limits_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float | None] = mapped_column(Float)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (UniqueConstraint("job_id", "attempt"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(200))
    outcome: Mapped[str | None] = mapped_column(String(30))
    diagnostic_ref: Mapped[str | None] = mapped_column(String(200))


class JobRequest(Base):
    """Remember every request key, including aliases deduplicated to an existing job."""
    __tablename__ = "job_requests"
    __table_args__ = (UniqueConstraint("project_id", "kind", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Export(Base):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    clip_revision_id: Mapped[str] = mapped_column(ForeignKey("clip_revisions.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    mp4_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    srt_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderUsage(Base):
    __tablename__ = "provider_usage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_attempt_id: Mapped[str] = mapped_column(ForeignKey("job_attempts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50), default="deepseek")
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(30))
    request_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
