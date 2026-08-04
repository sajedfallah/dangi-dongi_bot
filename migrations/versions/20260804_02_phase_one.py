"""phase one commerce wallet waitlist notifications"""

from alembic import op

revision = "20260804_02"
down_revision = "20260804_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create phase-one commerce tables.

    The refund_requests.amount column already exists in the baseline model,
    so it must not be added again.
    """
    bind = op.get_bind()

    # Import all dependent models so SQLAlchemy knows their referenced tables.
    import models.user
    import models.event
    import models.ticket
    import models.advanced
    import models.commerce

    from models.commerce import (
        ScheduledNotification,
        WaitlistEntry,
        Wallet,
        WalletTransaction,
        WithdrawalRequest,
    )

    tables = (
        Wallet.__table__,
        WalletTransaction.__table__,
        WithdrawalRequest.__table__,
        WaitlistEntry.__table__,
        ScheduledNotification.__table__,
    )

    for table in tables:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()

    import models.user
    import models.event
    import models.ticket
    import models.advanced
    import models.commerce

    from models.commerce import (
        ScheduledNotification,
        WaitlistEntry,
        Wallet,
        WalletTransaction,
        WithdrawalRequest,
    )

    tables = (
        ScheduledNotification.__table__,
        WaitlistEntry.__table__,
        WithdrawalRequest.__table__,
        WalletTransaction.__table__,
        Wallet.__table__,
    )

    for table in tables:
        table.drop(bind=bind, checkfirst=True)