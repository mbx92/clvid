"""Persist research sources and editable news scripts."""
from alembic import op
import sqlalchemy as sa

revision = "83cd20010001"
down_revision = "72bc19010001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("script_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        *[sa.Column(name, sa.JSON(), nullable=False) for name in (
            "options_json", "sources_json", "topics_json", "videos_json", "selection_json", "notes_json", "usage_json")],
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("run_token", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_script_drafts_owner_id", "script_drafts", ["owner_id"])


def downgrade():
    op.drop_table("script_drafts")
