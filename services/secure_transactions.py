import json, secrets, string
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.event import Event
from services.notification_service import schedule_event_reminders
from models.ticket import Order, Ticket, TicketType, PromoCode, PromoReservation
from models.advanced import AuditLog, FinancialLedger, RefundRequest
from models.enums import OrderStatus, TicketStatus, PromoReservationStatus, RefundStatus

UTC=lambda: datetime.now(timezone.utc)

def audit(session, actor_id, action, entity_type, entity_id, before=None, after=None, metadata=None):
    session.add(AuditLog(actor_id=actor_id, action=action, entity_type=entity_type, entity_id=str(entity_id), before_json=json.dumps(before,ensure_ascii=False,default=str) if before else None, after_json=json.dumps(after,ensure_ascii=False,default=str) if after else None, metadata_json=json.dumps(metadata,ensure_ascii=False,default=str) if metadata else None))

def _code(): return ''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(12))

async def reserve_order(session: AsyncSession, *, user_id:int,event_id:int,total_amount:int,total_quantity:int,cart_data:dict,promo_id:int|None,expires_hours:int=5):
    async with session.begin():
        result=await session.execute(update(Event).where(Event.id==event_id, Event.capacity>=total_quantity).values(capacity=Event.capacity-total_quantity).returning(Event.id))
        if result.scalar_one_or_none() is None: raise ValueError('ظرفیت کافی نیست.')
        order=Order(user_id=user_id,event_id=event_id,total_amount=total_amount,total_quantity=total_quantity,cart_data=json.dumps(cart_data,ensure_ascii=False),promo_code_id=promo_id,status=OrderStatus.AWAITING_PAYMENT,expires_at=UTC()+timedelta(hours=expires_hours))
        session.add(order); await session.flush()
        if promo_id:
            promo=(await session.execute(select(PromoCode).where(PromoCode.id==promo_id).with_for_update())).scalar_one_or_none()
            if not promo or not promo.is_active or (promo.max_uses is not None and promo.used_count+promo.reserved_count>=promo.max_uses): raise ValueError('کد تخفیف دیگر قابل استفاده نیست.')
            promo.reserved_count += 1
            session.add(PromoReservation(promo_code_id=promo.id,order_id=order.id,status=PromoReservationStatus.RESERVED))
        audit(session,user_id,'ORDER_RESERVED','order',order.id,after={'quantity':total_quantity,'amount':total_amount})
    await session.refresh(order); return order

async def attach_receipt(session:AsyncSession, *, order_id:int,user_id:int,file_id:str):
    async with session.begin():
        order=(await session.execute(select(Order).where(Order.id==order_id).with_for_update())).scalar_one_or_none()
        if not order or order.user_id!=user_id: raise PermissionError('این فاکتور متعلق به شما نیست.')
        if order.status!=OrderStatus.AWAITING_PAYMENT: raise ValueError('این فاکتور در وضعیت دریافت رسید نیست.')
        if order.expires_at<=UTC(): raise ValueError('مهلت این فاکتور تمام شده است.')
        order.receipt_file_id=file_id; order.status=OrderStatus.PENDING_APPROVAL
        audit(session,user_id,'RECEIPT_ATTACHED','order',order.id)
    return order

async def approve_order_atomic(session:AsyncSession, *, order_id:int,admin_id:int):
    tickets=[]
    async with session.begin():
        order=(await session.execute(select(Order).where(Order.id==order_id).with_for_update())).scalar_one_or_none()
        if not order or order.status!=OrderStatus.PENDING_APPROVAL: raise ValueError('فاکتور قابل تأیید نیست.')
        cart=json.loads(order.cart_data)
        for tt_id,item in cart.items():
            for owner in item['owners']:
                t=Ticket(order_id=order.id,user_id=order.user_id,event_id=order.event_id,ticket_type_id=int(tt_id),owner_name=owner,status=TicketStatus.ISSUED,tracking_code=_code())
                session.add(t); tickets.append(t)
        order.status=OrderStatus.APPROVED; order.approved_at=UTC(); order.approved_by=admin_id
        if order.promo_code_id:
            reservation=(await session.execute(select(PromoReservation).where(PromoReservation.order_id==order.id).with_for_update())).scalar_one_or_none()
            promo=(await session.execute(select(PromoCode).where(PromoCode.id==order.promo_code_id).with_for_update())).scalar_one()
            if reservation and reservation.status==PromoReservationStatus.RESERVED:
                reservation.status=PromoReservationStatus.CONSUMED; promo.reserved_count=max(0,promo.reserved_count-1); promo.used_count+=1
        session.add(FinancialLedger(order_id=order.id,entry_type='PAYMENT_APPROVED',amount=order.total_amount,actor_id=admin_id))
        event=await session.get(Event,order.event_id)
        await schedule_event_reminders(session,order.user_id,event)
        audit(session,admin_id,'ORDER_APPROVED','order',order.id)
    for t in tickets: await session.refresh(t)
    return order,tickets

async def release_order(session:AsyncSession, *, order_id:int,new_status:OrderStatus,actor_id:int):
    async with session.begin():
        order=(await session.execute(select(Order).where(Order.id==order_id).with_for_update())).scalar_one_or_none()
        if not order or order.status not in {OrderStatus.AWAITING_PAYMENT,OrderStatus.PENDING_APPROVAL}: return None
        order.status=new_status
        await session.execute(update(Event).where(Event.id==order.event_id).values(capacity=Event.capacity+order.total_quantity))
        if order.promo_code_id:
            reservation=(await session.execute(select(PromoReservation).where(PromoReservation.order_id==order.id).with_for_update())).scalar_one_or_none()
            promo=(await session.execute(select(PromoCode).where(PromoCode.id==order.promo_code_id).with_for_update())).scalar_one_or_none()
            if reservation and reservation.status==PromoReservationStatus.RESERVED:
                reservation.status=PromoReservationStatus.RELEASED
                if promo: promo.reserved_count=max(0,promo.reserved_count-1)
        audit(session,actor_id,f'ORDER_{new_status.value}','order',order.id)
    return order

async def create_refund_request(session:AsyncSession, *, ticket_id:int,user_id:int,payout_reference:str):
    digits=''.join(c for c in payout_reference if c.isdigit())
    if payout_reference!='WALLET' and len(digits)<4: raise ValueError('شماره کارت یا شبا معتبر نیست.')
    async with session.begin():
        ticket=(await session.execute(select(Ticket).where(Ticket.id==ticket_id).with_for_update())).scalar_one_or_none()
        if not ticket or ticket.user_id!=user_id: raise PermissionError('این بلیت متعلق به شما نیست.')
        if ticket.status!=TicketStatus.ISSUED: raise ValueError('این بلیت قابل استرداد نیست.')
        event=(await session.execute(select(Event).where(Event.id==ticket.event_id))).scalar_one()
        if UTC()>=event.refund_deadline: raise ValueError('مهلت قانونی استرداد این رویداد پایان یافته است.')
        exists=(await session.execute(select(RefundRequest).where(RefundRequest.ticket_id==ticket.id,RefundRequest.status==RefundStatus.PENDING))).scalar_one_or_none()
        if exists: raise ValueError('برای این بلیت درخواست باز وجود دارد.')
        order=await session.get(Order,ticket.order_id) if ticket.order_id else None
        amount=max(0,(order.total_amount//order.total_quantity) if order and order.total_quantity else (await session.get(TicketType,ticket.ticket_type_id)).price)
        req=RefundRequest(ticket_id=ticket.id,user_id=user_id,payout_reference='WALLET',payout_last4='----',amount=amount,status=RefundStatus.PENDING)
        session.add(req); ticket.status=TicketStatus.REFUND_PENDING; await session.flush(); audit(session,user_id,'REFUND_REQUESTED','refund',req.id)
    await session.refresh(req); return req,ticket
