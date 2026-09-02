"""professional split metadata

Revision ID: 0003_professional_splits
Revises: 0002_rbac_audit
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_professional_splits"
down_revision = "0002_rbac_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("split_mode", sa.String(length=20), nullable=False, server_default="equal"))
        batch.add_column(sa.Column("split_config", sa.Text(), nullable=True))
    with op.batch_alter_table("expenses") as batch:
        batch.alter_column("split_mode", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("split_config")
        batch.drop_column("split_mode")
