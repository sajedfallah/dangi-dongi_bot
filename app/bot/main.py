import asyncio
from decimal import Decimal, InvalidOperation

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

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


def normalize_digits(value: str) -> str:
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return value.translate(table)


def parse_amount(value: str) -> Decimal:
    cleaned = normalize_digits(value).strip().replace(",", "").replace("٬", "").replace(" ", "")
    cleaned = cleaned.replace("تومان", "").replace("تومن", "").strip()
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
    if amount <= 0:
        raise ValueError("amount must be positive")
    return amount


def fmt_amount(value: str | int | float | Decimal) -> str:
    amount = Decimal(str(value))
    if amount == amount.to_integral_value():
        return f"{int(amount):,}"
    return f"{amount:,.2f}"


async def ensure_user_from_message(message: Message) -> dict:
    payload = {
        "telegram_id": message.from_user.id,
        "display_name": message.from_user.full_name or str(message.from_user.id),
    }
    async with api_client() as client:
        response = await client.post("/api/v1/users", json=payload)
        response.raise_for_status()
        return response.json()


async def ensure_user_from_callback(callback: CallbackQuery) -> dict:
    payload = {
        "telegram_id": callback.from_user.id,
        "display_name": callback.from_user.full_name or str(callback.from_user.id),
    }
    async with api_client() as client:
        response = await client.post("/api/v1/users", json=payload)
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


async def user_has_group(user_id: int, group_id: int) -> bool:
    async with api_client() as client:
        response = await client.get(f"/api/v1/users/{user_id}/groups")
        response.raise_for_status()
        return any(item["id"] == group_id for item in response.json())


def group_menu(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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
        ]
    )


def participants_keyboard(members: list[dict], selected: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for member in members:
        marker = "✅" if member["user_id"] in selected else "⬜"
        rows.append([
            InlineKeyboardButton(
                text=f"{marker} {member['display_name']}",
                callback_data=f"expense:participant:{member['user_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="✅ ثبت هزینه", callback_data="expense:participants_done")])
    rows.append([InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_groups(target: Message, user_id: int):
    async with api_client() as client:
        response = await client.get(f"/api/v1/users/{user_id}/groups")
        response.raise_for_status()
        groups = response.json()
    if not groups:
        await target.answer(
            "هنوز هیچ حسابی نداری. با «➕ ساخت حساب جدید» اولین حساب رو بساز.",
            reply_markup=main_keyboard,
        )
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"💼 {group['name']}", callback_data=f"group:{group['id']}")]
            for group in groups
        ]
    )
    await target.answer("📂 حساب‌های تو:", reply_markup=keyboard)


async def run_bot():
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    bot = Bot(settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart(deep_link=True))
    async def start_deep_link(message: Message, command: CommandObject):
        user = await ensure_user_from_message(message)
        args = command.args or ""
        if args.startswith("join_"):
            try:
                group_id = int(args.removeprefix("join_"))
                group = await get_group(group_id)
                async with api_client() as client:
                    response = await client.post(
                        f"/api/v1/groups/{group_id}/members",
                        json={"user_id": user["id"]},
                    )
                    response.raise_for_status()
                await message.answer(
                    f"✅ به حساب «{group['name']}» اضافه شدی.",
                    reply_markup=group_menu(group_id),
                )
                return
            except (ValueError, httpx.HTTPError):
                await message.answer("این لینک دعوت معتبر نیست یا حساب دیگر در دسترس نیست.")
        await message.answer(
            "سلام 👋\nاینجا می‌تونی خرج‌های مشترک و دونگ‌ها رو بدون حساب‌وکتاب دستی مدیریت کنی.",
            reply_markup=main_keyboard,
        )

    @dp.message(CommandStart())
    async def start(message: Message):
        await ensure_user_from_message(message)
        await message.answer(
            "سلام 👋\nاینجا می‌تونی خرج‌های مشترک و دونگ‌ها رو بدون حساب‌وکتاب دستی مدیریت کنی.",
            reply_markup=main_keyboard,
        )

    @dp.message(Command("cancel"))
    async def cancel_command(message: Message, state: FSMContext):
        await state.clear()
        await message.answer("عملیات لغو شد.", reply_markup=main_keyboard)

    @dp.callback_query(F.data == "flow:cancel")
    async def cancel_callback(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer("لغو شد")
        await callback.message.answer("عملیات لغو شد.", reply_markup=main_keyboard)

    @dp.message(F.text == "➕ ساخت حساب جدید")
    async def new_group(message: Message, state: FSMContext):
        await state.clear()
        await state.set_state(CreateGroupFlow.waiting_name)
        await message.answer("اسم حساب رو وارد کن.\nمثال: سفر شمال\n\nبرای لغو: /cancel")

    @dp.message(CreateGroupFlow.waiting_name)
    async def group_name(message: Message, state: FSMContext):
        name = (message.text or "").strip()
        if not name:
            await message.answer("اسم حساب نمی‌تونه خالی باشه.")
            return
        user = await ensure_user_from_message(message)
        async with api_client() as client:
            response = await client.post(
                "/api/v1/groups",
                json={"name": name[:120], "owner_user_id": user["id"], "currency": "IRT"},
            )
            response.raise_for_status()
            group = response.json()
        await state.clear()
        await message.answer(
            f"✅ حساب «{group['name']}» ساخته شد.\nحالا می‌تونی دوستات رو دعوت کنی یا اولین هزینه رو ثبت کنی.",
            reply_markup=group_menu(group["id"]),
        )

    @dp.message(F.text == "📂 حساب‌های من")
    async def my_groups(message: Message):
        user = await ensure_user_from_message(message)
        await show_groups(message, user["id"])

    @dp.callback_query(F.data == "groups:list")
    async def my_groups_callback(callback: CallbackQuery):
        user = await ensure_user_from_callback(callback)
        await callback.answer()
        await show_groups(callback.message, user["id"])

    @dp.callback_query(F.data.startswith("group:"))
    async def open_group(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await ensure_user_from_callback(callback)
        if not await user_has_group(user["id"], group_id):
            await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
            return
        group = await get_group(group_id)
        await callback.answer()
        await callback.message.answer(
            f"💼 {group['name']}\nچه کاری می‌خوای انجام بدی؟",
            reply_markup=group_menu(group_id),
        )

    @dp.callback_query(F.data.startswith("invite:"))
    async def invite_member(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await ensure_user_from_callback(callback)
        if not await user_has_group(user["id"], group_id):
            await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
            return
        group = await get_group(group_id)
        me = await bot.get_me()
        link = f"https://t.me/{me.username}?start=join_{group_id}"
        await callback.answer()
        await callback.message.answer(
            f"🔗 لینک دعوت «{group['name']}»:\n{link}\n\nاین لینک رو برای دوستات بفرست؛ با بازکردنش مستقیم عضو این حساب می‌شن."
        )

    @dp.callback_query(F.data.startswith("members:"))
    async def members(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await ensure_user_from_callback(callback)
        if not await user_has_group(user["id"], group_id):
            await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
            return
        items = await get_members(group_id)
        text = "👥 اعضای حساب:\n\n" + "\n".join(
            f"• {item['display_name']}{' 👑' if item['role'] == 'owner' else ''}" for item in items
        )
        await callback.answer()
        await callback.message.answer(text, reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("expense:new:"))
    async def expense_new(callback: CallbackQuery, state: FSMContext):
        group_id = int(callback.data.split(":")[2])
        user = await ensure_user_from_callback(callback)
        if not await user_has_group(user["id"], group_id):
            await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
            return
        await state.clear()
        await state.update_data(group_id=group_id)
        await state.set_state(ExpenseFlow.waiting_amount)
        await callback.answer()
        await callback.message.answer("💰 مبلغ هزینه رو به تومان وارد کن.\nمثال: 1,250,000\n\nبرای لغو: /cancel")

    @dp.message(ExpenseFlow.waiting_amount)
    async def expense_amount(message: Message, state: FSMContext):
        try:
            amount = parse_amount(message.text or "")
        except ValueError:
            await message.answer("مبلغ معتبر نیست. فقط مبلغ مثبت وارد کن؛ مثال: 750000")
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
        group_id = data["group_id"]
        members = await get_members(group_id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=item["display_name"], callback_data=f"expense:payer:{item['user_id']}")]
                for item in members
            ] + [[InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")]]
        )
        await state.update_data(title=title[:160])
        await state.set_state(ExpenseFlow.waiting_payer)
        await message.answer("💳 چه کسی این هزینه رو پرداخت کرده؟", reply_markup=keyboard)

    @dp.callback_query(ExpenseFlow.waiting_payer, F.data.startswith("expense:payer:"))
    async def expense_payer(callback: CallbackQuery, state: FSMContext):
        payer_id = int(callback.data.split(":")[2])
        data = await state.get_data()
        members = await get_members(data["group_id"])
        member_ids = {item["user_id"] for item in members}
        if payer_id not in member_ids:
            await callback.answer("پرداخت‌کننده معتبر نیست.", show_alert=True)
            return
        selected = sorted(member_ids)
        await state.update_data(paid_by_user_id=payer_id, participant_user_ids=selected)
        await state.set_state(ExpenseFlow.waiting_participants)
        await callback.answer()
        await callback.message.answer(
            "👥 هزینه بین چه کسانی تقسیم بشه؟\nبه‌صورت پیش‌فرض همه انتخاب شدن. روی اسم هر نفر بزن تا انتخابش تغییر کنه.",
            reply_markup=participants_keyboard(members, set(selected)),
        )

    @dp.callback_query(ExpenseFlow.waiting_participants, F.data.startswith("expense:participant:"))
    async def toggle_participant(callback: CallbackQuery, state: FSMContext):
        user_id = int(callback.data.split(":")[2])
        data = await state.get_data()
        selected = set(data.get("participant_user_ids", []))
        if user_id in selected:
            selected.remove(user_id)
        else:
            selected.add(user_id)
        await state.update_data(participant_user_ids=sorted(selected))
        members = await get_members(data["group_id"])
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=participants_keyboard(members, selected))

    @dp.callback_query(ExpenseFlow.waiting_participants, F.data == "expense:participants_done")
    async def finish_expense(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        participants = data.get("participant_user_ids", [])
        if not participants:
            await callback.answer("حداقل یک نفر باید در هزینه شریک باشه.", show_alert=True)
            return
        payload = {
            "paid_by_user_id": data["paid_by_user_id"],
            "amount": data["amount"],
            "title": data["title"],
            "participant_user_ids": participants,
        }
        async with api_client() as client:
            response = await client.post(f"/api/v1/groups/{data['group_id']}/expenses", json=payload)
            if response.status_code >= 400:
                await callback.answer("ثبت هزینه انجام نشد. دوباره تلاش کن.", show_alert=True)
                return
            expense = response.json()
        members = await get_members(data["group_id"])
        names = {item["user_id"]: item["display_name"] for item in members}
        payer_name = names.get(data["paid_by_user_id"], "نامشخص")
        await state.clear()
        await callback.answer("ثبت شد")
        await callback.message.answer(
            f"✅ هزینه ثبت شد\n\n"
            f"📝 {expense['title']}\n"
            f"💰 {fmt_amount(expense['amount'])} تومان\n"
            f"💳 پرداخت‌کننده: {payer_name}\n"
            f"👥 تقسیم بین {len(participants)} نفر",
            reply_markup=group_menu(data["group_id"]),
        )

    @dp.callback_query(F.data.startswith("balance:"))
    async def balance(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await ensure_user_from_callback(callback)
        if not await user_has_group(user["id"], group_id):
            await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
            return
        members = await get_members(group_id)
        names = {item["user_id"]: item["display_name"] for item in members}
        async with api_client() as client:
            response = await client.get(f"/api/v1/groups/{group_id}/balances")
            response.raise_for_status()
            balances = response.json()
        lines = []
        for item in balances:
            value = Decimal(str(item["balance"]))
            if value > 0:
                status = f"طلبکار {fmt_amount(value)} تومان"
            elif value < 0:
                status = f"بدهکار {fmt_amount(-value)} تومان"
            else:
                status = "تسویه"
            lines.append(f"• {names.get(item['user_id'], 'کاربر')}: {status}")
        await callback.answer()
        await callback.message.answer("📊 وضعیت حساب:\n\n" + "\n".join(lines), reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("plan:"))
    async def settlement_plan(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await ensure_user_from_callback(callback)
        if not await user_has_group(user["id"], group_id):
            await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
            return
        members = await get_members(group_id)
        names = {item["user_id"]: item["display_name"] for item in members}
        async with api_client() as client:
            response = await client.get(f"/api/v1/groups/{group_id}/settlement-plan")
            response.raise_for_status()
            plan = response.json()
        if not plan:
            await callback.answer()
            await callback.message.answer("✅ همه‌چیز تسویه است؛ انتقالی لازم نیست.", reply_markup=group_menu(group_id))
            return
        lines = [
            f"• {names.get(item['from_user_id'], 'کاربر')} ← {fmt_amount(item['amount'])} تومان → {names.get(item['to_user_id'], 'کاربر')}"
            for item in plan
        ]
        buttons = []
        for item in plan:
            if item["from_user_id"] == user["id"]:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"✅ پرداخت کردم به {names.get(item['to_user_id'], 'کاربر')}",
                        callback_data=f"settle:{group_id}:{item['from_user_id']}:{item['to_user_id']}:{item['amount']}",
                    )
                ])
        buttons.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"group:{group_id}")])
        await callback.answer()
        await callback.message.answer(
            "💳 پیشنهاد تسویه:\n\n" + "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )

    @dp.callback_query(F.data.startswith("settle:"))
    async def record_settlement(callback: CallbackQuery):
        _, group_id_raw, from_raw, to_raw, amount_raw = callback.data.split(":", 4)
        group_id = int(group_id_raw)
        from_user_id = int(from_raw)
        to_user_id = int(to_raw)
        user = await ensure_user_from_callback(callback)
        if user["id"] != from_user_id or not await user_has_group(user["id"], group_id):
            await callback.answer("فقط بدهکار می‌تونه پرداخت خودش رو ثبت کنه.", show_alert=True)
            return
        async with api_client() as client:
            response = await client.post(
                f"/api/v1/groups/{group_id}/settlements",
                json={"from_user_id": from_user_id, "to_user_id": to_user_id, "amount": amount_raw},
            )
            if response.status_code >= 400:
                await callback.answer("ثبت تسویه انجام نشد.", show_alert=True)
                return
        members = await get_members(group_id)
        names = {item["user_id"]: item["display_name"] for item in members}
        await callback.answer("تسویه ثبت شد")
        await callback.message.answer(
            f"✅ پرداخت {fmt_amount(amount_raw)} تومان به {names.get(to_user_id, 'کاربر')} ثبت شد.",
            reply_markup=group_menu(group_id),
        )

    @dp.callback_query(F.data.startswith("history:"))
    async def history(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await ensure_user_from_callback(callback)
        if not await user_has_group(user["id"], group_id):
            await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
            return
        async with api_client() as client:
            response = await client.get(f"/api/v1/groups/{group_id}/expenses", params={"limit": 20})
            response.raise_for_status()
            items = response.json()
        if not items:
            text = "📜 هنوز هزینه‌ای در این حساب ثبت نشده."
        else:
            text = "📜 ۲۰ هزینه آخر:\n\n" + "\n".join(
                f"• {item['title']} — {fmt_amount(item['amount'])} تومان — {item['paid_by_name']}"
                for item in items
            )
        await callback.answer()
        await callback.message.answer(text, reply_markup=group_menu(group_id))

    @dp.message(F.text == "❓ راهنما")
    async def help_msg(message: Message):
        await message.answer(
            "راهنمای سریع:\n"
            "۱) یک حساب بساز.\n"
            "۲) لینک دعوت رو برای دوستات بفرست.\n"
            "۳) هزینه‌ها رو ثبت کن و افراد شریک رو انتخاب کن.\n"
            "۴) «وضعیت حساب» طلب و بدهی هر نفر رو نشون می‌ده.\n"
            "۵) «تسویه» کمترین انتقال‌های لازم رو پیشنهاد می‌ده.\n\n"
            "هرجا خواستی عملیات جاری رو لغو کنی: /cancel"
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
