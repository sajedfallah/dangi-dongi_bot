import asyncio
from decimal import Decimal, InvalidOperation

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

from app.bot.security import make_join_payload, parse_join_payload
from app.core.config import settings


class CreateGroupFlow(StatesGroup):
    waiting_name = State()


class ExpenseFlow(StatesGroup):
    waiting_amount = State()
    waiting_title = State()
    waiting_payer = State()
    waiting_participants = State()


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ ساخت حساب جدید"), KeyboardButton(text="📂 حساب‌های من")],
        [KeyboardButton(text="❓ راهنما")],
    ],
    resize_keyboard=True,
)


def api_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.api_base_url, timeout=15)


def parse_amount(value: str) -> Decimal:
    digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    cleaned = value.translate(digits).strip().replace(",", "").replace("٬", "").replace(" ", "")
    cleaned = cleaned.replace("تومان", "").replace("تومن", "").strip()
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
    if amount <= 0:
        raise ValueError("amount must be positive")
    return amount


def fmt_amount(value) -> str:
    amount = Decimal(str(value))
    return f"{int(amount):,}" if amount == amount.to_integral_value() else f"{amount:,.2f}"


async def ensure_user(telegram_user) -> dict:
    async with api_client() as client:
        response = await client.post(
            "/api/v1/users",
            json={
                "telegram_id": telegram_user.id,
                "display_name": telegram_user.full_name or str(telegram_user.id),
            },
        )
        response.raise_for_status()
        return response.json()


async def get_group(group_id: int) -> dict:
    async with api_client() as client:
        response = await client.get(f"/api/v1/groups/{group_id}")
        response.raise_for_status()
        return response.json()


async def get_members(group_id: int) -> list[dict]:
    async with api_client() as client:
        response = await client.get(f"/api/v1/groups/{group_id}/members")
        response.raise_for_status()
        return response.json()


async def has_group_access(user_id: int, group_id: int) -> bool:
    async with api_client() as client:
        response = await client.get(f"/api/v1/users/{user_id}/groups")
        response.raise_for_status()
        return any(group["id"] == group_id for group in response.json())


def group_menu(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 ثبت هزینه", callback_data=f"expense:new:{group_id}")],
        [
            InlineKeyboardButton(text="📊 وضعیت حساب", callback_data=f"balance:{group_id}"),
            InlineKeyboardButton(text="💳 تسویه", callback_data=f"plan:{group_id}"),
        ],
        [
            InlineKeyboardButton(text="📜 تاریخچه", callback_data=f"history:{group_id}"),
            InlineKeyboardButton(text="👥 اعضا", callback_data=f"members:{group_id}"),
        ],
        [InlineKeyboardButton(text="🔗 دعوت عضو", callback_data=f"invite:{group_id}")],
        [InlineKeyboardButton(text="⬅️ حساب‌های من", callback_data="groups:list")],
    ])


def participant_keyboard(members: list[dict], selected: set[int]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"{'✅' if member['user_id'] in selected else '⬜'} {member['display_name']}",
        callback_data=f"expense:participant:{member['user_id']}",
    )] for member in members]
    rows += [
        [InlineKeyboardButton(text="✅ ثبت هزینه", callback_data="expense:participants_done")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_groups(message: Message, user_id: int):
    async with api_client() as client:
        response = await client.get(f"/api/v1/users/{user_id}/groups")
        response.raise_for_status()
        groups = response.json()
    if not groups:
        await message.answer("هنوز حسابی نداری. با «➕ ساخت حساب جدید» شروع کن.", reply_markup=main_keyboard)
        return
    await message.answer(
        "📂 حساب‌های تو:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💼 {group['name']}", callback_data=f"group:{group['id']}")]
            for group in groups
        ]),
    )


async def authorize(callback: CallbackQuery, group_id: int) -> dict | None:
    user = await ensure_user(callback.from_user)
    if not await has_group_access(user["id"], group_id):
        await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
        return None
    return user


async def run_bot():
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    if settings.env != "development" and settings.app_secret_key == "change-me-in-production":
        raise RuntimeError("APP_SECRET_KEY must be configured outside development")

    bot = Bot(settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart(deep_link=True))
    async def start_with_invite(message: Message, command: CommandObject):
        user = await ensure_user(message.from_user)
        group_id = parse_join_payload(command.args or "")
        if group_id is None:
            await message.answer("این لینک دعوت معتبر نیست.", reply_markup=main_keyboard)
            return
        try:
            group = await get_group(group_id)
            async with api_client() as client:
                response = await client.post(f"/api/v1/groups/{group_id}/members", json={"user_id": user["id"]})
                response.raise_for_status()
            await message.answer(f"✅ به حساب «{group['name']}» اضافه شدی.", reply_markup=group_menu(group_id))
        except httpx.HTTPError:
            await message.answer("حساب این دعوت دیگر در دسترس نیست.", reply_markup=main_keyboard)

    @dp.message(CommandStart())
    async def start(message: Message):
        await ensure_user(message.from_user)
        await message.answer(
            "سلام 👋\nخرج‌های مشترک و دونگ‌ها رو اینجا بدون حساب‌وکتاب دستی مدیریت کن.",
            reply_markup=main_keyboard,
        )

    @dp.message(Command("cancel"))
    async def cancel(message: Message, state: FSMContext):
        await state.clear()
        await message.answer("عملیات لغو شد.", reply_markup=main_keyboard)

    @dp.callback_query(F.data == "flow:cancel")
    async def cancel_button(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer("لغو شد")
        await callback.message.answer("عملیات لغو شد.", reply_markup=main_keyboard)

    @dp.message(F.text == "➕ ساخت حساب جدید")
    async def create_group_start(message: Message, state: FSMContext):
        await state.clear()
        await state.set_state(CreateGroupFlow.waiting_name)
        await message.answer("اسم حساب رو وارد کن.\nمثال: سفر شمال\n\nلغو: /cancel")

    @dp.message(CreateGroupFlow.waiting_name)
    async def create_group_finish(message: Message, state: FSMContext):
        name = (message.text or "").strip()
        if not name:
            await message.answer("اسم حساب نمی‌تونه خالی باشه.")
            return
        user = await ensure_user(message.from_user)
        async with api_client() as client:
            response = await client.post("/api/v1/groups", json={
                "name": name[:120], "owner_user_id": user["id"], "currency": "IRT"
            })
            response.raise_for_status()
            group = response.json()
        await state.clear()
        await message.answer(
            f"✅ حساب «{group['name']}» ساخته شد.\nدوستات رو دعوت کن یا اولین هزینه رو ثبت کن.",
            reply_markup=group_menu(group["id"]),
        )

    @dp.message(F.text == "📂 حساب‌های من")
    async def groups_message(message: Message):
        user = await ensure_user(message.from_user)
        await show_groups(message, user["id"])

    @dp.callback_query(F.data == "groups:list")
    async def groups_callback(callback: CallbackQuery):
        user = await ensure_user(callback.from_user)
        await callback.answer()
        await show_groups(callback.message, user["id"])

    @dp.callback_query(F.data.startswith("group:"))
    async def open_group(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        group = await get_group(group_id)
        await callback.answer()
        await callback.message.answer(f"💼 {group['name']}\nچه کاری می‌خوای انجام بدی؟", reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("invite:"))
    async def invite(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        group = await get_group(group_id)
        me = await bot.get_me()
        link = f"https://t.me/{me.username}?start={make_join_payload(group_id)}"
        await callback.answer()
        await callback.message.answer(
            f"🔗 لینک امن دعوت «{group['name']}»:\n{link}\n\nاین لینک رو برای اعضای همین حساب بفرست."
        )

    @dp.callback_query(F.data.startswith("members:"))
    async def members(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        items = await get_members(group_id)
        text = "👥 اعضای حساب:\n\n" + "\n".join(
            f"• {item['display_name']}{' 👑' if item['role'] == 'owner' else ''}" for item in items
        )
        await callback.answer()
        await callback.message.answer(text, reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("expense:new:"))
    async def expense_start(callback: CallbackQuery, state: FSMContext):
        group_id = int(callback.data.split(":")[2])
        if not await authorize(callback, group_id):
            return
        await state.clear()
        await state.update_data(group_id=group_id)
        await state.set_state(ExpenseFlow.waiting_amount)
        await callback.answer()
        await callback.message.answer("💰 مبلغ هزینه رو به تومان وارد کن.\nمثال: 1,250,000\n\nلغو: /cancel")

    @dp.message(ExpenseFlow.waiting_amount)
    async def expense_amount(message: Message, state: FSMContext):
        try:
            amount = parse_amount(message.text or "")
        except ValueError:
            await message.answer("مبلغ معتبر نیست. مثال: 750000")
            return
        await state.update_data(amount=str(amount))
        await state.set_state(ExpenseFlow.waiting_title)
        await message.answer("📝 این هزینه بابت چی بوده؟\nمثال: شام، بنزین، هتل")

    @dp.message(ExpenseFlow.waiting_title)
    async def expense_title(message: Message, state: FSMContext):
        title = (message.text or "").strip()
        if not title:
            await message.answer("عنوان هزینه نمی‌تونه خالی باشه.")
            return
        data = await state.get_data()
        members_list = await get_members(data["group_id"])
        await state.update_data(title=title[:160])
        await state.set_state(ExpenseFlow.waiting_payer)
        await message.answer(
            "💳 چه کسی این هزینه رو پرداخت کرده؟",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=member["display_name"], callback_data=f"expense:payer:{member['user_id']}")]
                for member in members_list
            ] + [[InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")]]),
        )

    @dp.callback_query(ExpenseFlow.waiting_payer, F.data.startswith("expense:payer:"))
    async def expense_payer(callback: CallbackQuery, state: FSMContext):
        payer_id = int(callback.data.split(":")[2])
        data = await state.get_data()
        members_list = await get_members(data["group_id"])
        member_ids = {member["user_id"] for member in members_list}
        if payer_id not in member_ids:
            await callback.answer("پرداخت‌کننده معتبر نیست.", show_alert=True)
            return
        selected = sorted(member_ids)
        await state.update_data(paid_by_user_id=payer_id, participant_user_ids=selected)
        await state.set_state(ExpenseFlow.waiting_participants)
        await callback.answer()
        await callback.message.answer(
            "👥 هزینه بین چه کسانی تقسیم بشه؟\nهمه به‌صورت پیش‌فرض انتخاب شدن.",
            reply_markup=participant_keyboard(members_list, set(selected)),
        )

    @dp.callback_query(ExpenseFlow.waiting_participants, F.data.startswith("expense:participant:"))
    async def toggle_participant(callback: CallbackQuery, state: FSMContext):
        user_id = int(callback.data.split(":")[2])
        data = await state.get_data()
        selected = set(data.get("participant_user_ids", []))
        selected.remove(user_id) if user_id in selected else selected.add(user_id)
        await state.update_data(participant_user_ids=sorted(selected))
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=participant_keyboard(await get_members(data["group_id"]), selected))

    @dp.callback_query(ExpenseFlow.waiting_participants, F.data == "expense:participants_done")
    async def expense_finish(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        participants = data.get("participant_user_ids", [])
        if not participants:
            await callback.answer("حداقل یک نفر باید انتخاب بشه.", show_alert=True)
            return
        async with api_client() as client:
            response = await client.post(f"/api/v1/groups/{data['group_id']}/expenses", json={
                "paid_by_user_id": data["paid_by_user_id"],
                "amount": data["amount"],
                "title": data["title"],
                "participant_user_ids": participants,
            })
            if response.status_code >= 400:
                await callback.answer("ثبت هزینه انجام نشد.", show_alert=True)
                return
            expense = response.json()
        names = {m["user_id"]: m["display_name"] for m in await get_members(data["group_id"])}
        payer = names.get(data["paid_by_user_id"], "نامشخص")
        group_id = data["group_id"]
        await state.clear()
        await callback.answer("ثبت شد")
        await callback.message.answer(
            f"✅ هزینه ثبت شد\n\n📝 {expense['title']}\n💰 {fmt_amount(expense['amount'])} تومان\n"
            f"💳 پرداخت‌کننده: {payer}\n👥 تقسیم بین {len(participants)} نفر",
            reply_markup=group_menu(group_id),
        )

    @dp.callback_query(F.data.startswith("balance:"))
    async def balances(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        names = {m["user_id"]: m["display_name"] for m in await get_members(group_id)}
        async with api_client() as client:
            response = await client.get(f"/api/v1/groups/{group_id}/balances")
            response.raise_for_status()
            items = response.json()
        lines = []
        for item in items:
            amount = Decimal(str(item["balance"]))
            status = "تسویه" if amount == 0 else (
                f"طلبکار {fmt_amount(amount)} تومان" if amount > 0 else f"بدهکار {fmt_amount(-amount)} تومان"
            )
            lines.append(f"• {names.get(item['user_id'], 'کاربر')}: {status}")
        await callback.answer()
        await callback.message.answer("📊 وضعیت حساب:\n\n" + "\n".join(lines), reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("plan:"))
    async def settlement_plan(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await authorize(callback, group_id)
        if not user:
            return
        names = {m["user_id"]: m["display_name"] for m in await get_members(group_id)}
        async with api_client() as client:
            response = await client.get(f"/api/v1/groups/{group_id}/settlement-plan")
            response.raise_for_status()
            plan = response.json()
        if not plan:
            await callback.answer()
            await callback.message.answer("✅ همه‌چیز تسویه است.", reply_markup=group_menu(group_id))
            return
        lines = [f"• {names.get(x['from_user_id'], 'کاربر')} → {names.get(x['to_user_id'], 'کاربر')}: {fmt_amount(x['amount'])} تومان" for x in plan]
        buttons = [[InlineKeyboardButton(
            text=f"✅ پرداخت کردم به {names.get(x['to_user_id'], 'کاربر')}",
            callback_data=f"settle:{group_id}:{x['from_user_id']}:{x['to_user_id']}:{x['amount']}",
        )] for x in plan if x["from_user_id"] == user["id"]]
        buttons.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"group:{group_id}")])
        await callback.answer()
        await callback.message.answer("💳 پیشنهاد تسویه:\n\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    @dp.callback_query(F.data.startswith("settle:"))
    async def settle(callback: CallbackQuery):
        _, group_raw, from_raw, to_raw, amount_raw = callback.data.split(":", 4)
        group_id, from_id, to_id = int(group_raw), int(from_raw), int(to_raw)
        user = await authorize(callback, group_id)
        if not user or user["id"] != from_id:
            if user:
                await callback.answer("فقط بدهکار می‌تونه پرداخت خودش رو ثبت کنه.", show_alert=True)
            return
        async with api_client() as client:
            response = await client.post(f"/api/v1/groups/{group_id}/settlements", json={
                "from_user_id": from_id, "to_user_id": to_id, "amount": amount_raw
            })
            if response.status_code >= 400:
                await callback.answer("ثبت تسویه انجام نشد.", show_alert=True)
                return
        names = {m["user_id"]: m["display_name"] for m in await get_members(group_id)}
        await callback.answer("تسویه ثبت شد")
        await callback.message.answer(
            f"✅ پرداخت {fmt_amount(amount_raw)} تومان به {names.get(to_id, 'کاربر')} ثبت شد.",
            reply_markup=group_menu(group_id),
        )

    @dp.callback_query(F.data.startswith("history:"))
    async def history(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        async with api_client() as client:
            response = await client.get(f"/api/v1/groups/{group_id}/expenses", params={"limit": 20})
            response.raise_for_status()
            items = response.json()
        text = "📜 هنوز هزینه‌ای ثبت نشده." if not items else "📜 ۲۰ هزینه آخر:\n\n" + "\n".join(
            f"• {x['title']} — {fmt_amount(x['amount'])} تومان — {x['paid_by_name']}" for x in items
        )
        await callback.answer()
        await callback.message.answer(text, reply_markup=group_menu(group_id))

    @dp.message(F.text == "❓ راهنما")
    async def help_message(message: Message):
        await message.answer(
            "۱) حساب بساز.\n۲) لینک دعوت امن رو برای دوستات بفرست.\n۳) هزینه رو ثبت و افراد شریک رو انتخاب کن.\n"
            "۴) وضعیت حساب طلب/بدهی رو نشون می‌ده.\n۵) بخش تسویه انتقال‌های لازم رو پیشنهاد می‌ده.\n\nلغو عملیات: /cancel"
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
