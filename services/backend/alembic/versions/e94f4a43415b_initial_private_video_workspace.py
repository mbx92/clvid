"""Initial private video workspace

Revision ID: e94f4a43415b
Revises: 
"""
from alembic import op
import sqlalchemy as sa


revision = 'e94f4a43415b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Frozen initial schema; circular pointers are added after their target tables.
    op.create_table('login_attempts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_login_attempts_created_at'), 'login_attempts', ['created_at'], unique=False)
    op.create_index(op.f('ix_login_attempts_key'), 'login_attempts', ['key'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('projects',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('owner_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('source_asset_id', sa.String(length=36), nullable=True),
    sa.Column('preview_asset_id', sa.String(length=36), nullable=True),
    sa.Column('lifecycle_state', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['preview_asset_id'], ['assets.id'], name='fk_projects_preview', use_alter=True),
    sa.ForeignKeyConstraint(['source_asset_id'], ['assets.id'], name='fk_projects_source', use_alter=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_lifecycle_state'), 'projects', ['lifecycle_state'], unique=False)
    op.create_index(op.f('ix_projects_owner_id'), 'projects', ['owner_id'], unique=False)
    op.create_index('ix_projects_owner_status_updated', 'projects', ['owner_id', 'status', 'updated_at'], unique=False)
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)
    op.create_table('sessions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('csrf_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sessions_expires_at'), 'sessions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('assets',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('storage_key', sa.String(length=512), nullable=False),
    sa.Column('bytes', sa.BigInteger(), nullable=False),
    sa.Column('mime', sa.String(length=100), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=True),
    sa.Column('meta_json', sa.JSON(), nullable=False),
    sa.Column('state', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key')
    )
    op.create_index(op.f('ix_assets_project_id'), 'assets', ['project_id'], unique=False)
    op.create_table('clips',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('origin', sa.String(length=24), nullable=False),
    sa.Column('active_revision_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['active_revision_id'], ['clip_revisions.id'], name='fk_clips_active_revision', use_alter=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clips_project_id'), 'clips', ['project_id'], unique=False)
    op.create_table('jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('stage', sa.String(length=30), nullable=False),
    sa.Column('input_json', sa.JSON(), nullable=False),
    sa.Column('result_json', sa.JSON(), nullable=False),
    sa.Column('input_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('idempotency_key', sa.String(length=128), nullable=True),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('progress', sa.Float(), nullable=True),
    sa.Column('error_code', sa.String(length=100), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'input_fingerprint'),
    sa.UniqueConstraint('project_id', 'kind', 'idempotency_key')
    )
    op.create_index(op.f('ix_jobs_project_id'), 'jobs', ['project_id'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_index('ix_jobs_status_lease', 'jobs', ['status', 'lease_expires_at'], unique=False)
    op.create_table('transcripts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=24), nullable=False),
    sa.Column('model', sa.String(length=128), nullable=False),
    sa.Column('config_json', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'version')
    )
    op.create_index(op.f('ix_transcripts_project_id'), 'transcripts', ['project_id'], unique=False)
    op.create_table('clip_revisions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('clip_id', sa.String(length=36), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('transcript_id', sa.String(length=36), nullable=True),
    sa.Column('start_ms', sa.Integer(), nullable=False),
    sa.Column('end_ms', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('topic', sa.String(length=500), nullable=False),
    sa.Column('crop_json', sa.JSON(), nullable=False),
    sa.Column('subtitle_style_json', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['clip_id'], ['clips.id'], ),
    sa.ForeignKeyConstraint(['transcript_id'], ['transcripts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('clip_id', 'revision')
    )
    op.create_index(op.f('ix_clip_revisions_clip_id'), 'clip_revisions', ['clip_id'], unique=False)
    op.create_table('job_attempts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('job_id', sa.String(length=36), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('worker_id', sa.String(length=200), nullable=True),
    sa.Column('outcome', sa.String(length=30), nullable=True),
    sa.Column('diagnostic_ref', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_id', 'attempt')
    )
    op.create_index(op.f('ix_job_attempts_job_id'), 'job_attempts', ['job_id'], unique=False)
    op.create_table('outbox_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('job_id', sa.String(length=36), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_outbox_events_dispatched_at'), 'outbox_events', ['dispatched_at'], unique=False)
    op.create_index(op.f('ix_outbox_events_job_id'), 'outbox_events', ['job_id'], unique=False)
    op.create_table('transcript_segments',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('transcript_id', sa.String(length=36), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('start_ms', sa.Integer(), nullable=False),
    sa.Column('end_ms', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('words_json', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['transcript_id'], ['transcripts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('transcript_id', 'order')
    )
    op.create_index(op.f('ix_transcript_segments_transcript_id'), 'transcript_segments', ['transcript_id'], unique=False)
    op.create_table('exports',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('clip_revision_id', sa.String(length=36), nullable=False),
    sa.Column('job_id', sa.String(length=36), nullable=False),
    sa.Column('config_json', sa.JSON(), nullable=False),
    sa.Column('mp4_asset_id', sa.String(length=36), nullable=True),
    sa.Column('srt_asset_id', sa.String(length=36), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['clip_revision_id'], ['clip_revisions.id'], ),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.ForeignKeyConstraint(['mp4_asset_id'], ['assets.id'], ),
    sa.ForeignKeyConstraint(['srt_asset_id'], ['assets.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_id')
    )
    op.create_index(op.f('ix_exports_clip_revision_id'), 'exports', ['clip_revision_id'], unique=False)
    op.create_table('provider_usage',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('job_attempt_id', sa.String(length=36), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('model', sa.String(length=128), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('outcome', sa.String(length=30), nullable=False),
    sa.Column('request_id', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['job_attempt_id'], ['job_attempts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_provider_usage_job_attempt_id'), 'provider_usage', ['job_attempt_id'], unique=False)
    op.create_table('subtitle_cues',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('clip_revision_id', sa.String(length=36), nullable=False),
    sa.Column('start_ms', sa.Integer(), nullable=False),
    sa.Column('end_ms', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['clip_revision_id'], ['clip_revisions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subtitle_cues_clip_revision_id'), 'subtitle_cues', ['clip_revision_id'], unique=False)
    if op.get_bind().dialect.name != 'sqlite':
        op.create_foreign_key('fk_projects_source', 'projects', 'assets', ['source_asset_id'], ['id'])
        op.create_foreign_key('fk_projects_preview', 'projects', 'assets', ['preview_asset_id'], ['id'])
        op.create_foreign_key('fk_clips_active_revision', 'clips', 'clip_revisions', ['active_revision_id'], ['id'])


def downgrade():
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_constraint('fk_clips_active_revision', 'clips', type_='foreignkey')
        op.drop_constraint('fk_projects_preview', 'projects', type_='foreignkey')
        op.drop_constraint('fk_projects_source', 'projects', type_='foreignkey')
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_subtitle_cues_clip_revision_id'), table_name='subtitle_cues')
    op.drop_table('subtitle_cues')
    op.drop_index(op.f('ix_provider_usage_job_attempt_id'), table_name='provider_usage')
    op.drop_table('provider_usage')
    op.drop_index(op.f('ix_exports_clip_revision_id'), table_name='exports')
    op.drop_table('exports')
    op.drop_index(op.f('ix_transcript_segments_transcript_id'), table_name='transcript_segments')
    op.drop_table('transcript_segments')
    op.drop_index(op.f('ix_outbox_events_job_id'), table_name='outbox_events')
    op.drop_index(op.f('ix_outbox_events_dispatched_at'), table_name='outbox_events')
    op.drop_table('outbox_events')
    op.drop_index(op.f('ix_job_attempts_job_id'), table_name='job_attempts')
    op.drop_table('job_attempts')
    op.drop_index(op.f('ix_clip_revisions_clip_id'), table_name='clip_revisions')
    op.drop_table('clip_revisions')
    op.drop_index(op.f('ix_transcripts_project_id'), table_name='transcripts')
    op.drop_table('transcripts')
    op.drop_index('ix_jobs_status_lease', table_name='jobs')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_project_id'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_clips_project_id'), table_name='clips')
    op.drop_table('clips')
    op.drop_index(op.f('ix_assets_project_id'), table_name='assets')
    op.drop_table('assets')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_expires_at'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_index(op.f('ix_projects_status'), table_name='projects')
    op.drop_index('ix_projects_owner_status_updated', table_name='projects')
    op.drop_index(op.f('ix_projects_owner_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_lifecycle_state'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_login_attempts_key'), table_name='login_attempts')
    op.drop_index(op.f('ix_login_attempts_created_at'), table_name='login_attempts')
    op.drop_table('login_attempts')
    # ### end Alembic commands ###
