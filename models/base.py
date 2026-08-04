from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declarative_base


Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )