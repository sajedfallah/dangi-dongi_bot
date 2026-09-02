from __future__ import annotations

from collections import defaultdict

from aiogram import Dispatcher, F
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
        # Remove the user's typed input, or the old callback panel, before the next panel.
        if self.from_user and not self.from_user.is_bot:
            await _safe_delete(bot, chat_id, self.message_id)
        elif self.from_user and self.from_user.is_bot:
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

    original_start_polling = Dispatcher.start_polling

    async def start_polling_with_ux(self: Dispatcher, *bots, **kwargs):
        if not getattr(self, "_dangi_ux_handlers", False):
            self._dangi_ux_handlers = True

            async def show_home_message(message: Message, state: FSMContext):
                await state.clear()
                await message.answer(
                    "🏠 <b>منوی اصلی</b>\n\nاز اینجا می‌تونی حساب‌هات، اعلان‌ها و تنظیماتت رو مدیریت کنی.",
                    reply_markup=module.main_keyboard,
                    parse_mode="HTML",
                )

            async def back_message(message: Message, state: FSMContext):
                data = await state.get_data()
                group_id = data.get("group_id")
                await state.clear()
                if group_id:
                    try:
                        group = await module.get_group(int(group_id))
                        await message.answer(
                            f"💼 <b>{group['name']}</b>",
                            reply_markup=module.group_menu(int(group_id)),
                            parse_mode="HTML",
                        )
                        return
                    except Exception:
                        pass
                user = await module.ensure_user(message.from_user)
                await module.show_groups(message, user["id"])

            async def home_callback(callback: CallbackQuery, state: FSMContext):
                await state.clear()
                try:
                    await callback.answer()
                except Exception:
                    pass
                await callback.message.answer(
                    "🏠 <b>منوی اصلی</b>\n\nاز اینجا می‌تونی حساب‌هات، اعلان‌ها و تنظیماتت رو مدیریت کنی.",
                    reply_markup=module.main_keyboard,
                    parse_mode="HTML",
                )

            async def back_callback(callback: CallbackQuery, state: FSMContext):
                data = await state.get_data()
                group_id = data.get("group_id")
                await state.clear()
                try:
                    await callback.answer()
                except Exception:
                    pass
                if group_id:
                    try:
                        group = await module.get_group(int(group_id))
                        await callback.message.answer(
                            f"💼 <b>{group['name']}</b>",
                            reply_markup=module.group_menu(int(group_id)),
                            parse_mode="HTML",
                        )
                        return
                    except Exception:
                        pass
                user = await module.ensure_user(callback.from_user)
                await module.show_groups(callback.message, user["id"])

            self.message.register(show_home_message, F.text == "🏠 منوی اصلی")
            self.message.register(back_message, F.text == "⬅️ برگشت")
            self.callback_query.register(home_callback, F.data == "ux:home")
            self.callback_query.register(back_callback, F.data == "ux:back")

        return await original_start_polling(self, *bots, **kwargs)

    Dispatcher.start_polling = start_polling_with_ux
