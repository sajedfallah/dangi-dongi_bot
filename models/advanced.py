from sqlalchemy import Column,Integer,String,Text,BigInteger,ForeignKey,DateTime,Enum,UniqueConstraint
from .base import Base
from .enums import SupportStatus, RefundStatus
class SupportTicket(Base):
    __tablename__='support_tickets'; id=Column(Integer,primary_key=True); user_id=Column(BigInteger,ForeignKey('users.telegram_id'),nullable=False,index=True); status=Column(Enum(SupportStatus,native_enum=False),nullable=False,default=SupportStatus.OPEN)
class SupportMessage(Base):
    __tablename__='support_messages'; id=Column(Integer,primary_key=True); ticket_id=Column(Integer,ForeignKey('support_tickets.id'),nullable=False,index=True); sender_id=Column(BigInteger,nullable=False); text=Column(Text,nullable=False)
class RefundRequest(Base):
    __tablename__='refund_requests'; __table_args__=(UniqueConstraint('ticket_id','status',name='uq_open_refund_per_ticket'),)
    id=Column(Integer,primary_key=True); ticket_id=Column(Integer,ForeignKey('tickets.id'),nullable=False,index=True); user_id=Column(BigInteger,ForeignKey('users.telegram_id'),nullable=False,index=True); payout_reference=Column(String(512),nullable=False); payout_last4=Column(String(4),nullable=False); status=Column(Enum(RefundStatus,native_enum=False),nullable=False,default=RefundStatus.PENDING); amount=Column(Integer,nullable=False,default=0); reviewed_by=Column(BigInteger); reviewed_at=Column(DateTime(timezone=True)); admin_note=Column(Text)
class AuditLog(Base):
    __tablename__='audit_logs'; id=Column(Integer,primary_key=True); actor_id=Column(BigInteger,index=True); action=Column(String(100),nullable=False,index=True); entity_type=Column(String(50),nullable=False); entity_id=Column(String(64),nullable=False); before_json=Column(Text); after_json=Column(Text); metadata_json=Column(Text)
class FinancialLedger(Base):
    __tablename__='financial_ledger'; id=Column(Integer,primary_key=True); order_id=Column(Integer,ForeignKey('orders.id'),index=True); refund_request_id=Column(Integer,ForeignKey('refund_requests.id'),index=True); entry_type=Column(String(30),nullable=False); amount=Column(Integer,nullable=False); actor_id=Column(BigInteger); note=Column(Text)
