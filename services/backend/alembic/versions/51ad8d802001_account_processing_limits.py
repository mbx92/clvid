"""Persist account limits and immutable job limit snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "51ad8d802001"
down_revision = "fe38e7a7c3c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("processing_settings",
                    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("max_video_seconds", sa.Integer(), nullable=False),
                    sa.Column("max_upload_bytes", sa.BigInteger(), nullable=False),
                    sa.Column("max_clip_ms", sa.Integer(), nullable=False))
    op.add_column("jobs", sa.Column("limits_json", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("jobs", "limits_json")
    op.drop_table("processing_settings")
