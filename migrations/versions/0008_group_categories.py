"""add group custom categories

Revision ID: 0008_group_categories
Revises: 0007_reminder_cadence
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_group_categories"
down_revision = "0007_reminder_cadence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("group_id", "name", name="uq_group_category_name"),
    )
    op.create_index("ix_group_categories_group_id", "group_categories", ["group_id"], unique=False)
    op.create_index("ix_group_categories_created_by_user_id", "group_categories", ["created_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_group_categories_created_by_user_id", table_name="group_categories")
    op.drop_index("ix_group_categories_group_id", table_name="group_categories")
    op.drop_table("group_categories")
