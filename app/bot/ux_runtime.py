from __future__ import annotations

from aiogram import BaseMiddleware, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup


_LAST_PANEL: dict[int, int] = {}
_INSTALLED = False


def _has_button(markup: InlineKeyboardMarkup | None, text: str) -> bool:
    if not markup:
        return False
    return any(button.text == text for row in markup.inline_keyboard for button in row)


def _with_nav(markup: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup | None:
    if markup is None:
        return None
    rows = [list(row) for row in markup.inline_keyboard]
    nav = []
    if not _has_button(markup, "⬅️ برگشت") and not _has_button(markup, "⬅️ بازگشت"):
        nav.append(InlineKeyboardButton(text="⬅️ برگشت", callback_data="ux:back"))
    if not _has_button(markup, "🏠 منوی اصلی"):
        nav.append(InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="ux:home"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_persistent_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ حساب جدید"), KeyboardButton(text="📂 حساب‌های من")],
            [KeyboardButton(text="🔔 اعلان‌ها"), KeyboardButton(text="⚙️ تنظیمات من")],
            [KeyboardButton(text="🗄 آرشیو"), KeyboardButton(text="❓ راهنما")],
            [KeyboardButton(text="⬅️ برگشت"), KeyboardButton(text="🏠 منوی اصلی")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


async def _safe_delete(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


def install(module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    module.main_keyboard = build_persistent_keyboard()
    original_answer = Message.answer

    async def clean_answer(self: Message, text, *args, **kwargs):
        chat_id = self.chat.id
        bot = self.bot
        await _safe_delete(bot, chat_id, self.message_id)
        previous = _LAST_PANEL.get(chat_id)
        if previous and previous != self.message_id:
            await _safe_delete(bot, chat_id, previous)

        markup = kwargs.get("reply_markup")
        if isinstance(markup, InlineKeyboardMarkup):
            kwargs["reply_markup"] = _with_nav(markup)

        result = await original_answer(self, text, *args, **kwargs)
        _LAST_PANEL[chat_id] = result.message_id
        return result

    Message.answer = clean_answer

    async def show_home(target: Message, state: FSMContext):
        await state.clear()
        await target.answer(
            "🏠 <b>منوی اصلی</b>\n\nاز اینجا می‌تونی حساب‌ها، اعلان‌ها و تنظیماتت رو مدیریت کنی.",
            reply_markup=module.main_keyboard,
            parse_mode="HTML",
        )

    async def show_group(target: Message, group_id: int):
        group = await module.get_group(group_id)
        await target.answer(
            f"💼 <b>{group['name']}</b>",
            reply_markup=module.group_menu(group_id),
            parse_mode="HTML",
        )

    async def navigate_back(target: Message, from_user, state: FSMContext):
        current = await state.get_state()
        data = await state.get_data()
        group_id = data.get("group_id")

        if current:
            if current.endswith("ExpenseFlow:title"):
                await state.set_state(module.ExpenseFlow.amount)
                await target.answer("💰 مبلغ هزینه رو وارد کن.")
                return
            if current.endswith("ExpenseFlow:category"):
                await state.set_state(module.ExpenseFlow.title)
                await target.answer("📝 این هزینه بابت چی بوده؟")
                return
            if current.endswith("ExpenseFlow:payer"):
                await state.set_state(module.ExpenseFlow.category)
                await target.answer("🏷 دسته‌بندی هزینه رو انتخاب کن.", reply_markup=module.category_keyboard())
                return
            if current.endswith("ExpenseFlow:participants") and group_id:
                await state.set_state(module.ExpenseFlow.payer)
                members = await module.get_members(int(group_id))
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=m["display_name"], callback_data=f"expense:payer:{m['user_id']}")]
                    for m in members
                ])
                await target.answer("💳 چه کسی پرداخت کرده؟", reply_markup=kb)
                return
            if current.endswith("ExpenseFlow:split_mode") and group_id:
                await state.set_state(module.ExpenseFlow.participants)
                members = await module.get_members(int(group_id))
                selected = set(data.get("participant_user_ids") or [m["user_id"] for m in members])
                await target.answer("👥 هزینه بین چه کسانی تقسیم بشه؟", reply_markup=module.participants_keyboard(members, selected))
                return
            if current.endswith("ExpenseFlow:split_value"):
                await state.set_state(module.ExpenseFlow.split_mode)
                await target.answer("⚖️ روش تقسیم رو انتخاب کن.", reply_markup=module.split_keyboard())
                return

            payment_steps = {
                "PaymentProfileFlow:account_holder": (module.PaymentProfileFlow.bank_name, "🏦 نام بانک رو وارد کن. برای خالی گذاشتن «-» بفرست."),
                "PaymentProfileFlow:card_number": (module.PaymentProfileFlow.account_holder, "👤 نام صاحب حساب رو وارد کن. برای خالی گذاشتن «-» بفرست."),
                "PaymentProfileFlow:iban": (module.PaymentProfileFlow.card_number, "💳 شماره کارت رو وارد کن. برای خالی گذاشتن «-» بفرست."),
                "PaymentProfileFlow:account_number": (module.PaymentProfileFlow.iban, "🔢 شماره شبا رو وارد کن. برای خالی گذاشتن «-» بفرست."),
            }
            for suffix, (prev_state, prompt) in payment_steps.items():
                if current.endswith(suffix):
                    await state.set_state(prev_state)
                    await target.answer(prompt)
                    return

            if current.endswith("ReceiptFlow:waiting_receipt") and group_id:
                await state.clear()
                await show_group(target, int(group_id))
                return

            if current.endswith("EditExpenseFlow:waiting_value") and group_id:
                await state.clear()
                await show_group(target, int(group_id))
                return

        await state.clear()
        if group_id:
            try:
                await show_group(target, int(group_id))
                return
            except Exception:
                pass
        user = await module.ensure_user(from_user)
        await module.show_groups(target, user["id"])

    class GlobalNavMiddleware(BaseMiddleware):
        async def __call__(self, handler, event, data):
            if isinstance(event, Message) and event.text in {"🏠 منوی اصلی", "⬅️ برگشت"}:
                state: FSMContext = data["state"]
                if event.text == "🏠 منوی اصلی":
                    await show_home(event, state)
                else:
                    await navigate_back(event, event.from_user, state)
                return None
            return await handler(event, data)

    original_start_polling = Dispatcher.start_polling

    async def start_polling_with_ux(self: Dispatcher, *bots, **kwargs):
        if not getattr(self, "_dangi_ux_handlers", False):
            self._dangi_ux_handlers = True
            self.message.outer_middleware(GlobalNavMiddleware())

            async def home_callback(callback: CallbackQuery, state: FSMContext):
                try:
                    await callback.answer()
                except Exception:
                    pass
                await show_home(callback.message, state)

            async def back_callback(callback: CallbackQuery, state: FSMContext):
                try:
                    await callback.answer()
                except Exception:
                    pass
                await navigate_back(callback.message, callback.from_user, state)

            self.callback_query.register(home_callback, F.data == "ux:home")
            self.callback_query.register(back_callback, F.data == "ux:back")

        return await original_start_polling(self, *bots, **kwargs)

    Dispatcher.start_polling = start_polling_with_ux
