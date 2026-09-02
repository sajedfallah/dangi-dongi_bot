from __future__ import annotations

from html import escape

from aiogram import Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message


class AdvancedExpenseFlow(StatesGroup):
    custom_other_title = State()
    historical_value = State()


_INSTALLED = False


def install(module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_group_menu = module.group_menu

    def group_menu(group_id: int) -> InlineKeyboardMarkup:
        markup = original_group_menu(group_id)
        rows = [list(row) for row in markup.inline_keyboard]
        insert_at = max(0, len(rows) - 2)
        rows.insert(insert_at, [
            InlineKeyboardButton(text="👤 عضو جدید × هزینه‌های قبلی", callback_data=f"retro:start:{group_id}")
        ])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    module.group_menu = group_menu

    def category_keyboard() -> InlineKeyboardMarkup:
        rows = []
        for key, label in module.CATEGORY_LABELS.items():
            callback = "advanced:other" if key == "other" else f"expense:category:{key}"
            rows.append([InlineKeyboardButton(text=label, callback_data=callback)])
        rows.append([InlineKeyboardButton(text="❌ لغو", callback_data="flow:cancel")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    module.category_keyboard = category_keyboard

    previous_start_polling = Dispatcher.start_polling

    async def start_polling_with_advanced(self: Dispatcher, *bots, **kwargs):
        if not getattr(self, "_dangi_advanced_expense_handlers", False):
            self._dangi_advanced_expense_handlers = True

            async def other_category(callback: CallbackQuery, state: FSMContext):
                data = await state.get_data()
                if not data.get("group_id"):
                    await callback.answer("جلسه منقضی شده.", show_alert=True)
                    return
                await state.update_data(category="other")
                await state.set_state(AdvancedExpenseFlow.custom_other_title)
                await callback.answer()
                await callback.message.answer(
                    "✍️ عنوان دقیق این هزینه را بنویس.\nمثال: پارکینگ، انعام، شارژ ویلا یا هر مورد دیگری."
                )

            async def other_title(message: Message, state: FSMContext):
                title = (message.text or "").strip()
                if not title:
                    await message.answer("عنوان هزینه نمی‌تواند خالی باشد.")
                    return
                data = await state.get_data()
                members = await module.get_members(data["group_id"])
                await state.update_data(title=title[:160], category="other")
                await state.set_state(module.ExpenseFlow.payer)
                await message.answer(
                    "💳 چه کسی پرداخت کرده؟",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=m["display_name"], callback_data=f"expense:payer:{m['user_id']}")]
                        for m in members
                    ]),
                )

            async def retro_start(callback: CallbackQuery):
                group_id = int(callback.data.split(":")[2])
                user = await module.authorize(callback, group_id)
                if not user:
                    return
                members = await module.get_members(group_id)
                current = next((m for m in members if m["user_id"] == user["id"]), None)
                if not current or current.get("role") not in {"owner", "admin"}:
                    await callback.answer("فقط مالک یا ادمین می‌تواند هزینه‌های قبلی را بازتقسیم کند.", show_alert=True)
                    return
                rows = [
                    [InlineKeyboardButton(text=f"👤 {m['display_name']}", callback_data=f"retro:member:{group_id}:{m['user_id']}")]
                    for m in members
                ]
                rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"group:{group_id}")])
                await callback.answer()
                await callback.message.answer(
                    "👤 <b>افزودن عضو به هزینه‌های قبلی</b>\n\nعضوی را انتخاب کن که می‌خواهی به بعضی هزینه‌های گذشته اضافه شود.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML",
                )

            async def retro_member(callback: CallbackQuery):
                _, _, group_raw, member_raw = callback.data.split(":")
                group_id, member_id = int(group_raw), int(member_raw)
                user = await module.authorize(callback, group_id)
                if not user:
                    return
                members = await module.get_members(group_id)
                member = next((m for m in members if m["user_id"] == member_id), None)
                async with module.api_client() as client:
                    r = await client.get(
                        f"/api/v1/product/groups/{group_id}/historical-expenses/{member_id}",
                        params={"actor_user_id": user["id"]},
                    )
                if r.status_code == 403:
                    await callback.answer("فقط مالک یا ادمین اجازه این کار را دارد.", show_alert=True)
                    return
                r.raise_for_status()
                expenses = [x for x in r.json() if not x["already_participant"]]
                if not expenses:
                    await callback.answer()
                    await callback.message.answer(
                        f"✅ {escape(member['display_name'] if member else 'این عضو')} از قبل در همه هزینه‌های موجود سهم دارد.",
                        reply_markup=module.group_menu(group_id),
                        parse_mode="HTML",
                    )
                    return
                rows = [
                    [InlineKeyboardButton(
                        text=f"#{x['id']} · {x['title']} · {module.fmt_amount(x['amount'])}",
                        callback_data=f"retro:expense:{group_id}:{member_id}:{x['id']}",
                    )]
                    for x in expenses[:30]
                ]
                rows.append([InlineKeyboardButton(text="⬅️ انتخاب عضو", callback_data=f"retro:start:{group_id}")])
                await callback.answer()
                await callback.message.answer(
                    f"🧾 هزینه‌های قبلی برای <b>{escape(member['display_name'] if member else 'عضو')}</b>\n\n"
                    "هر هزینه‌ای را که این عضو باید در آن شریک باشد انتخاب کن:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML",
                )

            async def retro_expense(callback: CallbackQuery):
                _, _, group_raw, member_raw, expense_raw = callback.data.split(":")
                group_id, member_id, expense_id = int(group_raw), int(member_raw), int(expense_raw)
                await callback.answer()
                await callback.message.answer(
                    "⚖️ سهم عضو جدید در این هزینه چگونه محاسبه شود؟",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="⚖️ مساوی با همه", callback_data=f"retro:apply:{group_id}:{member_id}:{expense_id}:equal")],
                        [InlineKeyboardButton(text="📊 درصد مشخص", callback_data=f"retro:value:{group_id}:{member_id}:{expense_id}:percentage")],
                        [InlineKeyboardButton(text="💵 مبلغ ثابت", callback_data=f"retro:value:{group_id}:{member_id}:{expense_id}:exact")],
                        [InlineKeyboardButton(text="⬅️ هزینه‌ها", callback_data=f"retro:member:{group_id}:{member_id}")],
                    ]),
                )

            async def apply_equal(callback: CallbackQuery):
                _, _, group_raw, member_raw, expense_raw, mode = callback.data.split(":")
                group_id, member_id, expense_id = int(group_raw), int(member_raw), int(expense_raw)
                user = await module.authorize(callback, group_id)
                if not user:
                    return
                async with module.api_client() as client:
                    r = await client.post(
                        f"/api/v1/product/groups/{group_id}/expenses/{expense_id}/historical-member",
                        json={"actor_user_id": user["id"], "member_user_id": member_id, "mode": mode, "value": None},
                    )
                if r.status_code >= 400:
                    await callback.answer("اعمال سهم انجام نشد.", show_alert=True)
                    return
                result = r.json()
                await callback.answer("اعمال شد")
                await callback.message.answer(
                    f"✅ عضو به هزینه #{expense_id} اضافه شد.\nسهم جدید: {module.fmt_amount(result['new_share'])} تومان",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🧾 انتخاب هزینه بعدی", callback_data=f"retro:member:{group_id}:{member_id}")],
                        [InlineKeyboardButton(text="💼 پنل حساب", callback_data=f"group:{group_id}")],
                    ]),
                )

            async def ask_value(callback: CallbackQuery, state: FSMContext):
                _, _, group_raw, member_raw, expense_raw, mode = callback.data.split(":")
                await state.clear()
                await state.update_data(
                    group_id=int(group_raw), member_user_id=int(member_raw), expense_id=int(expense_raw), retro_mode=mode
                )
                await state.set_state(AdvancedExpenseFlow.historical_value)
                await callback.answer()
                await callback.message.answer(
                    "📊 درصد سهم عضو جدید را وارد کن (مثلاً 25)." if mode == "percentage"
                    else "💵 مبلغ ثابت سهم عضو جدید را به تومان وارد کن."
                )

            async def apply_value(message: Message, state: FSMContext):
                data = await state.get_data()
                try:
                    value = module.parse_number(message.text or "")
                except ValueError:
                    await message.answer("عدد معتبر و مثبت وارد کن.")
                    return
                user = await module.ensure_user(message.from_user)
                async with module.api_client() as client:
                    r = await client.post(
                        f"/api/v1/product/groups/{data['group_id']}/expenses/{data['expense_id']}/historical-member",
                        json={
                            "actor_user_id": user["id"],
                            "member_user_id": data["member_user_id"],
                            "mode": data["retro_mode"],
                            "value": str(value),
                        },
                    )
                if r.status_code >= 400:
                    detail = r.json().get("detail", "مقدار قابل اعمال نیست") if r.headers.get("content-type", "").startswith("application/json") else "مقدار قابل اعمال نیست"
                    await message.answer(f"❌ {detail}")
                    return
                result = r.json()
                group_id, member_id = data["group_id"], data["member_user_id"]
                await state.clear()
                await message.answer(
                    f"✅ سهم عضو روی هزینه #{data['expense_id']} اعمال شد.\nسهم جدید: {module.fmt_amount(result['new_share'])} تومان",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🧾 انتخاب هزینه بعدی", callback_data=f"retro:member:{group_id}:{member_id}")],
                        [InlineKeyboardButton(text="💼 پنل حساب", callback_data=f"group:{group_id}")],
                    ]),
                )

            self.callback_query.register(other_category, F.data == "advanced:other")
            self.message.register(other_title, AdvancedExpenseFlow.custom_other_title)
            self.callback_query.register(retro_start, F.data.startswith("retro:start:"))
            self.callback_query.register(retro_member, F.data.startswith("retro:member:"))
            self.callback_query.register(retro_expense, F.data.startswith("retro:expense:"))
            self.callback_query.register(apply_equal, F.data.startswith("retro:apply:"))
            self.callback_query.register(ask_value, F.data.startswith("retro:value:"))
            self.message.register(apply_value, AdvancedExpenseFlow.historical_value)

        return await previous_start_polling(self, *bots, **kwargs)

    Dispatcher.start_polling = start_polling_with_advanced
