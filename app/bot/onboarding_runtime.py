from __future__ import annotations

from html import escape

from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

_INSTALLED = False


def _welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ ساخت اولین حساب", callback_data="onboard:create")],
        [InlineKeyboardButton(text="👀 اول ببین چطور کار می‌کند", callback_data="onboard:tour:1")],
        [InlineKeyboardButton(text="📂 حساب‌های من", callback_data="groups:list")],
    ])


def _tour_keyboard(step: int) -> InlineKeyboardMarkup:
    if step == 1:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="بعدی ۲/۳ ›", callback_data="onboard:tour:2")],
            [InlineKeyboardButton(text="🚀 ساخت حساب", callback_data="onboard:create")],
            [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="onboard:home")],
        ])
    if step == 2:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="‹ قبلی", callback_data="onboard:tour:1"), InlineKeyboardButton(text="بعدی ۳/۳ ›", callback_data="onboard:tour:3")],
            [InlineKeyboardButton(text="🚀 ساخت حساب", callback_data="onboard:create")],
            [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="onboard:home")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ قبلی", callback_data="onboard:tour:2")],
        [InlineKeyboardButton(text="🚀 حالا حساب خودم را بساز", callback_data="onboard:create")],
        [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="onboard:home")],
    ])


def install(module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    previous_show_groups = module.show_groups

    async def show_groups(target: Message, user_id: int, archived: bool = False):
        groups = await module.dashboard_groups(user_id, archived=archived)
        if groups or archived:
            return await previous_show_groups(target, user_id, archived=archived)
        await target.answer(
            "📂 <b>هنوز حسابی نداری</b>\n\n"
            "برای شروع یک حساب بساز؛ مثلاً «سفر شمال»، «خانه» یا «دورهمی دوستان».\n"
            "بعد می‌توانی اعضا را دعوت کنی و هزینه‌ها را ثبت کنی.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ ساخت اولین حساب", callback_data="onboard:create")],
                [InlineKeyboardButton(text="👀 آموزش ۳۰ ثانیه‌ای", callback_data="onboard:tour:1")],
            ]),
            parse_mode="HTML",
        )

    module.show_groups = show_groups

    async def render_home(message: Message, user: dict):
        active = await module.dashboard_groups(user["id"], archived=False)
        archived = await module.dashboard_groups(user["id"], archived=True)
        if not active and not archived:
            await message.answer(
                "👋 <b>به دنگی - دونگی خوش اومدی</b>\n\n"
                "خرج‌های مشترک را ثبت کن، سهم هر نفر را حساب کن و دقیق ببین چه کسی به چه کسی بدهکار است.\n\n"
                "برای شروع یکی از گزینه‌های زیر را انتخاب کن 👇",
                reply_markup=_welcome_keyboard(),
                parse_mode="HTML",
            )
            return
        async with module.api_client() as client:
            r = await client.get(f"/api/v1/dashboard/users/{user['id']}/summary")
            summary = r.json() if r.status_code == 200 else {}
        remaining = summary.get("remaining_free_groups", 0)
        await message.answer(
            f"🏠 <b>دنگی - دونگی</b>\n\n"
            f"{len(active)} حساب فعال داری. یک حساب را انتخاب کن یا حساب جدید بساز.\n"
            f"سهمیه ساخت حساب رایگان باقی‌مانده: <b>{remaining}</b>",
            reply_markup=module.main_keyboard,
            parse_mode="HTML",
        )

    async def render_group(callback: CallbackQuery, group_id: int):
        user = await module.authorize(callback, group_id)
        if not user:
            return
        group = await module.get_group(group_id)
        members = await module.get_members(group_id)
        async with module.api_client() as client:
            r = await client.get(f"/api/v1/groups/{group_id}/expenses", params={"limit": 1})
            expenses = r.json() if r.status_code == 200 else []
        member_done = len(members) > 1
        expense_done = bool(expenses)
        completed = 1 + int(member_done) + int(expense_done)
        checklist = ""
        if completed < 3:
            checklist = (
                "\n\n🚀 <b>راه‌اندازی حساب</b>\n"
                "✅ حساب ساخته شد\n"
                f"{'✅' if member_done else '⬜'} حداقل یک نفر را دعوت کن\n"
                f"{'✅' if expense_done else '⬜'} اولین هزینه را ثبت کن\n"
                f"\n{completed}/3 تکمیل شده"
            )
        await callback.answer()
        await callback.message.answer(
            f"💼 <b>{escape(group['name'])}</b>{checklist}\n\nیک گزینه را انتخاب کن:",
            reply_markup=module.group_menu(group_id),
            parse_mode="HTML",
        )

    class OnboardingMiddleware(BaseMiddleware):
        async def __call__(self, handler, event, data):
            if isinstance(event, Message):
                text = (event.text or "").strip()
                if text == "/start":
                    user = await module.ensure_user(event.from_user)
                    await render_home(event, user)
                    return None
                if text == "❓ راهنما":
                    await event.answer(
                        "❓ <b>راهنمای دنگی - دونگی</b>\n\n"
                        "اگر اولین بار است اینجایی، آموزش کوتاه را ببین؛ کمتر از یک دقیقه طول می‌کشد.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="👀 آموزش ۳۰ ثانیه‌ای", callback_data="onboard:tour:1")],
                            [InlineKeyboardButton(text="➕ ساخت حساب", callback_data="onboard:create")],
                            [InlineKeyboardButton(text="📂 حساب‌های من", callback_data="groups:list")],
                        ]),
                        parse_mode="HTML",
                    )
                    return None
            if isinstance(event, CallbackQuery):
                raw = event.data or ""
                if raw.startswith("onboard:"):
                    if raw == "onboard:create":
                        await data["state"].clear()
                        await data["state"].set_state(module.CreateGroupFlow.waiting_name)
                        await event.answer()
                        await event.message.answer("✨ اسم اولین حساب را وارد کن.\nمثال: سفر شمال")
                        return None
                    if raw == "onboard:home":
                        user = await module.ensure_user(event.from_user)
                        await event.answer()
                        await render_home(event.message, user)
                        return None
                    if raw.startswith("onboard:tour:"):
                        step = int(raw.rsplit(":", 1)[1])
                        texts = {
                            1: "1️⃣ <b>حساب بساز</b>\n\nمثلاً «سفر کیش». هر سفر، خانه یا جمع دوستان می‌تواند یک حساب جدا داشته باشد.",
                            2: "2️⃣ <b>هزینه ثبت کن</b>\n\nمثلاً علی ۲,۰۰۰,۰۰۰ تومان برای شام پرداخت کرده. اعضا و روش تقسیم را انتخاب کن؛ محاسبه با دنگی - دونگی است.\n\n💡 مطمئن نیستی؟ «مساوی» معمولاً بهترین انتخاب است.",
                            3: "3️⃣ <b>تسویه کنید</b>\n\nربات مشخص می‌کند چه کسی باید به چه کسی پرداخت کند. بدهکار «پرداخت کردم» می‌زند و بعد از تأیید بستانکار، تسویه نهایی می‌شود.",
                        }
                        await event.answer()
                        await event.message.answer(texts[step], reply_markup=_tour_keyboard(step), parse_mode="HTML")
                        return None
                if raw.startswith("group:"):
                    parts = raw.split(":")
                    if len(parts) == 2 and parts[1].isdigit():
                        await render_group(event, int(parts[1]))
                        return None
            return await handler(event, data)

    original_start_polling = Dispatcher.start_polling

    async def start_polling_onboarding(self: Dispatcher, *bots, **kwargs):
        if not getattr(self, "_dangi_onboarding_handlers", False):
            self._dangi_onboarding_handlers = True
            self.message.outer_middleware(OnboardingMiddleware())
            self.callback_query.outer_middleware(OnboardingMiddleware())
        return await original_start_polling(self, *bots, **kwargs)

    Dispatcher.start_polling = start_polling_onboarding
