"""payment profiles, receipts and reminders

Revision ID: 0006_payments_receipts_reminders
Revises: 0005_user_dashboard_archive
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_payments_receipts_reminders"
down_revision = "0005_user_dashboard_archive"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("bank_name", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("account_holder", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("card_number", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("iban", sa.String(length=40), nullable=True))
    op.add_column("users", sa.Column("account_number", sa.String(length=40), nullable=True))
    op.add_column("users", sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("settlements", sa.Column("receipt_file_id", sa.String(length=255), nullable=True))
    op.add_column("settlements", sa.Column("receipt_kind", sa.String(length=20), nullable=True))

    op.create_table(
        "debt_reminder_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("debtor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("creditor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("last_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("group_id", "debtor_user_id", "creditor_user_id", name="uq_debt_reminder_pair"),
    )
    op.create_index("ix_debt_reminder_states_group_id", "debt_reminder_states", ["group_id"])
    op.create_index("ix_debt_reminder_states_debtor_user_id", "debt_reminder_states", ["debtor_user_id"])
    op.create_index("ix_debt_reminder_states_creditor_user_id", "debt_reminder_states", ["creditor_user_id"])
    op.create_index("ix_debt_reminder_states_last_sent_at", "debt_reminder_states", ["last_sent_at"])


def downgrade():
    op.drop_index("ix_debt_reminder_states_last_sent_at", table_name="debt_reminder_states")
    op.drop_index("ix_debt_reminder_states_creditor_user_id", table_name="debt_reminder_states")
    op.drop_index("ix_debt_reminder_states_debtor_user_id", table_name="debt_reminder_states")
    op.drop_index("ix_debt_reminder_states_group_id", table_name="debt_reminder_states")
    op.drop_table("debt_reminder_states")
    op.drop_column("settlements", "receipt_kind")
    op.drop_column("settlements", "receipt_file_id")
    op.drop_column("users", "reminder_enabled")
    op.drop_column("users", "account_number")
    op.drop_column("users", "iban")
    op.drop_column("users", "card_number")
    op.drop_column("users", "account_holder")
    op.drop_column("users", "bank_name")
