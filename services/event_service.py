from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from models.event import Event
from models.ticket import TicketType, Ticket, Order, PromoCode, VIPGuest
import random
import string
import json
import datetime
from zoneinfo import ZoneInfo
from config import settings

# --- Event Services ---
async def create_event(session: AsyncSession, title: str, description: str, date: str, location: str, capacity: int, admin_id: int):
    try:
        naive = datetime.datetime.strptime(date.strip(), '%Y-%m-%d %H:%M')
    except ValueError as exc:
        raise ValueError('فرمت تاریخ باید YYYY-MM-DD HH:MM باشد.') from exc
    starts_at = naive.replace(tzinfo=ZoneInfo(settings.event_timezone))
    refund_deadline = starts_at - datetime.timedelta(hours=settings.default_refund_cutoff_hours)
    new_event = Event(title=title, description=description, starts_at=starts_at, refund_deadline=refund_deadline, timezone=settings.event_timezone, location=location, capacity=capacity, created_by=admin_id)
    session.add(new_event)
    await session.commit()
    await session.refresh(new_event)
    return new_event

async def get_active_events(session: AsyncSession):
    result = await session.execute(select(Event).where(Event.status == "ACTIVE"))
    return result.scalars().all()

async def get_event_by_id(session: AsyncSession, event_id: int):
    result = await session.execute(select(Event).where(Event.id == event_id))
    return result.scalar_one_or_none()

async def update_event_capacity(session: AsyncSession, event_id: int, new_capacity: int):
    event = await get_event_by_id(session, event_id)
    if event:
        event.capacity = new_capacity
        await session.commit()
        return True
    return False

async def get_event_stats(session: AsyncSession, event_id: int):
    approved_orders = await session.execute(select(func.sum(Order.total_quantity)).where(Order.event_id == event_id, Order.status == "APPROVED"))
    sold = approved_orders.scalar() or 0
    
    pending_orders = await session.execute(
        select(func.sum(Order.total_quantity)).where(Order.event_id == event_id, Order.status.in_(["AWAITING_PAYMENT", "PENDING_APPROVAL"]))
    )
    reserved = pending_orders.scalar() or 0
    
    comp_tickets = await session.execute(select(func.count(Ticket.id)).where(Ticket.event_id == event_id, Ticket.is_complimentary == 1))
    comps = comp_tickets.scalar() or 0
    
    vip_guests = await session.execute(select(func.count(VIPGuest.id)).where(VIPGuest.event_id == event_id))
    vips = vip_guests.scalar() or 0
    
    return {"sold": sold, "reserved": reserved, "comps": comps, "vips": vips}

async def decrease_event_capacity(session: AsyncSession, event_id: int, amount: int = 1):
    event = await get_event_by_id(session, event_id)
    if event and event.capacity >= amount:
        event.capacity -= amount
        await session.commit()
        return True
    return False

async def increase_event_capacity(session: AsyncSession, event_id: int, amount: int):
    event = await get_event_by_id(session, event_id)
    if event:
        event.capacity += amount
        await session.commit()
        return True
    return False

# --- Ticket Services ---
async def add_ticket_type(session: AsyncSession, event_id: int, name: str, price: int):
    new_type = TicketType(event_id=event_id, name=name, price=price)
    session.add(new_type)
    await session.commit()
    return new_type

async def get_ticket_types_for_event(session: AsyncSession, event_id: int):
    result = await session.execute(select(TicketType).where(TicketType.event_id == event_id))
    return result.scalars().all()

async def get_ticket_type_by_id(session: AsyncSession, tt_id: int):
    result = await session.execute(select(TicketType).where(TicketType.id == tt_id))
    return result.scalar_one_or_none()

async def create_user_ticket(session: AsyncSession, user_id: int, event_id: int, ticket_type_id: int, owner_name: str, is_comp: int = 0):
    tracking_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    new_ticket = Ticket(user_id=user_id, event_id=event_id, ticket_type_id=ticket_type_id, tracking_code=tracking_code, owner_name=owner_name, status="ISSUED", is_complimentary=is_comp)
    session.add(new_ticket)
    await session.commit()
    await session.refresh(new_ticket)
    return new_ticket

async def verify_and_consume_ticket(session: AsyncSession, tracking_code: str):
    result = await session.execute(select(Ticket).where(Ticket.tracking_code == tracking_code))
    ticket = result.scalar_one_or_none()
    if not ticket: return None, "not_found"
    if ticket.status == "USED": return ticket, "already_used"
    if ticket.status == "ISSUED":
        ticket.status = "USED"
        await session.commit()
        return ticket, "success"
    return ticket, "invalid_status"

# --- Order Services ---
async def create_order(session: AsyncSession, user_id: int, event_id: int, total_amount: int, total_qty: int, cart_data: dict, promo_id: int = None, expires_in_hours: int = 5):
    expires_at = datetime.datetime.now() + datetime.timedelta(hours=expires_in_hours)
    new_order = Order(
        user_id=user_id, event_id=event_id, total_amount=total_amount, 
        total_quantity=total_qty, cart_data=json.dumps(cart_data), 
        promo_code_id=promo_id, status="AWAITING_PAYMENT", expires_at=expires_at
    )
    session.add(new_order)
    await session.commit()
    await session.refresh(new_order)
    return new_order

async def get_order_by_id(session: AsyncSession, order_id: int):
    result = await session.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one_or_none()

# --- Promo & VIP Services ---
async def create_promo_code(session: AsyncSession, event_id: int, code: str, discount: float, max_uses: int):
    promo = PromoCode(event_id=event_id, code=code.upper(), discount_percent=discount, max_uses=max_uses)
    session.add(promo)
    await session.commit()
    return promo

async def get_promo_by_code(session: AsyncSession, code: str, event_id: int):
    result = await session.execute(
        select(PromoCode).where(PromoCode.code == code.upper(), PromoCode.event_id.in_([event_id, None]))
    )
    promo = result.scalar_one_or_none()
    if not promo: return None, "کد تخفیف نامعتبر است."
    if promo.max_uses and promo.used_count >= promo.max_uses: return None, "ظرفیت این کد تخفیف به پایان رسیده است."
    return promo, "success"

async def create_vip_guest(session: AsyncSession, event_id: int, guest_name: str, role: str, admin_id: int):
    guest = VIPGuest(event_id=event_id, guest_name=guest_name, guest_role=role, added_by=admin_id)
    session.add(guest)
    await session.commit()
    return guest
    
async def get_vip_guests_for_event(session: AsyncSession, event_id: int):
    result = await session.execute(select(VIPGuest).where(VIPGuest.event_id == event_id))
    return result.scalars().all()