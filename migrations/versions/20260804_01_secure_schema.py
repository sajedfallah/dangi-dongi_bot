"""secure transactional schema baseline"""
from alembic import op
import sqlalchemy as sa
revision='20260804_01'; down_revision=None; branch_labels=None; depends_on=None
def upgrade():
    # Baseline for a fresh PostgreSQL deployment; models remain source of truth.
    bind=op.get_bind()
    from models.base import Base
    import models.user,models.event,models.ticket,models.advanced
    Base.metadata.create_all(bind=bind)
def downgrade():
    from models.base import Base
    bind=op.get_bind(); Base.metadata.drop_all(bind=bind)
