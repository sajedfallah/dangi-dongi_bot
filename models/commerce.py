from sqlalchemy import Column, Integer, BigInteger, String, Text, ForeignKey, DateTime, Enum, UniqueConstraint, Boolean
from .base import Base
from .enums import WalletEntryType, WithdrawalStatus, WaitlistStatus, NotificationStatus

class Wallet(Base):
    __tablename__='wallets'
    user_id=Column(BigInteger,ForeignKey('users.telegram_id'),primary_key=True)
    available_balance=Column(Integer,nullable=False,default=0)
    locked_balance=Column(Integer,nullable=False,default=0)

class WalletTransaction(Base):
    __tablename__='wallet_transactions'
    id=Column(Integer,primary_key=True)
    user_id=Column(BigInteger,ForeignKey('users.telegram_id'),nullable=False,index=True)
    entry_type=Column(Enum(WalletEntryType,native_enum=False),nullable=False,index=True)
    amount=Column(Integer,nullable=False)
    balance_after=Column(Integer,nullable=False)
    reference_type=Column(String(50)); reference_id=Column(String(64)); note=Column(Text)
    actor_id=Column(BigInteger)

class WithdrawalRequest(Base):
    __tablename__='withdrawal_requests'
    id=Column(Integer,primary_key=True)
    user_id=Column(BigInteger,ForeignKey('users.telegram_id'),nullable=False,index=True)
    amount=Column(Integer,nullable=False)
    payout_reference=Column(String(512),nullable=False)
    payout_last4=Column(String(4),nullable=False)
    status=Column(Enum(WithdrawalStatus,native_enum=False),nullable=False,default=WithdrawalStatus.PENDING,index=True)
    receipt_file_id=Column(String(255)); reviewed_by=Column(BigInteger); reviewed_at=Column(DateTime(timezone=True)); admin_note=Column(Text)

class WaitlistEntry(Base):
    __tablename__='waitlist_entries'
    __table_args__=(UniqueConstraint('event_id','user_id',name='uq_waitlist_event_user'),)
    id=Column(Integer,primary_key=True); event_id=Column(Integer,ForeignKey('events.id'),nullable=False,index=True); user_id=Column(BigInteger,ForeignKey('users.telegram_id'),nullable=False,index=True)
    quantity=Column(Integer,nullable=False,default=1); status=Column(Enum(WaitlistStatus,native_enum=False),nullable=False,default=WaitlistStatus.WAITING,index=True)
    notified_at=Column(DateTime(timezone=True)); expires_at=Column(DateTime(timezone=True))

class ScheduledNotification(Base):
    __tablename__='scheduled_notifications'
    id=Column(Integer,primary_key=True); user_id=Column(BigInteger,ForeignKey('users.telegram_id'),nullable=False,index=True); event_id=Column(Integer,ForeignKey('events.id'),index=True)
    send_at=Column(DateTime(timezone=True),nullable=False,index=True); text=Column(Text,nullable=False); status=Column(Enum(NotificationStatus,native_enum=False),nullable=False,default=NotificationStatus.PENDING,index=True)
    attempts=Column(Integer,nullable=False,default=0); last_error=Column(Text)
