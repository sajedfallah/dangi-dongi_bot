from sqlalchemy import Column, Integer, String, Text, BigInteger, ForeignKey, DateTime, Enum
from .base import Base
from .enums import EventStatus
class Event(Base):
    __tablename__='events'
    id=Column(Integer, primary_key=True, index=True)
    title=Column(String(100), nullable=False)
    description=Column(Text)
    starts_at=Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at=Column(DateTime(timezone=True))
    refund_deadline=Column(DateTime(timezone=True), nullable=False)
    timezone=Column(String(50), nullable=False, default='Asia/Tehran')
    location=Column(String(200), nullable=False)
    capacity=Column(Integer, nullable=False)
    status=Column(Enum(EventStatus, native_enum=False), nullable=False, default=EventStatus.ACTIVE)
    created_by=Column(BigInteger, ForeignKey('users.telegram_id'))
    @property
    def date(self): return self.starts_at.strftime('%Y-%m-%d %H:%M') if self.starts_at else '-'
class EventChecker(Base):
    __tablename__='event_checkers'
    id=Column(Integer, primary_key=True)
    event_id=Column(Integer, ForeignKey('events.id'), nullable=False)
    user_id=Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
