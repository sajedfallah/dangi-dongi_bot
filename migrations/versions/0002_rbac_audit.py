"""rbac and audit

Revision ID: 0002_rbac_audit
Revises: 0001_initial
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_rbac_audit"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("expenses") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_expenses_created_by_user_id_users",
            "users",
            ["created_by_user_id"],
            ["id"],
        )
        batch_op.create_index("ix_expenses_created_by_user_id", ["created_by_user_id"], unique=False)

    op.execute("UPDATE expenses SET updated_at = created_at WHERE updated_at IS NULL")

    with op.batch_alter_table("expenses") as batch_op:
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_logs_group_id", "audit_logs", ["group_id"], unique=False)
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"], unique=False)
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"], unique=False)
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_logs")
    with op.batch_alter_table("expenses") as batch_op:
        batch_op.drop_index("ix_expenses_created_by_user_id")
        batch_op.drop_constraint("fk_expenses_created_by_user_id_users", type_="foreignkey")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_by_user_id")
