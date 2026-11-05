"""Persistent automatic publication planning preferences."""
from alembic import op
import sqlalchemy as sa

revision = 'a5ef40010001'
down_revision = '94de30010001'
branch_labels = depends_on = None


def upgrade():
    op.create_table('publication_automation',
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('settings_json', sa.JSON(), nullable=False))


def downgrade():
    op.drop_table('publication_automation')
