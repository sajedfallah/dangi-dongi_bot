"""add two-party settlement lifecycle

Revision ID: 0004_two_party_settlements
Revises: 0003_professional_splits
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_two_party_settlements"
down_revision = "0003_professional_splits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("settlements") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"))
        batch_op.add_column(sa.Column("responded_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_settlements_status", ["status"], unique=False)
    # Existing settlements were accepted under the old one-step flow and stay confirmed.
    op.execute("UPDATE settlements SET status = 'confirmed' WHERE status IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("settlements") as batch_op:
        batch_op.drop_index("ix_settlements_status")
        batch_op.drop_column("responded_at")
        batch_op.drop_column("status")
