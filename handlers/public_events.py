from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.database import AsyncSessionLocal
from services.event_service import (
    get_active_events,
    get_event_by_id,
    get_ticket_types_for_event,
)
from services.user_service import get_user
from models.enums import EventStatus, UserStatus


router = Router()


async def user_is_approved(user_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        user = await get_user(session, user_id)

    return bool(
        user
        and getattr(user, "status", None) in {"APPROVED", UserStatus.APPROVED}
    )


async def send_public_events_menu(
    target: types.Message,
    *,
    edit: bool = False,
) -> None:
    async with AsyncSessionLocal() as session:
        events = await get_active_events(session)

    builder = InlineKeyboardBuilder()

    if events:
        text = (
            "🎵 **رویدادهای فعال**\n\n"
            "برای مشاهده اطلاعات و خرید بلیت، "
            "رویداد موردنظر را انتخاب کنید."
        )

        for event in events:
            builder.button(
                text=f"🎟 {event.title}",
                callback_data=f"public_event_{event.id}",
            )

        builder.adjust(1)
    else:
        text = (
            "📭 در حال حاضر رویداد فعالی برای نمایش وجود ندارد."
        )

    if edit:
        await target.edit_text(
            text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown",
        )
    else:
        await target.answer(
            text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown",
        )


@router.message(F.text == "🎵 رویدادها")
async def show_public_events(message: types.Message) -> None:
    if not await user_is_approved(message.from_user.id):
        await message.answer(
            "⏳ برای مشاهده رویدادها، حساب شما باید توسط مدیریت تأیید شود."
        )
        return

    await send_public_events_menu(message)


@router.callback_query(F.data.in_({"public_events_list", "user_events_list"}))
async def public_events_list(callback: types.CallbackQuery) -> None:
    if not await user_is_approved(callback.from_user.id):
        await callback.answer(
            "حساب شما هنوز تأیید نشده است.",
            show_alert=True,
        )
        return

    await send_public_events_menu(
        callback.message,
        edit=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("public_event_"))
async def show_public_event_details(
    callback: types.CallbackQuery,
) -> None:
    if not await user_is_approved(callback.from_user.id):
        await callback.answer(
            "حساب شما هنوز تأیید نشده است.",
            show_alert=True,
        )
        return

    try:
        event_id = int(callback.data.split("_")[-1])
    except (TypeError, ValueError):
        await callback.answer(
            "شناسه رویداد نامعتبر است.",
            show_alert=True,
        )
        return

    async with AsyncSessionLocal() as session:
        event = await get_event_by_id(session, event_id)
        ticket_types = await get_ticket_types_for_event(
            session,
            event_id,
        )

    if not event:
        await callback.answer(
            "این رویداد پیدا نشد.",
            show_alert=True,
        )
        return

    if getattr(event, "status", None) not in {"ACTIVE", EventStatus.ACTIVE}:
        await callback.answer(
            "این رویداد دیگر فعال نیست.",
            show_alert=True,
        )
        return

    text = (
        f"✨ **{event.title}**\n\n"
        f"📝 {event.description or 'بدون توضیحات'}\n\n"
        f"📅 **زمان:** {event.date}\n"
        f"📍 **مکان:** {event.location}\n"
        f"🎫 **ظرفیت باقی‌مانده:** {event.capacity}\n"
    )

    if ticket_types:
        text += "\n💳 **انواع بلیت:**\n"

        for ticket_type in ticket_types:
            text += (
                f"• {ticket_type.name}: "
                f"{ticket_type.price:,} تومان\n"
            )
    else:
        text += (
            "\n⚠️ هنوز نوع بلیت و قیمت برای این رویداد تعریف نشده است."
        )

    keyboard_rows = []

    if ticket_types and event.capacity > 0:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text="🎫 خرید / رزرو بلیت",
                    callback_data=f"buy_{event.id}",
                )
            ]
        )

    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="🔙 بازگشت به رویدادها",
                callback_data="public_events_list",
            )
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard_rows
        ),
        parse_mode="Markdown",
    )
    await callback.answer()