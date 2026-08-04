import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from database.database import AsyncSessionLocal
from filters.admin import AdminFilter
from models.enums import EventStatus
from services.event_service import (
    add_ticket_type,
    create_event,
    create_promo_code,
    get_active_events,
    get_event_by_id,
    get_event_stats,
    get_ticket_types_for_event,
    update_event_capacity,
)
from states.admin_event import EventCreate, EventEdit, PromoCreate, TicketTypeCreate

logger = logging.getLogger(__name__)
router = Router(name="admin_events")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _event_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎫 انواع بلیت", callback_data=f"admin_ticket_types_{event_id}")],
            [InlineKeyboardButton(text="➕ افزودن نوع بلیت", callback_data=f"admin_add_ticket_type_{event_id}")],
            [InlineKeyboardButton(text="🏷 ساخت کد تخفیف", callback_data=f"admin_add_promo_{event_id}")],
            [InlineKeyboardButton(text="📊 آمار", callback_data=f"admin_event_stats_{event_id}")],
            [InlineKeyboardButton(text="👥 تغییر ظرفیت", callback_data=f"admin_capacity_{event_id}")],
            [InlineKeyboardButton(text="⛔ بستن رویداد", callback_data=f"admin_close_event_{event_id}")],
            [InlineKeyboardButton(text="🔙 فهرست رویدادها", callback_data="admin_events_list")],
        ]
    )


async def _send_events(target: types.Message, *, edit: bool = False) -> None:
    async with AsyncSessionLocal() as session:
        events = await get_active_events(session)

    builder = InlineKeyboardBuilder()
    for event in events:
        builder.button(text=f"🎟 {event.title}", callback_data=f"admin_event_{event.id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="➕ ایجاد رویداد جدید", callback_data="admin_create_event"))

    text = "🎵 **مدیریت رویدادها**\n\nرویداد موردنظر را انتخاب کنید." if events else "📭 رویداد فعالی ثبت نشده است."
    if edit:
        await target.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        await target.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


@router.message(Command("cancel"))
async def cancel_flow(message: types.Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("عملیات فعالی برای لغو وجود ندارد.")
        return
    await state.clear()
    await message.answer("✅ عملیات جاری لغو شد.")


@router.message(F.text == "🎵 رویدادها")
async def admin_events(message: types.Message) -> None:
    await _send_events(message)


@router.callback_query(F.data == "admin_events_list")
async def admin_events_callback(callback: types.CallbackQuery) -> None:
    await _send_events(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "admin_create_event")
async def begin_create_event(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(EventCreate.waiting_for_title)
    await callback.message.edit_text("📌 عنوان رویداد را وارد کنید:")
    await callback.answer()


@router.message(EventCreate.waiting_for_title, F.text)
async def create_title(message: types.Message, state: FSMContext) -> None:
    title = message.text.strip()
    if len(title) < 3 or len(title) > 100:
        await message.answer("❌ عنوان باید بین ۳ تا ۱۰۰ کاراکتر باشد.")
        return
    await state.update_data(title=title)
    await state.set_state(EventCreate.waiting_for_description)
    await message.answer("📝 توضیحات رویداد را وارد کنید:")


@router.message(EventCreate.waiting_for_description, F.text)
async def create_description(message: types.Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip())
    await state.set_state(EventCreate.waiting_for_date)
    await message.answer("📅 تاریخ و ساعت شروع را به فرمت `2027-03-02 14:00` وارد کنید:", parse_mode="Markdown")


@router.message(EventCreate.waiting_for_date, F.text)
async def create_date(message: types.Message, state: FSMContext) -> None:
    value = message.text.strip()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(settings.event_timezone))
    except ValueError:
        await message.answer("❌ فرمت نامعتبر است. نمونه صحیح: `2027-03-02 14:00`", parse_mode="Markdown")
        return
    if parsed <= datetime.now(ZoneInfo(settings.event_timezone)):
        await message.answer("❌ زمان رویداد باید در آینده باشد.")
        return
    await state.update_data(date=value)
    await state.set_state(EventCreate.waiting_for_location)
    await message.answer("📍 مکان برگزاری را وارد کنید:")


@router.message(EventCreate.waiting_for_location, F.text)
async def create_location(message: types.Message, state: FSMContext) -> None:
    location = message.text.strip()
    if len(location) < 2 or len(location) > 200:
        await message.answer("❌ مکان باید بین ۲ تا ۲۰۰ کاراکتر باشد.")
        return
    await state.update_data(location=location)
    await state.set_state(EventCreate.waiting_for_capacity)
    await message.answer("👥 ظرفیت رویداد را فقط به‌صورت عدد وارد کنید:")


@router.message(EventCreate.waiting_for_capacity, F.text)
async def create_capacity(message: types.Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(",", "")
    if not raw.isdigit() or not 1 <= int(raw) <= 1_000_000:
        await message.answer("❌ ظرفیت باید عددی بین ۱ تا ۱٬۰۰۰٬۰۰۰ باشد.")
        return
    data = await state.get_data()
    try:
        async with AsyncSessionLocal() as session:
            event = await create_event(
                session,
                title=data["title"],
                description=data["description"],
                date=data["date"],
                location=data["location"],
                capacity=int(raw),
                admin_id=message.from_user.id,
            )
    except Exception:
        logger.exception("event creation failed")
        await message.answer("❌ ثبت رویداد با خطای داخلی مواجه شد. لاگ سرور را بررسی کنید.")
        return
    await state.clear()
    await message.answer(
        f"✅ رویداد با موفقیت ثبت شد.\n\n🆔 `{event.id}`\n📌 {event.title}\n👥 ظرفیت: {event.capacity:,}",
        reply_markup=_event_keyboard(event.id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("admin_event_"))
async def event_details(callback: types.CallbackQuery) -> None:
    event_id = int(callback.data.rsplit("_", 1)[1])
    async with AsyncSessionLocal() as session:
        event = await get_event_by_id(session, event_id)
    if not event:
        await callback.answer("رویداد پیدا نشد.", show_alert=True)
        return
    await callback.message.edit_text(
        f"🎟 **{event.title}**\n\n📝 {event.description or '-'}\n📅 {event.date}\n📍 {event.location}\n👥 ظرفیت باقی‌مانده: {event.capacity:,}\n📊 وضعیت: {event.status}",
        reply_markup=_event_keyboard(event.id),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ticket_types_"))
async def ticket_types(callback: types.CallbackQuery) -> None:
    event_id = int(callback.data.rsplit("_", 1)[1])
    async with AsyncSessionLocal() as session:
        rows = await get_ticket_types_for_event(session, event_id)
    text = "🎫 **انواع بلیت**\n\n" + ("\n".join(f"• {r.name}: {r.price:,} تومان" for r in rows) if rows else "هنوز نوع بلیتی تعریف نشده است.")
    await callback.message.edit_text(text, reply_markup=_event_keyboard(event_id), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_add_ticket_type_"))
async def begin_ticket_type(callback: types.CallbackQuery, state: FSMContext) -> None:
    event_id = int(callback.data.rsplit("_", 1)[1])
    await state.clear(); await state.update_data(event_id=event_id)
    await state.set_state(TicketTypeCreate.waiting_for_name)
    await callback.message.edit_text("🎫 نام نوع بلیت را وارد کنید؛ مانند عادی یا VIP:")
    await callback.answer()


@router.message(TicketTypeCreate.waiting_for_name, F.text)
async def ticket_type_name(message: types.Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not 2 <= len(name) <= 100:
        await message.answer("❌ نام نوع بلیت نامعتبر است.")
        return
    await state.update_data(name=name)
    await state.set_state(TicketTypeCreate.waiting_for_price)
    await message.answer("💰 قیمت بلیت را به تومان و فقط عدد وارد کنید:")


@router.message(TicketTypeCreate.waiting_for_price, F.text)
async def ticket_type_price(message: types.Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(",", "")
    if not raw.isdigit() or int(raw) < 0:
        await message.answer("❌ قیمت نامعتبر است.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        ticket_type = await add_ticket_type(session, data["event_id"], data["name"], int(raw))
    await state.clear()
    await message.answer(f"✅ نوع بلیت «{ticket_type.name}» با قیمت {ticket_type.price:,} تومان ثبت شد.", reply_markup=_event_keyboard(data["event_id"]))


@router.callback_query(F.data.startswith("admin_capacity_"))
async def begin_capacity(callback: types.CallbackQuery, state: FSMContext) -> None:
    event_id = int(callback.data.rsplit("_", 1)[1])
    await state.clear(); await state.update_data(event_id=event_id)
    await state.set_state(EventEdit.waiting_for_new_capacity)
    await callback.message.edit_text("👥 ظرفیت جدید را وارد کنید:")
    await callback.answer()


@router.message(EventEdit.waiting_for_new_capacity, F.text)
async def save_capacity(message: types.Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(",", "")
    if not raw.isdigit() or int(raw) < 0:
        await message.answer("❌ ظرفیت نامعتبر است.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        ok = await update_event_capacity(session, data["event_id"], int(raw))
    await state.clear()
    await message.answer("✅ ظرفیت به‌روزرسانی شد." if ok else "❌ رویداد پیدا نشد.", reply_markup=_event_keyboard(data["event_id"]))


@router.callback_query(F.data.startswith("admin_add_promo_"))
async def begin_promo(callback: types.CallbackQuery, state: FSMContext) -> None:
    event_id = int(callback.data.rsplit("_", 1)[1])
    await state.clear(); await state.update_data(event_id=event_id)
    await state.set_state(PromoCreate.waiting_for_code)
    await callback.message.edit_text("🏷 کد تخفیف را وارد کنید:")
    await callback.answer()


@router.message(PromoCreate.waiting_for_code, F.text)
async def promo_code(message: types.Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    if not 3 <= len(code) <= 50 or not code.replace("-", "").isalnum():
        await message.answer("❌ کد تخفیف نامعتبر است.")
        return
    await state.update_data(code=code)
    await state.set_state(PromoCreate.waiting_for_discount)
    await message.answer("درصد تخفیف را بین ۱ تا ۱۰۰ وارد کنید:")


@router.message(PromoCreate.waiting_for_discount, F.text)
async def promo_discount(message: types.Message, state: FSMContext) -> None:
    raw = message.text.strip()
    try: value = float(raw)
    except ValueError: value = 0
    if not 0 < value <= 100:
        await message.answer("❌ درصد باید بین ۱ تا ۱۰۰ باشد.")
        return
    await state.update_data(discount=value)
    await state.set_state(PromoCreate.waiting_for_uses)
    await message.answer("حداکثر تعداد استفاده را وارد کنید:")


@router.message(PromoCreate.waiting_for_uses, F.text)
async def promo_uses(message: types.Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit() or int(raw) < 1:
        await message.answer("❌ تعداد استفاده نامعتبر است.")
        return
    data = await state.get_data()
    try:
        async with AsyncSessionLocal() as session:
            promo = await create_promo_code(session, data["event_id"], data["code"], data["discount"], int(raw))
    except Exception:
        logger.exception("promo creation failed")
        await message.answer("❌ ثبت کد تخفیف ناموفق بود؛ احتمالاً کد تکراری است.")
        return
    await state.clear()
    await message.answer(f"✅ کد `{promo.code}` ثبت شد.", reply_markup=_event_keyboard(data["event_id"]), parse_mode="Markdown")


@router.callback_query(F.data.startswith("admin_event_stats_"))
async def event_stats(callback: types.CallbackQuery) -> None:
    event_id = int(callback.data.rsplit("_", 1)[1])
    async with AsyncSessionLocal() as session:
        stats = await get_event_stats(session, event_id)
    await callback.message.edit_text(
        f"📊 **آمار رویداد**\n\n✅ فروش قطعی: {stats['sold']}\n⏳ رزرو موقت: {stats['reserved']}\n🎁 بلیت اهدایی: {stats['comps']}\n⭐ مهمان ویژه: {stats['vips']}",
        reply_markup=_event_keyboard(event_id), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_close_event_"))
async def close_event(callback: types.CallbackQuery) -> None:
    event_id = int(callback.data.rsplit("_", 1)[1])
    async with AsyncSessionLocal() as session:
        event = await get_event_by_id(session, event_id)
        if not event:
            await callback.answer("رویداد پیدا نشد.", show_alert=True); return
        event.status = EventStatus.CLOSED
        await session.commit()
    await callback.message.edit_text("✅ رویداد بسته شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 فهرست", callback_data="admin_events_list")]]))
    await callback.answer()
