"""Read-only YouTube history and resumable synchronization."""
from alembic import op
import sqlalchemy as sa

revision = 'b6fa50010001'
down_revision = 'a5ef40010001'
branch_labels = depends_on = None


def upgrade():
    op.create_table('youtube_videos',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('social_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('video_id', sa.String(32), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('caption', sa.Text(), nullable=False),
        sa.Column('thumbnail_url', sa.Text()),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('available', sa.Boolean(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('account_id', 'video_id'))
    for column in ('owner_id', 'account_id', 'published_at'):
        op.create_index('ix_youtube_videos_'+column, 'youtube_videos', [column])
    op.create_table('youtube_sync_states',
        sa.Column('account_id', sa.String(36), sa.ForeignKey('social_accounts.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('uploads_playlist_id', sa.String(200)),
        sa.Column('cursor', sa.Text()),
        sa.Column('cycle_started_at', sa.DateTime(timezone=True)),
        sa.Column('last_synced_at', sa.DateTime(timezone=True)),
        sa.Column('next_sync_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('error_message', sa.Text()))


def downgrade():
    op.drop_table('youtube_sync_states')
    op.drop_table('youtube_videos')
