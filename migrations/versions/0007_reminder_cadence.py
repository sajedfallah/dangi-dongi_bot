"""add reminder first-seen timestamp

Revision ID: 0007_reminder_cadence
Revises: 0006_payments_receipts_reminders
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_reminder_cadence"
down_revision = "0006_payments_receipts_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("debt_reminder_states") as batch_op:
        batch_op.add_column(sa.Column("first_seen_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_debt_reminder_states_first_seen_at", ["first_seen_at"], unique=False)

    op.execute(
        "UPDATE debt_reminder_states "
        "SET first_seen_at = COALESCE(last_sent_at, CURRENT_TIMESTAMP) "
        "WHERE first_seen_at IS NULL"
    )

    with op.batch_alter_table("debt_reminder_states") as batch_op:
        batch_op.alter_column("first_seen_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("debt_reminder_states") as batch_op:
        batch_op.drop_index("ix_debt_reminder_states_first_seen_at")
        batch_op.drop_column("first_seen_at")
