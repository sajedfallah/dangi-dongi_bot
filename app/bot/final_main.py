from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from html import escape

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

from app.bot.security import make_join_payload, parse_join_payload
from app.core.config import settings


CATEGORY_LABELS = {
    "food": "🍽 خورد و خوراک",
    "transport": "🚕 رفت‌وآمد",
    "stay": "🏨 اقامت",
    "shopping": "🛍 خرید",
    "entertainment": "🎉 تفریح",
    "fuel": "⛽ سوخت",
    "other": "📦 سایر",
}
SPLIT_LABELS = {"equal": "مساوی", "percentage": "درصدی", "shares": "سهمی/وزنی", "exact": "مبلغ ثابت"}
ROLE_ICON = {"owner": "👑", "admin": "🛡", "member": "👤"}


class CreateGroupFlow(StatesGroup):
    waiting_name = State()


class PaymentProfileFlow(StatesGroup):
    bank_name = State()
    account_holder = State()
    card_number = State()
    iban = State()
    account_number = State()


class ExpenseFlow(StatesGroup):
    amount = State()
    title = State()
    category = State()
    payer = State()
    participants = State()
    split_mode = State()
    split_value = State()


class ReceiptFlow(StatesGroup):
    waiting_receipt = State()


class EditExpenseFlow(StatesGroup):
    waiting_value = State()


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ حساب جدید"), KeyboardButton(text="📂 حساب‌های من")],
        [KeyboardButton(text="🔔 اعلان‌ها"), KeyboardButton(text="⚙️ تنظیمات من")],
        [KeyboardButton(text="🗄 آرشیو"), KeyboardButton(text="❓ راهنما")],
    ],
    resize_keyboard=True,
)


def api_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.api_base_url, timeout=20)


def parse_number(value: str) -> Decimal:
    digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    cleaned = (value or "").translate(digits).strip().replace(",", "").replace("٬", "").replace(" ", "")
    cleaned = cleaned.replace("تومان", "").replace("تومن", "").replace("٪", "").replace("%", "").strip()
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid number") from exc
    if number <= 0:
        raise ValueError("number must be positive")
    return number


def fmt_amount(value) -> str:
    amount = Decimal(str(value))
    return f"{int(amount):,}" if amount == amount.to_integral_value() else f"{amount:,.2f}"


def payment_text(profile: dict | None) -> str:
    if not profile:
        return "اطلاعات پرداخت ثبت نشده."
    rows = []
    if profile.get("account_holder"):
        rows.append(f"👤 صاحب حساب: {escape(profile['account_holder'])}")
    if profile.get("bank_name"):
        rows.append(f"🏦 بانک: {escape(profile['bank_name'])}")
    if profile.get("card_number"):
        rows.append(f"💳 کارت: <code>{escape(profile['card_number'])}</code>")
    if profile.get("account_number"):
        rows.append(f"🏧 حساب: <code>{escape(profile['account_number'])}</code>")
    if profile.get("iban"):
        rows.append(f"🔢 شبا: <code>{escape(profile['iban'])}</code>")
    return "\n".join(rows) if rows else "اطلاعات پرداخت ثبت نشده."


def group_menu(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 ثبت هزینه", callback_data=f"expense:new:{group_id}")],
        [
            InlineKeyboardButton(text="📊 گزارش‌ها", callback_data=f"reports:{group_id}"),
            InlineKeyboardButton(text="💳 تسویه", callback_data=f"plan:{group_id}"),
        ],
        [
            InlineKeyboardButton(text="⏳ منتظر تأیید", callback_data=f"pending:{group_id}"),
            InlineKeyboardButton(text="🔔 یادآوری بدهی", callback_data=f"remind:{group_id}"),
        ],
        [
            InlineKeyboardButton(text="📜 تاریخچه", callback_data=f"history:{group_id}"),
            InlineKeyboardButton(text="👥 اعضا", callback_data=f"members:{group_id}"),
        ],
        [InlineKeyboardButton(text="🔗 دعوت عضو", callback_data=f"invite:{group_id}")],
        [InlineKeyboardButton(text="🗄 آرشیو حساب", callback_data=f"archive:{group_id}")],
        [InlineKeyboardButton(text="⬅️ حساب‌های من", callback_data="groups:list")],
    ])


def reports_menu(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 بدهکاران / بستانکاران", callback_data=f"report:debts:{group_id}")],
        [InlineKeyboardButton(text="🧾 گزارش کلی هزینه‌ها", callback_data=f"report:expenses:{group_id}")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"group:{group_id}")],
    ])


def category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"expense:category:{key}")]
        for key, label in CATEGORY_LABELS.items()
    ] + [[InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")]])


def split_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚖️ مساوی", callback_data="expense:split:equal")],
        [InlineKeyboardButton(text="📊 درصدی", callback_data="expense:split:percentage")],
        [InlineKeyboardButton(text="🔢 سهمی / وزنی", callback_data="expense:split:shares")],
        [InlineKeyboardButton(text="💵 مبلغ ثابت", callback_data="expense:split:exact")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")],
    ])


def participants_keyboard(members: list[dict], selected: set[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{'✅' if m['user_id'] in selected else '▫️'} {m['display_name']}",
            callback_data=f"expense:participant:{m['user_id']}",
        )]
        for m in members
    ]
    rows += [[InlineKeyboardButton(text="ادامه ➡️", callback_data="expense:participants_done")], [InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def ensure_user(tg_user) -> dict:
    async with api_client() as client:
        r = await client.post("/api/v1/users", json={"telegram_id": tg_user.id, "display_name": tg_user.full_name or str(tg_user.id)})
        r.raise_for_status()
        return r.json()


async def get_group(group_id: int) -> dict:
    async with api_client() as client:
        r = await client.get(f"/api/v1/groups/{group_id}")
        r.raise_for_status()
        return r.json()


async def get_members(group_id: int) -> list[dict]:
    async with api_client() as client:
        r = await client.get(f"/api/v1/groups/{group_id}/members")
        r.raise_for_status()
        return r.json()


async def dashboard_groups(user_id: int, archived: bool = False) -> list[dict]:
    async with api_client() as client:
        r = await client.get(f"/api/v1/dashboard/users/{user_id}/groups", params={"archived": str(archived).lower()})
        r.raise_for_status()
        return r.json()


async def authorize(callback: CallbackQuery, group_id: int) -> dict | None:
    user = await ensure_user(callback.from_user)
    groups = await dashboard_groups(user["id"], archived=False) + await dashboard_groups(user["id"], archived=True)
    if not any(g["id"] == group_id for g in groups):
        await callback.answer("به این حساب دسترسی نداری.", show_alert=True)
        return None
    return user


async def show_groups(target: Message, user_id: int, archived: bool = False):
    groups = await dashboard_groups(user_id, archived=archived)
    title = "🗄 حساب‌های آرشیوشده" if archived else "📂 حساب‌های من"
    if not groups:
        await target.answer(f"{title}\n\nموردی وجود ندارد.", reply_markup=main_keyboard)
        return
    rows = []
    for group in groups:
        role = ROLE_ICON.get(group.get("role"), "👤")
        rows.append([InlineKeyboardButton(text=f"{role} {group['name']}", callback_data=(f"restore:{group['id']}" if archived else f"group:{group['id']}"))])
    await target.answer(title, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def get_payment_profile(user_id: int) -> dict:
    async with api_client() as client:
        r = await client.get(f"/api/v1/product/users/{user_id}/payment-profile")
        r.raise_for_status()
        return r.json()


async def notify_creditor(bot: Bot, group_id: int, settlement: dict, receipt: tuple[str, str] | None = None):
    members = await get_members(group_id)
    names = {m["user_id"]: m["display_name"] for m in members}
    creditor = next((m for m in members if m["user_id"] == settlement["to_user_id"]), None)
    if not creditor or not creditor.get("telegram_id"):
        return
    caption = (
        f"💳 <b>اعلام پرداخت</b>\n\n"
        f"{escape(names.get(settlement['from_user_id'], 'کاربر'))} اعلام کرده "
        f"<b>{fmt_amount(settlement['amount'])} تومان</b> برای شما پرداخت کرده.\n\n"
        "آیا وجه را دریافت کرده‌اید؟"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تأیید دریافت", callback_data=f"settlement:confirm:{group_id}:{settlement['id']}")],
        [InlineKeyboardButton(text="❌ دریافت نکردم", callback_data=f"settlement:reject:{group_id}:{settlement['id']}")],
    ])
    try:
        if receipt:
            kind, file_id = receipt
            if kind == "photo":
                await bot.send_photo(creditor["telegram_id"], file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
            else:
                await bot.send_document(creditor["telegram_id"], file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await bot.send_message(creditor["telegram_id"], caption, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


async def send_debt_reminder(bot: Bot, item: dict, mark: bool = True):
    text = (
        f"🔔 <b>یادآوری پرداخت</b>\n\n"
        f"حساب: <b>{escape(item['group_name'])}</b>\n"
        f"شما <b>{fmt_amount(item['amount'])} تومان</b> به {escape(item['creditor_name'])} بدهکار هستید.\n\n"
        f"{payment_text(item.get('payment'))}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 مشاهده و تسویه", callback_data=f"plan:{item['group_id']}")],
    ])
    await bot.send_message(item["debtor_telegram_id"], text, reply_markup=kb, parse_mode="HTML")
    if mark:
        async with api_client() as client:
            await client.post("/api/v1/product/reminders/sent", json={
                "group_id": item["group_id"],
                "debtor_user_id": item["debtor_user_id"],
                "creditor_user_id": item["creditor_user_id"],
                "amount": item["amount"],
            })


async def reminder_loop(bot: Bot):
    await asyncio.sleep(10)
    while True:
        try:
            async with api_client() as client:
                r = await client.get("/api/v1/product/reminders/due")
                r.raise_for_status()
                items = r.json()
            for item in items:
                try:
                    await send_debt_reminder(bot, item)
                except Exception:
                    continue
        except Exception:
            pass
        await asyncio.sleep(3600)


async def run_bot():
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    bot = Bot(settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart(deep_link=True))
    async def start_invite(message: Message, command: CommandObject):
        user = await ensure_user(message.from_user)
        group_id = parse_join_payload(command.args or "")
        if group_id is None:
            await message.answer("❌ لینک دعوت معتبر نیست.", reply_markup=main_keyboard)
            return
        try:
            group = await get_group(group_id)
            async with api_client() as client:
                r = await client.post(f"/api/v1/groups/{group_id}/members", json={"user_id": user["id"]})
                r.raise_for_status()
            await message.answer(f"✅ به حساب «{escape(group['name'])}» اضافه شدی.", reply_markup=group_menu(group_id), parse_mode="HTML")
            await message.answer("🏠 داشبورد شخصی تو همیشه از این منو در دسترس است.", reply_markup=main_keyboard)
        except httpx.HTTPError:
            await message.answer("❌ این دعوت دیگر در دسترس نیست.", reply_markup=main_keyboard)

    @dp.message(CommandStart())
    async def start(message: Message):
        user = await ensure_user(message.from_user)
        async with api_client() as client:
            r = await client.get(f"/api/v1/dashboard/users/{user['id']}/summary")
            summary = r.json() if r.status_code == 200 else {}
        remaining = summary.get("remaining_free_groups", 0)
        await message.answer(
            f"👋 <b>دنگی - دونگی</b>\n\nخرج‌های مشترک، بدهی‌ها و تسویه‌ها را شفاف مدیریت کن.\n"
            f"سهمیه ساخت حساب رایگان باقی‌مانده: <b>{remaining}</b>",
            reply_markup=main_keyboard,
            parse_mode="HTML",
        )

    @dp.message(Command("cancel"))
    async def cancel(message: Message, state: FSMContext):
        await state.clear()
        await message.answer("عملیات لغو شد.", reply_markup=main_keyboard)

    @dp.callback_query(F.data == "flow:cancel")
    async def cancel_cb(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer("لغو شد")
        await callback.message.answer("عملیات لغو شد.", reply_markup=main_keyboard)

    @dp.message(F.text == "➕ حساب جدید")
    async def new_group(message: Message, state: FSMContext):
        await state.clear()
        await state.set_state(CreateGroupFlow.waiting_name)
        await message.answer("✨ اسم حساب جدید را وارد کن.\nمثال: سفر شمال")

    @dp.message(CreateGroupFlow.waiting_name)
    async def new_group_name(message: Message, state: FSMContext):
        name = (message.text or "").strip()
        if not name:
            await message.answer("اسم حساب نمی‌تواند خالی باشد.")
            return
        user = await ensure_user(message.from_user)
        async with api_client() as client:
            r = await client.post("/api/v1/dashboard/groups", json={"name": name[:120], "owner_user_id": user["id"], "currency": "IRT"})
        if r.status_code == 402:
            await state.clear()
            await message.answer("⭐ سقف حساب‌های رایگان شما تکمیل شده. زیرساخت ارتقا آماده است و پرداخت اشتراک در نسخه تجاری فعال می‌شود.", reply_markup=main_keyboard)
            return
        r.raise_for_status()
        group = r.json()
        await state.clear()
        await message.answer(f"✅ حساب «{escape(group['name'])}» ساخته شد.", reply_markup=group_menu(group["id"]), parse_mode="HTML")

    @dp.message(F.text == "📂 حساب‌های من")
    async def my_groups(message: Message):
        user = await ensure_user(message.from_user)
        await show_groups(message, user["id"])

    @dp.callback_query(F.data == "groups:list")
    async def my_groups_cb(callback: CallbackQuery):
        user = await ensure_user(callback.from_user)
        await callback.answer()
        await show_groups(callback.message, user["id"])

    @dp.message(F.text == "🗄 آرشیو")
    async def archived_groups(message: Message):
        user = await ensure_user(message.from_user)
        await show_groups(message, user["id"], archived=True)

    @dp.callback_query(F.data.startswith("group:"))
    async def open_group(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        group = await get_group(group_id)
        await callback.answer()
        await callback.message.answer(f"💼 <b>{escape(group['name'])}</b>\nیک گزینه را انتخاب کن:", reply_markup=group_menu(group_id), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("archive:"))
    async def archive_group(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await authorize(callback, group_id)
        if not user:
            return
        async with api_client() as client:
            r = await client.patch(f"/api/v1/dashboard/groups/{group_id}/archive", json={"actor_user_id": user["id"], "is_archived": True})
        if r.status_code >= 400:
            await callback.answer("فقط مدیر/مالک می‌تواند آرشیو کند.", show_alert=True)
            return
        await callback.answer("آرشیو شد")
        await callback.message.answer("🗄 حساب آرشیو شد؛ هیچ داده‌ای حذف نشده.", reply_markup=main_keyboard)

    @dp.callback_query(F.data.startswith("restore:"))
    async def restore_group(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await ensure_user(callback.from_user)
        async with api_client() as client:
            r = await client.patch(f"/api/v1/dashboard/groups/{group_id}/archive", json={"actor_user_id": user["id"], "is_archived": False})
        if r.status_code >= 400:
            await callback.answer("امکان بازگردانی نداری.", show_alert=True)
            return
        await callback.answer("بازگردانی شد")
        await callback.message.answer("✅ حساب به فهرست فعال برگشت.", reply_markup=main_keyboard)

    @dp.callback_query(F.data.startswith("invite:"))
    async def invite(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        group = await get_group(group_id)
        me = await bot.get_me()
        await callback.answer()
        await callback.message.answer(
            f"🔗 <b>دعوت به {escape(group['name'])}</b>\n\n<code>https://t.me/{me.username}?start={make_join_payload(group_id)}</code>",
            parse_mode="HTML",
        )

    @dp.callback_query(F.data.startswith("members:"))
    async def members(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        items = await get_members(group_id)
        lines = [f"{ROLE_ICON.get(x['role'], '👤')} {escape(x['display_name'])} — {x['role']}" for x in items]
        await callback.answer()
        await callback.message.answer("👥 <b>اعضا</b>\n\n" + "\n".join(lines), reply_markup=group_menu(group_id), parse_mode="HTML")

    @dp.message(F.text == "⚙️ تنظیمات من")
    async def settings_menu(message: Message):
        user = await ensure_user(message.from_user)
        profile = await get_payment_profile(user["id"])
        await message.answer(
            "⚙️ <b>تنظیمات من</b>\n\n" + payment_text(profile),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 ویرایش اطلاعات پرداخت", callback_data="profile:edit")],
                [InlineKeyboardButton(text=("🔔 یادآوری روشن" if profile.get("reminder_enabled") else "🔕 یادآوری خاموش"), callback_data="profile:toggle_reminder")],
            ]),
            parse_mode="HTML",
        )

    @dp.callback_query(F.data == "profile:edit")
    async def profile_edit(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await state.set_state(PaymentProfileFlow.bank_name)
        await callback.answer()
        await callback.message.answer("🏦 نام بانک را وارد کن. برای رد کردن این مورد، علامت - بفرست.")

    @dp.message(PaymentProfileFlow.bank_name)
    async def profile_bank(message: Message, state: FSMContext):
        await state.update_data(bank_name=None if message.text == "-" else (message.text or "").strip()[:80])
        await state.set_state(PaymentProfileFlow.account_holder)
        await message.answer("👤 نام صاحب حساب را وارد کن یا - بفرست.")

    @dp.message(PaymentProfileFlow.account_holder)
    async def profile_holder(message: Message, state: FSMContext):
        await state.update_data(account_holder=None if message.text == "-" else (message.text or "").strip()[:120])
        await state.set_state(PaymentProfileFlow.card_number)
        await message.answer("💳 شماره کارت را وارد کن یا - بفرست.")

    @dp.message(PaymentProfileFlow.card_number)
    async def profile_card(message: Message, state: FSMContext):
        await state.update_data(card_number=None if message.text == "-" else (message.text or "").replace(" ", "").replace("-", "")[:32])
        await state.set_state(PaymentProfileFlow.iban)
        await message.answer("🔢 شماره شبا را وارد کن یا - بفرست.")

    @dp.message(PaymentProfileFlow.iban)
    async def profile_iban(message: Message, state: FSMContext):
        await state.update_data(iban=None if message.text == "-" else (message.text or "").replace(" ", "").upper()[:40])
        await state.set_state(PaymentProfileFlow.account_number)
        await message.answer("🏧 شماره حساب را وارد کن یا - بفرست.")

    @dp.message(PaymentProfileFlow.account_number)
    async def profile_account(message: Message, state: FSMContext):
        user = await ensure_user(message.from_user)
        data = await state.get_data()
        data["account_number"] = None if message.text == "-" else (message.text or "").replace(" ", "")[:40]
        current = await get_payment_profile(user["id"])
        data["reminder_enabled"] = current.get("reminder_enabled", True)
        async with api_client() as client:
            r = await client.put(f"/api/v1/product/users/{user['id']}/payment-profile", json=data)
            r.raise_for_status()
            profile = r.json()
        await state.clear()
        await message.answer("✅ اطلاعات پرداخت ذخیره شد.\n\n" + payment_text(profile), reply_markup=main_keyboard, parse_mode="HTML")

    @dp.callback_query(F.data == "profile:toggle_reminder")
    async def toggle_reminder(callback: CallbackQuery):
        user = await ensure_user(callback.from_user)
        profile = await get_payment_profile(user["id"])
        profile["reminder_enabled"] = not profile.get("reminder_enabled", True)
        payload = {k: profile.get(k) for k in ("bank_name", "account_holder", "card_number", "iban", "account_number", "reminder_enabled")}
        async with api_client() as client:
            r = await client.put(f"/api/v1/product/users/{user['id']}/payment-profile", json=payload)
            r.raise_for_status()
        await callback.answer("تنظیم شد")
        await callback.message.answer("🔔 تنظیم یادآوری به‌روزرسانی شد.", reply_markup=main_keyboard)

    @dp.callback_query(F.data.startswith("reports:"))
    async def reports(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        await callback.answer()
        await callback.message.answer("📊 <b>گزارش‌های حساب</b>\nگزارش موردنظر را انتخاب کن:", reply_markup=reports_menu(group_id), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("report:debts:"))
    async def debt_report(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[2])
        user = await authorize(callback, group_id)
        if not user:
            return
        async with api_client() as client:
            r = await client.get(f"/api/v1/product/groups/{group_id}/reports/debts", params={"actor_user_id": user["id"]})
            r.raise_for_status()
            report = r.json()
        balances = report["balances"]
        debtors = [x for x in balances if x["status"] == "debtor"]
        creditors = [x for x in balances if x["status"] == "creditor"]
        lines = ["🔴 <b>بدهکاران</b>"] + ([f"• {escape(x['display_name'])}: {fmt_amount(abs(Decimal(x['balance'])))} تومان" for x in debtors] or ["• ندارد"])
        lines += ["", "🟢 <b>بستانکاران</b>"] + ([f"• {escape(x['display_name'])}: {fmt_amount(x['balance'])} تومان" for x in creditors] or ["• ندارد"])
        if report["transfers"]:
            lines += ["", "↔️ <b>مسیر پیشنهادی تسویه</b>"] + [f"• {escape(x['from_name'])} → {escape(x['to_name'])}: {fmt_amount(x['amount'])} تومان" for x in report["transfers"]]
        await callback.answer()
        await callback.message.answer("\n".join(lines), reply_markup=reports_menu(group_id), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("report:expenses:"))
    async def expense_report(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[2])
        user = await authorize(callback, group_id)
        if not user:
            return
        async with api_client() as client:
            r = await client.get(f"/api/v1/product/groups/{group_id}/reports/expenses", params={"actor_user_id": user["id"]})
            r.raise_for_status()
            report = r.json()
        lines = [
            "🧾 <b>گزارش کلی هزینه‌ها</b>",
            "",
            f"💰 مجموع: <b>{fmt_amount(report['total_amount'])} تومان</b>",
            f"🧮 تعداد هزینه‌ها: {report['expense_count']}",
            "",
            "📂 <b>تفکیک دسته‌بندی</b>",
        ]
        for item in report["categories"]:
            lines.append(f"• {CATEGORY_LABELS.get(item['category'], '📦 سایر')}: {fmt_amount(item['amount'])} تومان ({item['count']} مورد)")
        if not report["categories"]:
            lines.append("• هنوز هزینه‌ای ثبت نشده")
        await callback.answer()
        await callback.message.answer("\n".join(lines), reply_markup=reports_menu(group_id), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("expense:new:"))
    async def expense_start(callback: CallbackQuery, state: FSMContext):
        group_id = int(callback.data.split(":")[2])
        user = await authorize(callback, group_id)
        if not user:
            return
        await state.clear()
        await state.update_data(group_id=group_id, actor_user_id=user["id"])
        await state.set_state(ExpenseFlow.amount)
        await callback.answer()
        await callback.message.answer("💰 مبلغ هزینه را به تومان وارد کن.")

    @dp.message(ExpenseFlow.amount)
    async def expense_amount(message: Message, state: FSMContext):
        try:
            amount = parse_number(message.text or "")
        except ValueError:
            await message.answer("❌ مبلغ معتبر وارد کن.")
            return
        await state.update_data(amount=str(amount))
        await state.set_state(ExpenseFlow.title)
        await message.answer("📝 این هزینه بابت چه بوده؟")

    @dp.message(ExpenseFlow.title)
    async def expense_title(message: Message, state: FSMContext):
        title = (message.text or "").strip()
        if not title:
            await message.answer("عنوان نمی‌تواند خالی باشد.")
            return
        await state.update_data(title=title[:160])
        await state.set_state(ExpenseFlow.category)
        await message.answer("📂 دسته‌بندی هزینه را انتخاب کن:", reply_markup=category_keyboard())

    @dp.callback_query(ExpenseFlow.category, F.data.startswith("expense:category:"))
    async def expense_category(callback: CallbackQuery, state: FSMContext):
        category = callback.data.split(":")[2]
        data = await state.get_data()
        members = await get_members(data["group_id"])
        await state.update_data(category=category)
        await state.set_state(ExpenseFlow.payer)
        await callback.answer()
        await callback.message.answer("💳 چه کسی پرداخت کرده؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=m["display_name"], callback_data=f"expense:payer:{m['user_id']}")] for m in members
        ]))

    @dp.callback_query(ExpenseFlow.payer, F.data.startswith("expense:payer:"))
    async def expense_payer(callback: CallbackQuery, state: FSMContext):
        payer_id = int(callback.data.split(":")[2])
        data = await state.get_data()
        members = await get_members(data["group_id"])
        ids = {m["user_id"] for m in members}
        if payer_id not in ids:
            await callback.answer("پرداخت‌کننده معتبر نیست.", show_alert=True)
            return
        await state.update_data(paid_by_user_id=payer_id, participant_user_ids=sorted(ids))
        await state.set_state(ExpenseFlow.participants)
        await callback.answer()
        await callback.message.answer("👥 هزینه بین چه کسانی تقسیم شود؟", reply_markup=participants_keyboard(members, ids))

    @dp.callback_query(ExpenseFlow.participants, F.data.startswith("expense:participant:"))
    async def toggle_participant(callback: CallbackQuery, state: FSMContext):
        uid = int(callback.data.split(":")[2])
        data = await state.get_data()
        selected = set(data.get("participant_user_ids", []))
        selected.remove(uid) if uid in selected else selected.add(uid)
        await state.update_data(participant_user_ids=sorted(selected))
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=participants_keyboard(await get_members(data["group_id"]), selected))

    @dp.callback_query(ExpenseFlow.participants, F.data == "expense:participants_done")
    async def participants_done(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        if not data.get("participant_user_ids"):
            await callback.answer("حداقل یک نفر را انتخاب کن.", show_alert=True)
            return
        await state.set_state(ExpenseFlow.split_mode)
        await callback.answer()
        await callback.message.answer("⚖️ روش تقسیم را انتخاب کن:", reply_markup=split_keyboard())

    async def submit_expense(target: Message, state: FSMContext):
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
        }
        async with api_client() as client:
            r = await client.post(f"/api/v1/groups/{data['group_id']}/expenses", json=payload)
        if r.status_code >= 400:
            await target.answer(f"❌ ثبت هزینه انجام نشد: {r.text[:180]}")
            return
        group_id = data["group_id"]
        expense = r.json()
        await state.clear()
        await target.answer(
            f"✅ هزینه ثبت شد.\n📝 {escape(expense['title'])}\n💰 {fmt_amount(expense['amount'])} تومان\n{CATEGORY_LABELS.get(data.get('category'), '📦 سایر')}",
            reply_markup=group_menu(group_id),
            parse_mode="HTML",
        )

    @dp.callback_query(ExpenseFlow.split_mode, F.data.startswith("expense:split:"))
    async def expense_split(callback: CallbackQuery, state: FSMContext):
        mode = callback.data.split(":")[2]
        await state.update_data(split_mode=mode, split_values=None)
        if mode == "equal":
            await callback.answer()
            await submit_expense(callback.message, state)
            return
        await state.update_data(split_index=0, split_values={})
        await state.set_state(ExpenseFlow.split_value)
        await callback.answer()
        await prompt_split_value(callback.message, state)

    async def prompt_split_value(message: Message, state: FSMContext):
        data = await state.get_data()
        idx = data.get("split_index", 0)
        ids = data["participant_user_ids"]
        names = {m["user_id"]: m["display_name"] for m in await get_members(data["group_id"])}
        unit = {"percentage": "درصد", "shares": "سهم", "exact": "تومان"}[data["split_mode"]]
        await message.answer(f"مقدار {unit} برای «{escape(names.get(ids[idx], 'کاربر'))}» را وارد کن:", parse_mode="HTML")

    @dp.message(ExpenseFlow.split_value)
    async def expense_split_value(message: Message, state: FSMContext):
        try:
            value = parse_number(message.text or "")
        except ValueError:
            await message.answer("عدد مثبت و معتبر وارد کن.")
            return
        data = await state.get_data()
        ids = data["participant_user_ids"]
        idx = data.get("split_index", 0)
        values = dict(data.get("split_values") or {})
        values[str(ids[idx])] = str(value)
        idx += 1
        await state.update_data(split_values=values, split_index=idx)
        if idx < len(ids):
            await prompt_split_value(message, state)
            return
        if data["split_mode"] == "percentage" and sum(Decimal(v) for v in values.values()) != Decimal("100"):
            await state.update_data(split_values={}, split_index=0)
            await message.answer("❌ مجموع درصدها باید دقیقاً 100 باشد. دوباره وارد کن.")
            await prompt_split_value(message, state)
            return
        if data["split_mode"] == "exact" and sum(Decimal(v) for v in values.values()) != Decimal(data["amount"]):
            await state.update_data(split_values={}, split_index=0)
            await message.answer("❌ مجموع مبلغ‌های ثابت باید دقیقاً برابر کل هزینه باشد. دوباره وارد کن.")
            await prompt_split_value(message, state)
            return
        await submit_expense(message, state)

    @dp.callback_query(F.data.startswith("plan:"))
    async def plan(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await authorize(callback, group_id)
        if not user:
            return
        members = await get_members(group_id)
        names = {m["user_id"]: m["display_name"] for m in members}
        async with api_client() as client:
            r = await client.get(f"/api/v1/groups/{group_id}/settlement-plan")
            r.raise_for_status()
            items = r.json()
        if not items:
            await callback.answer()
            await callback.message.answer("✅ این حساب کاملاً تسویه است.", reply_markup=group_menu(group_id))
            return
        lines = [f"• {escape(names.get(x['from_user_id'], 'کاربر'))} → {escape(names.get(x['to_user_id'], 'کاربر'))}: <b>{fmt_amount(x['amount'])} تومان</b>" for x in items]
        buttons = []
        for x in items:
            if x["from_user_id"] == user["id"]:
                profile = await get_payment_profile(x["to_user_id"])
                label = f"💸 پرداخت به {names.get(x['to_user_id'], 'طلبکار')}"
                buttons.append([InlineKeyboardButton(text=label, callback_data=f"settle:prepare:{group_id}:{x['from_user_id']}:{x['to_user_id']}:{x['amount']}")])
                if profile.get("card_number"):
                    buttons.append([InlineKeyboardButton(text="📋 نمایش شماره کارت", callback_data=f"payinfo:{x['to_user_id']}")])
        buttons.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"group:{group_id}")])
        await callback.answer()
        await callback.message.answer("💳 <b>پیشنهاد تسویه</b>\n\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("payinfo:"))
    async def payinfo(callback: CallbackQuery):
        user_id = int(callback.data.split(":")[1])
        profile = await get_payment_profile(user_id)
        await callback.answer()
        await callback.message.answer("💳 <b>اطلاعات پرداخت</b>\n\n" + payment_text(profile) + "\n\nبرای کپی، روی مقدار داخل کادر لمس/نگه‌دار.", parse_mode="HTML")

    @dp.callback_query(F.data.startswith("settle:prepare:"))
    async def settle_prepare(callback: CallbackQuery, state: FSMContext):
        _, _, group_raw, from_raw, to_raw, amount = callback.data.split(":", 5)
        user = await authorize(callback, int(group_raw))
        if not user or user["id"] != int(from_raw):
            return
        await state.clear()
        await state.update_data(group_id=int(group_raw), from_user_id=int(from_raw), to_user_id=int(to_raw), amount=amount, actor_user_id=user["id"])
        await callback.answer()
        await callback.message.answer(
            "پرداخت را انجام دادی؟ می‌توانی رسید را هم اختیاری بفرستی.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🧾 ارسال رسید", callback_data="settle:with_receipt")],
                [InlineKeyboardButton(text="✅ بدون رسید، پرداخت کردم", callback_data="settle:no_receipt")],
                [InlineKeyboardButton(text="❌ انصراف", callback_data="flow:cancel")],
            ]),
        )

    async def create_settlement_from_state(state: FSMContext) -> dict:
        data = await state.get_data()
        async with api_client() as client:
            r = await client.post(f"/api/v1/groups/{data['group_id']}/settlements", json={
                "actor_user_id": data["actor_user_id"],
                "from_user_id": data["from_user_id"],
                "to_user_id": data["to_user_id"],
                "amount": data["amount"],
            })
            r.raise_for_status()
            return r.json()

    @dp.callback_query(F.data == "settle:no_receipt")
    async def settle_no_receipt(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        if not data.get("group_id"):
            await callback.answer("جلسه منقضی شده.", show_alert=True)
            return
        settlement = await create_settlement_from_state(state)
        await notify_creditor(bot, data["group_id"], settlement)
        group_id = data["group_id"]
        await state.clear()
        await callback.answer("ثبت شد")
        await callback.message.answer("⏳ پرداخت اعلام شد و منتظر تأیید بستانکار است.", reply_markup=group_menu(group_id))

    @dp.callback_query(F.data == "settle:with_receipt")
    async def settle_with_receipt(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        if not data.get("group_id"):
            await callback.answer("جلسه منقضی شده.", show_alert=True)
            return
        await state.set_state(ReceiptFlow.waiting_receipt)
        await callback.answer()
        await callback.message.answer("🧾 عکس یا فایل رسید را ارسال کن. برای لغو /cancel")

    @dp.message(ReceiptFlow.waiting_receipt, F.photo | F.document)
    async def receive_receipt(message: Message, state: FSMContext):
        data = await state.get_data()
        settlement = await create_settlement_from_state(state)
        if message.photo:
            kind, file_id = "photo", message.photo[-1].file_id
        else:
            kind, file_id = "document", message.document.file_id
        async with api_client() as client:
            r = await client.post(f"/api/v1/product/groups/{data['group_id']}/settlements/{settlement['id']}/receipt", json={
                "actor_user_id": data["actor_user_id"], "receipt_file_id": file_id, "receipt_kind": kind,
            })
            r.raise_for_status()
        await notify_creditor(bot, data["group_id"], settlement, receipt=(kind, file_id))
        group_id = data["group_id"]
        await state.clear()
        await message.answer("✅ رسید و اعلام پرداخت برای بستانکار ارسال شد. منتظر تأیید او هستیم.", reply_markup=group_menu(group_id))

    @dp.message(ReceiptFlow.waiting_receipt)
    async def invalid_receipt(message: Message):
        await message.answer("لطفاً رسید را به‌صورت عکس یا فایل ارسال کن؛ یا /cancel بزن.")

    @dp.callback_query(F.data.startswith("settlement:confirm:"))
    async def confirm_settlement(callback: CallbackQuery):
        _, _, group_raw, settlement_raw = callback.data.split(":")
        group_id, settlement_id = int(group_raw), int(settlement_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        async with api_client() as client:
            r = await client.post(f"/api/v1/groups/{group_id}/settlements/{settlement_id}/confirm", json={"actor_user_id": user["id"]})
        if r.status_code >= 400:
            await callback.answer("این درخواست قابل تأیید نیست.", show_alert=True)
            return
        st = r.json()
        members = await get_members(group_id)
        debtor = next((m for m in members if m["user_id"] == st["from_user_id"]), None)
        async with api_client() as client:
            plan_r = await client.get(f"/api/v1/groups/{group_id}/settlement-plan")
            remaining = plan_r.json() if plan_r.status_code == 200 else []
        if debtor and debtor.get("telegram_id"):
            extra = "\n🎉 حساب شما در این گروه کاملاً تسویه شد." if not remaining else ("\n✨ فقط یک تسویه تا صفر شدن حساب باقی مانده." if len(remaining) == 1 else "")
            try:
                await bot.send_message(debtor["telegram_id"], f"✅ پرداخت {fmt_amount(st['amount'])} تومان توسط بستانکار تأیید شد.{extra}")
            except Exception:
                pass
        await callback.answer("تأیید شد")
        await callback.message.answer("✅ دریافت وجه تأیید شد و مانده حساب به‌روزرسانی شد.", reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("settlement:reject:"))
    async def reject_settlement(callback: CallbackQuery):
        _, _, group_raw, settlement_raw = callback.data.split(":")
        group_id, settlement_id = int(group_raw), int(settlement_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        async with api_client() as client:
            r = await client.post(f"/api/v1/groups/{group_id}/settlements/{settlement_id}/reject", json={"actor_user_id": user["id"]})
        if r.status_code >= 400:
            await callback.answer("این درخواست قابل رد نیست.", show_alert=True)
            return
        st = r.json()
        members = await get_members(group_id)
        debtor = next((m for m in members if m["user_id"] == st["from_user_id"]), None)
        if debtor and debtor.get("telegram_id"):
            try:
                await bot.send_message(debtor["telegram_id"], f"❌ اعلام پرداخت {fmt_amount(st['amount'])} تومان توسط بستانکار تأیید نشد.")
            except Exception:
                pass
        await callback.answer("رد شد")
        await callback.message.answer("❌ دریافت وجه رد شد و مانده تغییری نکرد.", reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("pending:"))
    async def pending(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await authorize(callback, group_id)
        if not user:
            return
        members = await get_members(group_id)
        names = {m["user_id"]: m["display_name"] for m in members}
        async with api_client() as client:
            r = await client.get(f"/api/v1/groups/{group_id}/settlements/pending", params={"actor_user_id": user["id"]})
            r.raise_for_status()
            items = r.json()
        if not items:
            await callback.answer()
            await callback.message.answer("⏳ تسویه منتظر تأییدی نداری.", reply_markup=group_menu(group_id))
            return
        lines, buttons = [], []
        for st in items:
            lines.append(f"• {escape(names.get(st['from_user_id'], 'کاربر'))} → {escape(names.get(st['to_user_id'], 'کاربر'))}: {fmt_amount(st['amount'])} تومان")
            if st["to_user_id"] == user["id"]:
                buttons.append([
                    InlineKeyboardButton(text="✅ تأیید", callback_data=f"settlement:confirm:{group_id}:{st['id']}"),
                    InlineKeyboardButton(text="❌ رد", callback_data=f"settlement:reject:{group_id}:{st['id']}"),
                ])
        buttons.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"group:{group_id}")])
        await callback.answer()
        await callback.message.answer("⏳ <b>تسویه‌های منتظر</b>\n\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("remind:"))
    async def manual_remind(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        if not await authorize(callback, group_id):
            return
        async with api_client() as client:
            r = await client.get("/api/v1/product/reminders/due", params={"force": "true"})
            r.raise_for_status()
            items = [x for x in r.json() if x["group_id"] == group_id]
        sent = 0
        for item in items:
            try:
                await send_debt_reminder(bot, item)
                sent += 1
            except Exception:
                pass
        await callback.answer("ارسال شد")
        await callback.message.answer(f"🔔 یادآوری برای {sent} بدهکار ارسال شد.", reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("history:"))
    async def history(callback: CallbackQuery):
        group_id = int(callback.data.split(":")[1])
        user = await authorize(callback, group_id)
        if not user:
            return
        members = await get_members(group_id)
        current = next((m for m in members if m["user_id"] == user["id"]), None)
        manager = bool(current and current["role"] in {"owner", "admin"})
        async with api_client() as client:
            r = await client.get(f"/api/v1/groups/{group_id}/expenses", params={"limit": 20})
            r.raise_for_status()
            items = r.json()
        if not items:
            await callback.answer()
            await callback.message.answer("📜 هنوز هزینه‌ای ثبت نشده.", reply_markup=group_menu(group_id))
            return
        lines = [f"• #{x['id']} {escape(x['title'])} — {fmt_amount(x['amount'])} تومان — {CATEGORY_LABELS.get(x.get('category'), '📦 سایر')}" for x in items]
        buttons = []
        for x in items:
            if manager or x.get("created_by_user_id") == user["id"]:
                buttons.append([
                    InlineKeyboardButton(text=f"✏️ #{x['id']}", callback_data=f"edit:{group_id}:{x['id']}"),
                    InlineKeyboardButton(text=f"🗑 #{x['id']}", callback_data=f"delete:ask:{group_id}:{x['id']}"),
                ])
        buttons.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"group:{group_id}")])
        await callback.answer()
        await callback.message.answer("📜 <b>۲۰ هزینه آخر</b>\n\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("edit:"))
    async def edit_menu(callback: CallbackQuery):
        _, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        await callback.answer()
        await callback.message.answer("✏️ چه چیزی ویرایش شود؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 عنوان", callback_data=f"editfield:title:{group_id}:{expense_id}")],
            [InlineKeyboardButton(text="💰 مبلغ", callback_data=f"editfield:amount:{group_id}:{expense_id}")],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"history:{group_id}")],
        ]))

    @dp.callback_query(F.data.startswith("editfield:"))
    async def edit_field(callback: CallbackQuery, state: FSMContext):
        _, field, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        async with api_client() as client:
            r = await client.get(f"/api/v1/groups/{group_id}/expenses/{expense_id}", params={"actor_user_id": user["id"]})
            r.raise_for_status()
            expense = r.json()
        await state.clear()
        await state.update_data(field=field, group_id=group_id, expense_id=expense_id, actor_user_id=user["id"], expense=expense)
        await state.set_state(EditExpenseFlow.waiting_value)
        await callback.answer()
        await callback.message.answer("مقدار جدید را وارد کن:")

    @dp.message(EditExpenseFlow.waiting_value)
    async def edit_value(message: Message, state: FSMContext):
        data = await state.get_data()
        expense = data["expense"]
        field = data["field"]
        if field == "amount":
            try:
                new_value = str(parse_number(message.text or ""))
            except ValueError:
                await message.answer("مبلغ معتبر وارد کن.")
                return
            amount = new_value
            title = expense["title"]
        else:
            title = (message.text or "").strip()[:160]
            if not title:
                await message.answer("عنوان خالی نباشد.")
                return
            amount = expense["amount"]
        split_mode = expense.get("split_mode", "equal")
        split_values = expense.get("split_values")
        if field == "amount" and split_mode == "exact":
            split_mode, split_values = "equal", None
        payload = {
            "actor_user_id": data["actor_user_id"],
            "paid_by_user_id": expense["paid_by_user_id"],
            "amount": amount,
            "title": title,
            "participant_user_ids": expense["participant_user_ids"],
            "split_mode": split_mode,
            "split_values": split_values,
            "category": expense.get("category"),
            "note": expense.get("note"),
        }
        async with api_client() as client:
            r = await client.put(f"/api/v1/groups/{data['group_id']}/expenses/{data['expense_id']}", json=payload)
        if r.status_code >= 400:
            await message.answer("❌ ویرایش انجام نشد.")
            return
        group_id = data["group_id"]
        await state.clear()
        await message.answer("✅ هزینه ویرایش شد.", reply_markup=group_menu(group_id))

    @dp.callback_query(F.data.startswith("delete:ask:"))
    async def delete_ask(callback: CallbackQuery):
        _, _, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        if not await authorize(callback, group_id):
            return
        await callback.answer()
        await callback.message.answer(f"⚠️ هزینه #{expense_id} حذف شود؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 حذف قطعی", callback_data=f"delete:yes:{group_id}:{expense_id}")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data=f"history:{group_id}")],
        ]))

    @dp.callback_query(F.data.startswith("delete:yes:"))
    async def delete_yes(callback: CallbackQuery):
        _, _, group_raw, expense_raw = callback.data.split(":")
        group_id, expense_id = int(group_raw), int(expense_raw)
        user = await authorize(callback, group_id)
        if not user:
            return
        async with api_client() as client:
            r = await client.request("DELETE", f"/api/v1/groups/{group_id}/expenses/{expense_id}", json={"actor_user_id": user["id"]})
        if r.status_code >= 400:
            await callback.answer("حذف انجام نشد.", show_alert=True)
            return
        await callback.answer("حذف شد")
        await callback.message.answer("✅ هزینه حذف شد.", reply_markup=group_menu(group_id))

    @dp.message(F.text == "🔔 اعلان‌ها")
    async def notifications(message: Message):
        user = await ensure_user(message.from_user)
        async with api_client() as client:
            r = await client.get(f"/api/v1/dashboard/users/{user['id']}/notifications")
            r.raise_for_status()
            items = r.json()
        if not items:
            await message.answer("🔔 اعلان فعالی نداری.", reply_markup=main_keyboard)
            return
        lines = [f"• تسویه #{x['settlement_id']} — {fmt_amount(x['amount'])} تومان" for x in items]
        await message.answer("🔔 <b>اعلان‌ها</b>\n\n" + "\n".join(lines), reply_markup=main_keyboard, parse_mode="HTML")

    @dp.message(F.text == "❓ راهنما")
    async def help_msg(message: Message):
        await message.answer(
            "❓ <b>راهنمای سریع دنگی - دونگی</b>\n\n"
            "1) حساب بساز یا با لینک دعوت عضو شو.\n"
            "2) هزینه را با دسته‌بندی و روش تقسیم ثبت کن.\n"
            "3) از گزارش‌ها بدهکاران/بستانکاران و هزینه‌ها را ببین.\n"
            "4) بدهکار «پرداخت کردم» می‌زند و رسید می‌تواند اختیاری باشد.\n"
            "5) فقط بعد از تأیید بستانکار، مانده حساب تغییر می‌کند.\n"
            "6) اطلاعات کارت/شبا را در تنظیمات من ثبت کن تا همراه یادآوری نمایش داده شود.",
            reply_markup=main_keyboard,
            parse_mode="HTML",
        )

    reminder_task = asyncio.create_task(reminder_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
