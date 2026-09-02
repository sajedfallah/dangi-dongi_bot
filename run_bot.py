import asyncio
import os

os.environ["DANGI_BOT_PROCESS"] = "1"

from aiogram import Dispatcher, F  # noqa: E402
from aiogram.types import (  # noqa: E402
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import app.bot.main as bot_main  # noqa: E402


# Personal dashboard is always available, regardless of whether the user entered
# normally or through another user's invite deep-link.
bot_main.main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ ساخت حساب جدید"), KeyboardButton(text="📂 حساب‌های من")],
        [KeyboardButton(text="🔔 اعلان‌ها"), KeyboardButton(text="🗄 آرشیو")],
        [KeyboardButton(text="❓ راهنما")],
    ],
    resize_keyboard=True,
)


# Add an archive action to every group panel. Permission is enforced by Backend.
_original_group_menu = bot_main.group_menu


def _group_menu_with_archive(group_id: int) -> InlineKeyboardMarkup:
    markup = _original_group_menu(group_id)
    rows = list(markup.inline_keyboard)
    # Insert archive immediately before the "accounts" navigation row.
    insert_at = max(0, len(rows) - 1)
    rows.insert(insert_at, [InlineKeyboardButton(text="🗄 آرشیو این حساب", callback_data=f"dashboard:archive:{group_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


bot_main.group_menu = _group_menu_with_archive


# When a user joins through a deep-link, the legacy flow opens that group. Keep
# that useful confirmation, then immediately expose the user's own dashboard so
# the invited group becomes just one membership among all their accounts.
_original_answer = Message.answer


async def _answer_with_dashboard_after_join(self: Message, text, *args, **kwargs):
    result = await _original_answer(self, text, *args, **kwargs)
    if isinstance(text, str) and text.startswith("✅ به حساب «") and "اضافه شدی" in text:
        await _original_answer(
            self,
            "🏠 این گروه به حساب‌های تو اضافه شد. از منوی شخصی می‌تونی گروه‌های خودت رو بسازی یا بین همه گروه‌هات جابه‌جا بشی.",
            reply_markup=bot_main.main_keyboard,
        )
    return result


Message.answer = _answer_with_dashboard_after_join


_original_start_polling = Dispatcher.start_polling


async def _start_polling_with_dashboard_handlers(self: Dispatcher, *bots, **kwargs):
    if not getattr(self, "_dangi_dashboard_handlers", False):
        self._dangi_dashboard_handlers = True

        async def notifications(message: Message):
            user = await bot_main.ensure_user(message.from_user)
            async with bot_main.api_client() as client:
                response = await client.get(f"/api/v1/dashboard/users/{user['id']}/notifications")
                response.raise_for_status()
                items = response.json()
            if not items:
                await message.answer("🔔 اعلان جدیدی نداری.", reply_markup=bot_main.main_keyboard)
                return
            lines = ["🔔 اعلان‌های تو:"]
            for item in items[:20]:
                action = "نیاز به تأیید تو" if item.get("requires_action") else "در انتظار طرف مقابل"
                lines.append(
                    f"• تسویه #{item['settlement_id']} — {bot_main.fmt_amount(item['amount'])} تومان — {action}"
                )
            await message.answer("\n".join(lines), reply_markup=bot_main.main_keyboard)

        async def archived_accounts(message: Message):
            user = await bot_main.ensure_user(message.from_user)
            async with bot_main.api_client() as client:
                response = await client.get(
                    f"/api/v1/dashboard/users/{user['id']}/groups",
                    params={"archived": "true"},
                )
                response.raise_for_status()
                groups = response.json()
            if not groups:
                await message.answer("🗄 حساب آرشیوشده‌ای نداری.", reply_markup=bot_main.main_keyboard)
                return
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"♻️ بازگردانی {group.get('raw_name', group['name'])}",
                    callback_data=f"dashboard:restore:{group['id']}",
                )]
                for group in groups
            ])
            await message.answer("🗄 آرشیو حساب‌ها:", reply_markup=keyboard)

        async def archive_callback(callback: CallbackQuery):
            group_id = int(callback.data.rsplit(":", 1)[1])
            user = await bot_main.ensure_user(callback.from_user)
            async with bot_main.api_client() as client:
                response = await client.patch(
                    f"/api/v1/dashboard/groups/{group_id}/archive",
                    json={"actor_user_id": user["id"], "is_archived": True},
                )
            if response.status_code == 403:
                await callback.answer("فقط مالک یا ادمین می‌تونه حساب رو آرشیو کنه.", show_alert=True)
                return
            if response.status_code >= 400:
                await callback.answer("آرشیو انجام نشد.", show_alert=True)
                return
            await callback.answer("آرشیو شد")
            await callback.message.answer(
                "✅ حساب آرشیو شد. اطلاعات و تاریخچه حذف نشده و از بخش «🗄 آرشیو» قابل بازگردانیه.",
                reply_markup=bot_main.main_keyboard,
            )

        async def restore_callback(callback: CallbackQuery):
            group_id = int(callback.data.rsplit(":", 1)[1])
            user = await bot_main.ensure_user(callback.from_user)
            async with bot_main.api_client() as client:
                response = await client.patch(
                    f"/api/v1/dashboard/groups/{group_id}/archive",
                    json={"actor_user_id": user["id"], "is_archived": False},
                )
            if response.status_code >= 400:
                await callback.answer("بازگردانی انجام نشد.", show_alert=True)
                return
            await callback.answer("بازگردانی شد")
            await callback.message.answer(
                "♻️ حساب دوباره فعال شد و در «📂 حساب‌های من» نمایش داده می‌شه.",
                reply_markup=bot_main.main_keyboard,
            )

        self.message.register(notifications, F.text == "🔔 اعلان‌ها")
        self.message.register(archived_accounts, F.text == "🗄 آرشیو")
        self.callback_query.register(archive_callback, F.data.startswith("dashboard:archive:"))
        self.callback_query.register(restore_callback, F.data.startswith("dashboard:restore:"))

    return await _original_start_polling(self, *bots, **kwargs)


Dispatcher.start_polling = _start_polling_with_dashboard_handlers


if __name__ == "__main__":
    asyncio.run(bot_main.run_bot())
