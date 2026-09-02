"""user dashboard and group archive

Revision ID: 0005_user_dashboard_archive
Revises: 0004_two_party_settlements
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_user_dashboard_archive"
down_revision = "0004_two_party_settlements"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("groups", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_groups_is_archived", "groups", ["is_archived"], unique=False)


def downgrade():
    op.drop_index("ix_groups_is_archived", table_name="groups")
    op.drop_column("groups", "is_archived")
