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
    waiting_split_mode = State()
    waiting_split_value = State()


class EditExpenseFlow(StatesGroup):
    waiting_amount = State()
    waiting_title = State()
    waiting_split_mode = State()
    waiting_split_value = State()


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ ساخت حساب جدید"), KeyboardButton(text="📂 حساب‌های من")],
        [KeyboardButton(text="❓ راهنما")],
    ],
    resize_keyboard=True,
)

SPLIT_LABELS = {
    "equal": "مساوی",
    "percentage": "درصدی",
    "shares": "سهمی/وزنی",
    "exact": "مبلغ ثابت",
}


def api_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.api_base_url, timeout=15)


def parse_number(value: str) -> Decimal:
    digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    cleaned = value.translate(digits).strip().replace(",", "").replace("٬", "").replace(" ", "")
    cleaned = cleaned.replace("تومان", "").replace("تومن", "").replace("٪", "").replace("%", "").strip()
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid number") from exc
    if number <= 0:
        raise ValueError("number must be positive")
    return number


def parse_amount(value: str) -> Decimal:
    return parse_number(value)


def fmt_amount(value) -> str:
    amount = Decimal(str(value))
    return f"{int(amount):,}" if amount == amount.to_integral_value() else f"{amount:,.2f}"


async def ensure_user(telegram_user) -> dict:
    async with api_client() as client:
        response = await client.post("/api/v1/users", json={
            "telegram_id": telegram_user.id,
            "display_name": telegram_user.full_name or str(telegram_user.id),
        })
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


async def get_expense(group_id: int, expense_id: int, actor_user_id: int) -> dict:
    async with api_client() as client:
        response = await client.get(
            f"/api/v1/groups/{group_id}/expenses/{expense_id}",
            params={"actor_user_id": actor_user_id},
        )
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
        [InlineKeyboardButton(text="ادامه ➡️", callback_data="expense:participants_done")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def split_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚖️ مساوی", callback_data=f"{prefix}:equal")],
        [InlineKeyboardButton(text="📊 درصدی", callback_data=f"{prefix}:percentage")],
        [InlineKeyboardButton(text="🔢 سهمی / وزنی", callback_data=f"{prefix}:shares")],
        [InlineKeyboardButton(text="💵 مبلغ ثابت", callback_data=f"{prefix}:exact")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")],
    ])


def edit_menu(group_id: int, expense_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 تغییر مبلغ", callback_data=f"edit:amount:{group_id}:{expense_id}")],
        [InlineKeyboardButton(text="📝 تغییر عنوان", callback_data=f"edit:title:{group_id}:{expense_id}")],
        [InlineKeyboardButton(text="⚖️ تغییر نوع تقسیم", callback_data=f"edit:split:{group_id}:{expense_id}")],
        [InlineKeyboardButton(text="⬅️ تاریخچه", callback_data=f"history:{group_id}")],
    ])


async def show_groups(message: Message, user_id: int):
    async with api_client() as client:
        response = await client.get(f"/api/v1/users/{user_id}/groups")
        response.raise_for_status()
        groups = response.json()
    if not groups:
        await message.answer("هنوز حسابی نداری. با «➕ ساخت حساب جدید» شروع کن.", reply_markup=main_keyboard)
        return
    await message.answer("📂 حساب‌های تو:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💼 {group['name']}", callback_data=f"group:{group['id']}")] for group in groups
    ]))


async def authorize(callback: CallbackQuery, group_id: int) -> dict | None:
    user = await ensure_user(callback.from_user)
    if not await has_group_access(user["id"], group_id):
        await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
        return None
    return user


async def prompt_split_value(target: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    participant_ids = data["participant_user_ids"]
    index = data.get("split_index", 0)
    members = {m["user_id"]: m["display_name"] for m in await get_members(data["group_id"])}
    user_id = participant_ids[index]
    mode = data["split_mode"]
    unit = {"percentage": "درصد", "shares": "سهم/وزن", "exact": "تومان"}[mode]
    await target.answer(f"مقدار {unit} برای «{members.get(user_id, 'کاربر')}» را وارد کن:")
    await state.set_state(EditExpenseFlow.waiting_split_value if edit else ExpenseFlow.waiting_split_value)


async def submit_expense_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    payload = {
        "actor_user_id": data["actor_user_id"],
        "paid_by_user_id": data["paid_by_user_id"],
        "amount": data["amount"],
        "title": data["title"],
        "participant_user_ids": data["participant_user_ids"],
        "split_mode": data.get("split_mode", "equal"),
        "split_values": data.get("split_values"),
    }
    async with api_client() as client:
        response = await client.post(f"/api/v1/groups/{data['group_id']}/expenses", json=payload)
    if response.status_code >= 400:
        detail = response.json().get("detail", "ثبت هزینه انجام نشد") if response.headers.get("content-type", "").startswith("application/json") else "ثبت هزینه انجام نشد"
        await callback.answer("ثبت نشد", show_alert=True)
        await callback.message.answer(f"❌ {detail}")
        return
    expense = response.json()
    names = {m["user_id"]: m["display_name"] for m in await get_members(data["group_id"])}
    payer = names.get(data["paid_by_user_id"], "نامشخص")
    group_id = data["group_id"]
    await state.clear()
    await callback.answer("ثبت شد")
    await callback.message.answer(
        f"✅ هزینه ثبت شد\n\n📝 {expense['title']}\n💰 {fmt_amount(expense['amount'])} تومان\n"
        f"💳 پرداخت‌کننده: {payer}\n⚖️ تقسیم: {SPLIT_LABELS.get(expense.get('split_mode'), 'مساوی')}",
        reply_markup=group_menu(group_id),
    )


async def submit_expense_edit(target: Message, state: FSMContext):
    data = await state.get_data()
    payload = {
        "actor_user_id": data["actor_user_id"],
        "paid_by_user_id": data["paid_by_user_id"],
        "amount": data["amount"],
        "title": data["title"],
        "participant_user_ids": data["participant_user_ids"],
        "split_mode": data.get("split_mode", "equal"),
        "split_values": data.get("split_values"),
        "category": data.get("category"),
        "note": data.get("note"),
    }
    async with api_client() as client:
        response = await client.put(
            f"/api/v1/groups/{data['group_id']}/expenses/{data['expense_id']}",
            json=payload,
        )
    if response.status_code >= 400:
        detail = response.json().get("detail", "ویرایش انجام نشد") if response.headers.get("content-type", "").startswith("application/json") else "ویرایش انجام نشد"
        await target.answer(f"❌ {detail}")
        return
    expense = response.json()
    group_id = data["group_id"]
    await state.clear()
    await target.answer(
        f"✅ هزینه #{expense['id']} ویرایش شد.\n📝 {expense['title']}\n💰 {fmt_amount(expense['amount'])} تومان\n"
        f"⚖️ تقسیم: {SPLIT_LABELS.get(expense.get('split_mode'), 'مساوی')}",
        reply_markup=group_menu(group_id),
    )


async def load_edit_state(state: FSMContext, user: dict, group_id: int, expense_id: int) -> dict:
    expense = await get_expense(group_id, expense_id, user["id"])
    await state.clear()
    await state.update_data(
        group_id=group_id,
        expense_id=expense_id,
        actor_user_id=user["id"],
        paid_by_user_id=expense["paid_by_user_id"],
        amount=str(expense["amount"]),
        title=expense["title"],
        participant_user_ids=expense["participant_user_ids"],
        split_mode=expense.get("split_mode", "equal"),
        split_values=expense.get("split_values"),
        category=expense.get("category"),
        note=expense.get("note"),
    )
    return expense


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
        await message.answer("سلام 👋\nبه دنگی - دونگی خوش اومدی. خرج‌های مشترک و دونگ‌ها رو بدون حساب‌وکتاب دستی مدیریت کن.", reply_markup=main_keyboard)

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
            response = await client.post("/api/v1/groups", json={"name": name[:120], "owner_user_id": user["id"], "currency": "IRT"})
            response.raise_for_status()
            group = response.json()
        await state.clear()
        await message.answer(f"✅ حساب «{group['name']}» ساخته شد.", reply_markup=group_menu(group["id"]))

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
        await callback.message.answer(f"🔗 لینک امن دعوت «{group['name']}»:\n{link}")

    @dp.callback_query(F.data.startswith("members:"))
    async def members(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        items = await get_members(group_id)
        role_icon = {"owner": " 👑", "admin": " 🛡", "member": ""}
        await callback.answer()
        await callback.message.answer("👥 اعضای حساب:\n\n" + "\n".join(f"• {x['display_name']}{role_icon.get(x['role'], '')}" for x in items), reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("expense:new:"))
    async def expense_start(callback: CallbackQuery, state: FSMContext):
        group_id = int(callback.data.split(":")[2])
        user = await authorize(callback, group_id)
        if not user:
            return
        await state.clear()
        await state.update_data(group_id=group_id, actor_user_id=user["id"])
        await state.set_state(ExpenseFlow.waiting_amount)
        await callback.answer()
        await callback.message.answer("💰 مبلغ هزینه رو به تومان وارد کن.\nمثال: 1,250,000")

    @dp.message(ExpenseFlow.waiting_amount)
    async def expense_amount(message: Message, state: FSMContext):
        try:
            amount = parse_amount(message.text or "")
        except ValueError:
            await message.answer("مبلغ معتبر نیست. مثال: 750000")
            return
        await state.update_data(amount=str(amount))
        await state.set_state(ExpenseFlow.waiting_title)
        await message.answer("📝 این هزینه بابت چی بوده؟")

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
        await message.answer("💳 چه کسی پرداخت کرده؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=m["display_name"], callback_data=f"expense:payer:{m['user_id']}")] for m in members_list
        ]))

    @dp.callback_query(ExpenseFlow.waiting_payer, F.data.startswith("expense:payer:"))
    async def expense_payer(callback: CallbackQuery, state: FSMContext):
        payer_id = int(callback.data.split(":")[2])
        data = await state.get_data()
        members_list = await get_members(data["group_id"])
        member_ids = {m["user_id"] for m in members_list}
        if payer_id not in member_ids:
            await callback.answer("پرداخت‌کننده معتبر نیست.", show_alert=True)
            return
        selected = sorted(member_ids)
        await state.update_data(paid_by_user_id=payer_id, participant_user_ids=selected)
        await state.set_state(ExpenseFlow.waiting_participants)
        await callback.answer()
        await callback.message.answer("👥 هزینه بین چه کسانی تقسیم بشه؟", reply_markup=participant_keyboard(members_list, set(selected)))

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
    async def participants_done(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        if not data.get("participant_user_ids"):
            await callback.answer("حداقل یک نفر باید انتخاب بشه.", show_alert=True)
            return
        await state.set_state(ExpenseFlow.waiting_split_mode)
        await callback.answer()
        await callback.message.answer("⚖️ هزینه چطور تقسیم بشه؟", reply_markup=split_keyboard("expense:split"))

    @dp.callback_query(ExpenseFlow.waiting_split_mode, F.data.startswith("expense:split:"))
    async def choose_split(callback: CallbackQuery, state: FSMContext):
        mode = callback.data.split(":")[2]
        await state.update_data(split_mode=mode, split_values=None)
        if mode == "equal":
            await submit_expense_create(callback, state)
            return
        await state.update_data(split_index=0, split_values={})
        await callback.answer()
        await prompt_split_value(callback.message, state)

    @dp.message(ExpenseFlow.waiting_split_value)
    async def split_value(message: Message, state: FSMContext):
        try:
            value = parse_number(message.text or "")
        except ValueError:
            await message.answer("عدد معتبر و مثبت وارد کن.")
            return
        data = await state.get_data()
        index = data.get("split_index", 0)
        ids = data["participant_user_ids"]
        values = dict(data.get("split_values") or {})
        values[str(ids[index])] = str(value)
        index += 1
        await state.update_data(split_values=values, split_index=index)
        if index < len(ids):
            await prompt_split_value(message, state)
            return
        if data["split_mode"] == "percentage" and sum(Decimal(v) for v in values.values()) != Decimal("100"):
            await state.update_data(split_index=0, split_values={})
            await message.answer("❌ مجموع درصدها باید دقیقاً 100 باشد. دوباره وارد کن.")
            await prompt_split_value(message, state)
            return
        fake = await bot.send_message(message.chat.id, "در حال ثبت…")
        class CallbackProxy:
            message = fake
            async def answer(self, *args, **kwargs):
                return None
        await submit_expense_create(CallbackProxy(), state)

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
            status = "تسویه" if amount == 0 else (f"طلبکار {fmt_amount(amount)} تومان" if amount > 0 else f"بدهکار {fmt_amount(-amount)} تومان")
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
        buttons = [[InlineKeyboardButton(text=f"✅ پرداخت کردم به {names.get(x['to_user_id'], 'کاربر')}", callback_data=f"settle:{group_id}:{x['from_user_id']}:{x['to_user_id']}:{x['amount']}")] for x in plan if x["from_user_id"] == user["id"]]
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
            response = await client.post(f"/api/v1/groups/{group_id}/settlements", json={"actor_user_id": user["id"], "from_user_id": from_id, "to_user_id": to_id, "amount": amount_raw})
        if response.status_code >= 400:
            await callback.answer("ثبت تسویه انجام نشد.", show_alert=True)
            return
        names = {m["user_id"]: m["display_name"] for m in await get_members(group_id)}
        await callback.answer("تسویه ثبت شد")
        await callback.message.answer(f"✅ پرداخت {fmt_amount(amount_raw)} تومان به {names.get(to_id, 'کاربر')} ثبت شد.", reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("history:"))
    async def history(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await authorize(callback, group_id)
        if not user:
            return
        members_list = await get_members(group_id)
        current = next((m for m in members_list if m["user_id"] == user["id"]), None)
        can_manage_all = bool(current and current["role"] in {"owner", "admin"})
        async with api_client() as client:
            response = await client.get(f"/api/v1/groups/{group_id}/expenses", params={"limit": 20})
            response.raise_for_status()
            items = response.json()
        if not items:
            await callback.answer()
            await callback.message.answer("📜 هنوز هزینه‌ای ثبت نشده.", reply_markup=group_menu(group_id))
            return
        text = "📜 ۲۰ هزینه آخر:\n\n" + "\n".join(f"• #{x['id']} {x['title']} — {fmt_amount(x['amount'])} تومان — {SPLIT_LABELS.get(x.get('split_mode'), 'مساوی')}" for x in items)
        buttons = []
        for item in items:
            if can_manage_all or item.get("created_by_user_id") == user["id"]:
                buttons.append([
                    InlineKeyboardButton(text=f"✏️ #{item['id']}", callback_data=f"expense:edit:{group_id}:{item['id']}"),
                    InlineKeyboardButton(text=f"🗑 #{item['id']}", callback_data=f"expense:delete_confirm:{group_id}:{item['id']}"),
                ])
        buttons.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"group:{group_id}")])
        await callback.answer()
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    @dp.callback_query(F.data.startswith("expense:edit:"))
    async def edit_expense_menu(callback: CallbackQuery):
        _, _, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        try:
            expense = await get_expense(group_id, expense_id, user["id"])
        except httpx.HTTPError:
            await callback.answer("هزینه پیدا نشد.", show_alert=True)
            return
        await callback.answer()
        await callback.message.answer(
            f"✏️ ویرایش #{expense_id}\n📝 {expense['title']}\n💰 {fmt_amount(expense['amount'])} تومان\n⚖️ {SPLIT_LABELS.get(expense.get('split_mode'), 'مساوی')}",
            reply_markup=edit_menu(group_id, expense_id),
        )

    @dp.callback_query(F.data.startswith("edit:amount:"))
    async def edit_amount_start(callback: CallbackQuery, state: FSMContext):
        _, _, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        await load_edit_state(state, user, group_id, expense_id)
        await state.set_state(EditExpenseFlow.waiting_amount)
        await callback.answer()
        await callback.message.answer("💰 مبلغ جدید را وارد کن:")

    @dp.message(EditExpenseFlow.waiting_amount)
    async def edit_amount_finish(message: Message, state: FSMContext):
        try:
            amount = parse_amount(message.text or "")
        except ValueError:
            await message.answer("مبلغ معتبر وارد کن.")
            return
        data = await state.get_data()
        await state.update_data(amount=str(amount))
        if data.get("split_mode") == "exact":
            await state.update_data(split_mode="equal", split_values=None)
            await message.answer("ℹ️ چون مبلغ کل تغییر کرد، تقسیم مبلغ ثابت به حالت مساوی برگشت. در صورت نیاز دوباره نوع تقسیم را ویرایش کن.")
        await submit_expense_edit(message, state)

    @dp.callback_query(F.data.startswith("edit:title:"))
    async def edit_title_start(callback: CallbackQuery, state: FSMContext):
        _, _, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        await load_edit_state(state, user, group_id, expense_id)
        await state.set_state(EditExpenseFlow.waiting_title)
        await callback.answer()
        await callback.message.answer("📝 عنوان جدید را وارد کن:")

    @dp.message(EditExpenseFlow.waiting_title)
    async def edit_title_finish(message: Message, state: FSMContext):
        title = (message.text or "").strip()
        if not title:
            await message.answer("عنوان نمی‌تونه خالی باشه.")
            return
        await state.update_data(title=title[:160])
        await submit_expense_edit(message, state)

    @dp.callback_query(F.data.startswith("edit:split:"))
    async def edit_split_start(callback: CallbackQuery, state: FSMContext):
        _, _, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        await load_edit_state(state, user, group_id, expense_id)
        await state.set_state(EditExpenseFlow.waiting_split_mode)
        await callback.answer()
        await callback.message.answer("⚖️ نوع تقسیم جدید:", reply_markup=split_keyboard("edit:mode"))

    @dp.callback_query(EditExpenseFlow.waiting_split_mode, F.data.startswith("edit:mode:"))
    async def edit_split_mode(callback: CallbackQuery, state: FSMContext):
        mode = callback.data.split(":")[2]
        await state.update_data(split_mode=mode, split_values=None)
        if mode == "equal":
            await callback.answer()
            await submit_expense_edit(callback.message, state)
            return
        await state.update_data(split_index=0, split_values={})
        await callback.answer()
        await prompt_split_value(callback.message, state, edit=True)

    @dp.message(EditExpenseFlow.waiting_split_value)
    async def edit_split_value(message: Message, state: FSMContext):
        try:
            value = parse_number(message.text or "")
        except ValueError:
            await message.answer("عدد معتبر و مثبت وارد کن.")
            return
        data = await state.get_data()
        index = data.get("split_index", 0)
        ids = data["participant_user_ids"]
        values = dict(data.get("split_values") or {})
        values[str(ids[index])] = str(value)
        index += 1
        await state.update_data(split_values=values, split_index=index)
        if index < len(ids):
            await prompt_split_value(message, state, edit=True)
            return
        if data["split_mode"] == "percentage" and sum(Decimal(v) for v in values.values()) != Decimal("100"):
            await state.update_data(split_index=0, split_values={})
            await message.answer("❌ مجموع درصدها باید 100 باشد. دوباره وارد کن.")
            await prompt_split_value(message, state, edit=True)
            return
        await submit_expense_edit(message, state)

    @dp.callback_query(F.data.startswith("expense:delete_confirm:"))
    async def delete_confirm(callback: CallbackQuery):
        _, _, _, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        if not await authorize(callback, group_id):
            return
        await callback.answer()
        await callback.message.answer(f"⚠️ هزینه #{expense_id} حذف شود؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 بله، حذف کن", callback_data=f"expense:delete:{group_id}:{expense_id}")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data=f"history:{group_id}")],
        ]))

    @dp.callback_query(F.data.startswith("expense:delete:"))
    async def delete_expense(callback: CallbackQuery):
        _, _, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        async with api_client() as client:
            response = await client.request("DELETE", f"/api/v1/groups/{group_id}/expenses/{expense_id}", json={"actor_user_id": user["id"]})
        if response.status_code == 403:
            await callback.answer("اجازه حذف این هزینه را نداری.", show_alert=True)
            return
        if response.status_code >= 400:
            await callback.answer("حذف هزینه انجام نشد.", show_alert=True)
            return
        await callback.answer("حذف شد")
        await callback.message.answer(f"✅ هزینه #{expense_id} حذف شد.", reply_markup=group_menu(group_id))

    @dp.message(F.text == "❓ راهنما")
    async def help_message(message: Message):
        await message.answer(
            "دنگی - دونگی برای مدیریت خرج‌های مشترک است.\n\n"
            "• تقسیم مساوی، درصدی، سهمی/وزنی و مبلغ ثابت\n"
            "• ویرایش مبلغ، عنوان و مدل تقسیم از تاریخچه\n"
            "• محاسبه طلب/بدهی و پیشنهاد تسویه\n"
            "• دعوت امن اعضا با لینک تلگرام\n\nلغو عملیات: /cancel"
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
