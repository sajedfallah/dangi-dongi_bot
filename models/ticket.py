from sqlalchemy import Column,Integer,String,BigInteger,ForeignKey,Text,DateTime,Float,Enum,UniqueConstraint
from .base import Base
from .enums import OrderStatus,TicketStatus,PromoReservationStatus
class TicketType(Base):
    __tablename__='ticket_types'; id=Column(Integer,primary_key=True); event_id=Column(Integer,ForeignKey('events.id'),nullable=False); name=Column(String(100),nullable=False); price=Column(Integer,nullable=False)
class PromoCode(Base):
    __tablename__='promo_codes'; id=Column(Integer,primary_key=True); event_id=Column(Integer,ForeignKey('events.id')); code=Column(String(50),unique=True,nullable=False,index=True); discount_percent=Column(Float,nullable=False); max_uses=Column(Integer); used_count=Column(Integer,nullable=False,default=0); reserved_count=Column(Integer,nullable=False,default=0); is_active=Column(Integer,nullable=False,default=1)
class PromoReservation(Base):
    __tablename__='promo_reservations'; __table_args__=(UniqueConstraint('order_id',name='uq_promo_reservation_order'),)
    id=Column(Integer,primary_key=True); promo_code_id=Column(Integer,ForeignKey('promo_codes.id'),nullable=False); order_id=Column(Integer,ForeignKey('orders.id'),nullable=False); status=Column(Enum(PromoReservationStatus,native_enum=False),nullable=False,default=PromoReservationStatus.RESERVED)
class VIPGuest(Base):
    __tablename__='vip_guests'; id=Column(Integer,primary_key=True); event_id=Column(Integer,ForeignKey('events.id'),nullable=False); guest_name=Column(String(100),nullable=False); guest_role=Column(String(50)); added_by=Column(BigInteger,ForeignKey('users.telegram_id'),nullable=False); status=Column(String(20),default='PENDING')
class Order(Base):
    __tablename__='orders'; id=Column(Integer,primary_key=True); user_id=Column(BigInteger,ForeignKey('users.telegram_id'),nullable=False,index=True); event_id=Column(Integer,ForeignKey('events.id'),nullable=False,index=True); total_amount=Column(Integer,nullable=False); total_quantity=Column(Integer,nullable=False); receipt_file_id=Column(String(255)); cart_data=Column(Text,nullable=False); promo_code_id=Column(Integer,ForeignKey('promo_codes.id')); status=Column(Enum(OrderStatus,native_enum=False),nullable=False,default=OrderStatus.AWAITING_PAYMENT,index=True); expires_at=Column(DateTime(timezone=True),nullable=False,index=True); approved_at=Column(DateTime(timezone=True)); approved_by=Column(BigInteger)
class Ticket(Base):
    __tablename__='tickets'; id=Column(Integer,primary_key=True); order_id=Column(Integer,ForeignKey('orders.id'),index=True); user_id=Column(BigInteger,ForeignKey('users.telegram_id'),index=True); event_id=Column(Integer,ForeignKey('events.id'),nullable=False,index=True); ticket_type_id=Column(Integer,ForeignKey('ticket_types.id')); owner_name=Column(String(100),nullable=False); status=Column(Enum(TicketStatus,native_enum=False),nullable=False,default=TicketStatus.RESERVED,index=True); tracking_code=Column(String(20),unique=True,nullable=False,index=True); is_complimentary=Column(Integer,default=0)
