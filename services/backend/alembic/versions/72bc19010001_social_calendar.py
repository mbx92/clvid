"""Account connections, OAuth state and persistent publishing calendar."""
from alembic import op
import sqlalchemy as sa
revision = '72bc19010001'
down_revision = '51ad8d802001'
branch_labels = depends_on = None


def upgrade():
    op.create_table('social_accounts',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False,index=True),
        sa.Column('platform',sa.String(20),nullable=False),sa.Column('external_id',sa.String(200),nullable=False),
        sa.Column('name',sa.String(200),nullable=False),sa.Column('token_ciphertext',sa.Text(),nullable=False),
        sa.Column('connected',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('owner_id','platform','external_id'))
    op.create_table('social_oauth_states',
        sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('session_id',sa.String(64),nullable=False),sa.Column('platform',sa.String(20),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('publications',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False,index=True),
        sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False,index=True),
        sa.Column('export_id',sa.String(36),sa.ForeignKey('exports.id',ondelete='SET NULL')),
        sa.Column('account_id',sa.String(36),sa.ForeignKey('social_accounts.id',ondelete='SET NULL')),
        sa.Column('platform',sa.String(20),nullable=False),sa.Column('title',sa.String(100),nullable=False),
        sa.Column('caption',sa.Text(),nullable=False),sa.Column('status',sa.String(24),nullable=False),
        sa.Column('scheduled_at',sa.DateTime(timezone=True),nullable=False),sa.Column('timezone',sa.String(50),nullable=False),
        sa.Column('options_json',sa.JSON(),nullable=False),sa.Column('request_key',sa.String(64),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('consent_at',sa.DateTime(timezone=True)),
        sa.Column('lease_expires_at',sa.DateTime(timezone=True)),sa.Column('remote_state_ciphertext',sa.Text(),nullable=False),
        sa.Column('remote_id',sa.String(200)),sa.Column('remote_url',sa.Text()),sa.Column('error_message',sa.Text()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('owner_id','request_key'))
    op.create_index('ix_publications_due','publications',['status','scheduled_at'])


def downgrade():
    op.drop_table('publications')
    op.drop_table('social_oauth_states')
    op.drop_table('social_accounts')
