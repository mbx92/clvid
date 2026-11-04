"""Storyboard documents and reusable user themes."""
from alembic import op
import sqlalchemy as sa

revision = "94de30010001"
down_revision = "83cd20010001"
branch_labels = depends_on = None

def upgrade():
    op.create_table("storyboards", sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), primary_key=True),
                    sa.Column("version", sa.Integer(), nullable=False), sa.Column("document_json", sa.JSON(), nullable=False))
    op.create_table("story_templates", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
                    sa.Column("name", sa.String(80), nullable=False), sa.Column("theme_json", sa.JSON(), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_story_templates_owner_id", "story_templates", ["owner_id"])

def downgrade():
    op.drop_table("story_templates")
    op.drop_table("storyboards")
