from __future__ import annotations

from decimal import Decimal
from html import escape

from aiogram import BaseMiddleware, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message


_INSTALLED = False


class V11Flow(StatesGroup):
    category_name = State()
    edit_text = State()
    edit_split_value = State()
    delete_confirmation = State()


def _insert_before_navigation(markup: InlineKeyboardMarkup, rows_to_add: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    rows = [list(row) for row in markup.inline_keyboard]
    idx = len(rows)
    for i, row in enumerate(rows):
        callbacks = {button.callback_data or "" for button in row}
        if any(cb.startswith("archive:") or cb == "groups:list" for cb in callbacks):
            idx = i
            break
    return InlineKeyboardMarkup(inline_keyboard=rows[:idx] + rows_to_add + rows[idx:])


def install(module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    previous_group_menu = module.group_menu
    previous_category_keyboard = module.category_keyboard

    def group_menu(group_id: int) -> InlineKeyboardMarkup:
        base = previous_group_menu(group_id)
        return _insert_before_navigation(base, [
            [InlineKeyboardButton(text="🏷 دسته‌بندی‌های گروه", callback_data=f"v11:categories:{group_id}")],
            [InlineKeyboardButton(text="🗑 حذف حساب", callback_data=f"v11:delete-preview:{group_id}")],
        ])

    def category_keyboard() -> InlineKeyboardMarkup:
        base = previous_category_keyboard()
        rows = [list(row) for row in base.inline_keyboard]
        insert_at = max(0, len(rows) - 1)
        rows.insert(insert_at, [InlineKeyboardButton(text="⭐ دسته‌بندی اختصاصی گروه", callback_data="v11:expense-custom-categories")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    module.group_menu = group_menu
    module.category_keyboard = category_keyboard

    async def current_user_and_role(from_user, group_id: int):
        user = await module.ensure_user(from_user)
        members = await module.get_members(group_id)
        member = next((m for m in members if int(m["user_id"]) == int(user["id"])), None)
        return user, member

    async def categories(group_id: int, actor_user_id: int) -> list[dict]:
        async with module.api_client() as client:
            r = await client.get(
                f"/api/v1/management/groups/{group_id}/categories",
                params={"actor_user_id": actor_user_id},
            )
            r.raise_for_status()
            return r.json()

    async def get_expense(group_id: int, expense_id: int, actor_user_id: int) -> dict:
        async with module.api_client() as client:
            r = await client.get(
                f"/api/v1/groups/{group_id}/expenses/{expense_id}",
                params={"actor_user_id": actor_user_id},
            )
            r.raise_for_status()
            return r.json()

    async def save_expense(target: Message, data: dict, expense: dict, *, success_text: str = "✅ هزینه ویرایش شد.") -> bool:
        payload = {
            "actor_user_id": data["actor_user_id"],
            "paid_by_user_id": expense["paid_by_user_id"],
            "amount": expense["amount"],
            "title": expense["title"],
            "participant_user_ids": expense["participant_user_ids"],
            "split_mode": expense.get("split_mode", "equal"),
            "split_values": expense.get("split_values"),
            "category": expense.get("category"),
            "note": expense.get("note"),
        }
        async with module.api_client() as client:
            r = await client.put(
                f"/api/v1/groups/{data['group_id']}/expenses/{data['expense_id']}",
                json=payload,
            )
        if r.status_code >= 400:
            await target.answer(f"❌ ویرایش انجام نشد: {r.text[:180]}")
            return False
        await target.answer(success_text, reply_markup=module.group_menu(data["group_id"]))
        return True

    async def full_edit_menu(target: Message, group_id: int, expense_id: int, user_id: int):
        expense = await get_expense(group_id, expense_id, user_id)
        members = await module.get_members(group_id)
        names = {m["user_id"]: m["display_name"] for m in members}
        participant_names = [names.get(uid, "کاربر") for uid in expense.get("participant_user_ids", [])]
        category = module.CATEGORY_LABELS.get(expense.get("category"), expense.get("category") or "بدون دسته‌بندی")
        text = (
            f"✏️ <b>ویرایش کامل هزینه #{expense_id}</b>\n\n"
            f"📝 {escape(expense['title'])}\n"
            f"💰 {module.fmt_amount(expense['amount'])} تومان\n"
            f"🏷 {escape(str(category))}\n"
            f"💳 پرداخت‌کننده: {escape(names.get(expense['paid_by_user_id'], 'کاربر'))}\n"
            f"👥 اعضا: {escape('، '.join(participant_names))}\n"
            f"⚖️ تقسیم: {escape(module.SPLIT_LABELS.get(expense.get('split_mode'), expense.get('split_mode', 'equal')))}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 عنوان", callback_data=f"v11edit:text:title:{group_id}:{expense_id}"),
                InlineKeyboardButton(text="💰 مبلغ", callback_data=f"v11edit:text:amount:{group_id}:{expense_id}"),
            ],
            [
                InlineKeyboardButton(text="🏷 دسته‌بندی", callback_data=f"v11edit:category:{group_id}:{expense_id}"),
                InlineKeyboardButton(text="💳 پرداخت‌کننده", callback_data=f"v11edit:payer:{group_id}:{expense_id}"),
            ],
            [
                InlineKeyboardButton(text="👥 اعضای شریک", callback_data=f"v11edit:participants:{group_id}:{expense_id}"),
                InlineKeyboardButton(text="⚖️ روش تقسیم", callback_data=f"v11edit:split:{group_id}:{expense_id}"),
            ],
            [InlineKeyboardButton(text="🗒 یادداشت", callback_data=f"v11edit:text:note:{group_id}:{expense_id}")],
            [InlineKeyboardButton(text="⬅️ تاریخچه", callback_data=f"history:{group_id}")],
        ])
        await target.answer(text, reply_markup=kb, parse_mode="HTML")

    async def intercept_edit(callback: CallbackQuery, state: FSMContext) -> bool:
        data = callback.data or ""
        if not data.startswith("edit:"):
            return False
        parts = data.split(":")
        if len(parts) != 3:
            return False
        group_id, expense_id = int(parts[1]), int(parts[2])
        user = await module.authorize(callback, group_id)
        if not user:
            return True
        await state.clear()
        try:
            await callback.answer()
        except Exception:
            pass
        await full_edit_menu(callback.message, group_id, expense_id, user["id"])
        return True

    class V11EditMiddleware(BaseMiddleware):
        async def __call__(self, handler, event, data):
            if isinstance(event, CallbackQuery) and (event.data or "").startswith("edit:"):
                handled = await intercept_edit(event, data["state"])
                if handled:
                    return None
            return await handler(event, data)

    original_start_polling = Dispatcher.start_polling

    async def start_polling_v11(self: Dispatcher, *bots, **kwargs):
        if getattr(self, "_dangi_v11_handlers", False):
            return await original_start_polling(self, *bots, **kwargs)
        self._dangi_v11_handlers = True
        self.callback_query.outer_middleware(V11EditMiddleware())

        async def show_categories(callback: CallbackQuery):
            group_id = int(callback.data.split(":")[2])
            user = await module.authorize(callback, group_id)
            if not user:
                return
            _, member = await current_user_and_role(callback.from_user, group_id)
            items = await categories(group_id, user["id"])
            rows = []
            for item in items:
                if member and member["role"] in {"owner", "admin"}:
                    rows.append([
                        InlineKeyboardButton(text=f"🏷 {item['name']}", callback_data="v11:noop"),
                        InlineKeyboardButton(text="🗑", callback_data=f"v11:category-delete:{group_id}:{item['id']}"),
                    ])
                else:
                    rows.append([InlineKeyboardButton(text=f"🏷 {item['name']}", callback_data="v11:noop")])
            if member and member["role"] in {"owner", "admin"}:
                rows.append([InlineKeyboardButton(text="➕ دسته‌بندی جدید", callback_data=f"v11:category-add:{group_id}")])
            rows.append([InlineKeyboardButton(text="⬅️ پنل حساب", callback_data=f"group:{group_id}")])
            text = "🏷 <b>دسته‌بندی‌های اختصاصی گروه</b>"
            if not items:
                text += "\n\nهنوز دسته‌بندی اختصاصی ساخته نشده."
            await callback.answer()
            await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

        async def noop(callback: CallbackQuery):
            await callback.answer()

        async def category_add(callback: CallbackQuery, state: FSMContext):
            group_id = int(callback.data.split(":")[2])
            user, member = await current_user_and_role(callback.from_user, group_id)
            if not member or member["role"] not in {"owner", "admin"}:
                await callback.answer("فقط مالک یا مدیر می‌تواند دسته‌بندی بسازد.", show_alert=True)
                return
            await state.clear()
            await state.update_data(group_id=group_id, actor_user_id=user["id"])
            await state.set_state(V11Flow.category_name)
            await callback.answer()
            await callback.message.answer("🏷 نام دسته‌بندی جدید را وارد کن. مثال: عوارض، دارو، اجاره")

        async def category_name(message: Message, state: FSMContext):
            name = " ".join((message.text or "").strip().split())
            if not name:
                await message.answer("نام دسته‌بندی نمی‌تواند خالی باشد.")
                return
            data = await state.get_data()
            async with module.api_client() as client:
                r = await client.post(
                    f"/api/v1/management/groups/{data['group_id']}/categories",
                    json={"actor_user_id": data["actor_user_id"], "name": name[:60]},
                )
            if r.status_code >= 400:
                await message.answer(f"❌ ساخت دسته‌بندی انجام نشد: {r.text[:160]}")
                return
            await state.clear()
            await message.answer(f"✅ دسته‌بندی «{escape(name[:60])}» ساخته شد.", reply_markup=module.group_menu(data["group_id"]), parse_mode="HTML")

        async def category_delete(callback: CallbackQuery):
            _, _, group_raw, category_raw = callback.data.split(":")
            group_id, category_id = int(group_raw), int(category_raw)
            user, member = await current_user_and_role(callback.from_user, group_id)
            if not member or member["role"] not in {"owner", "admin"}:
                await callback.answer("دسترسی نداری.", show_alert=True)
                return
            async with module.api_client() as client:
                r = await client.request(
                    "DELETE",
                    f"/api/v1/management/groups/{group_id}/categories/{category_id}",
                    json={"actor_user_id": user["id"]},
                )
            if r.status_code >= 400:
                await callback.answer("حذف انجام نشد.", show_alert=True)
                return
            await callback.answer("حذف شد")
            await callback.message.answer("✅ دسته‌بندی حذف شد. هزینه‌های قدیمی با نام قبلی حفظ شدند.", reply_markup=module.group_menu(group_id))

        async def expense_custom_categories(callback: CallbackQuery, state: FSMContext):
            data = await state.get_data()
            group_id = data.get("group_id")
            actor_user_id = data.get("actor_user_id")
            if not group_id or not actor_user_id:
                await callback.answer("ابتدا ثبت هزینه را از پنل حساب شروع کن.", show_alert=True)
                return
            items = await categories(int(group_id), int(actor_user_id))
            if not items:
                await callback.answer("هنوز دسته‌بندی اختصاصی ساخته نشده.", show_alert=True)
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🏷 {x['name']}", callback_data=f"v11:expense-catpick:{x['id']}")]
                for x in items
            ])
            await callback.answer()
            await callback.message.answer("⭐ دسته‌بندی اختصاصی را انتخاب کن:", reply_markup=kb)

        async def expense_catpick(callback: CallbackQuery, state: FSMContext):
            category_id = int(callback.data.split(":")[2])
            data = await state.get_data()
            items = await categories(int(data["group_id"]), int(data["actor_user_id"]))
            item = next((x for x in items if int(x["id"]) == category_id), None)
            if not item:
                await callback.answer("دسته‌بندی پیدا نشد.", show_alert=True)
                return
            members = await module.get_members(data["group_id"])
            await state.update_data(category=item["name"])
            await state.set_state(module.ExpenseFlow.payer)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=m["display_name"], callback_data=f"expense:payer:{m['user_id']}")]
                for m in members
            ])
            await callback.answer()
            await callback.message.answer("💳 چه کسی پرداخت کرده؟", reply_markup=kb)

        async def edit_text_start(callback: CallbackQuery, state: FSMContext):
            _, _, field, group_raw, expense_raw = callback.data.split(":")
            group_id, expense_id = int(group_raw), int(expense_raw)
            user = await module.authorize(callback, group_id)
            if not user:
                return
            expense = await get_expense(group_id, expense_id, user["id"])
            await state.clear()
            await state.update_data(field=field, group_id=group_id, expense_id=expense_id, actor_user_id=user["id"], expense=expense)
            await state.set_state(V11Flow.edit_text)
            prompt = {
                "title": "📝 عنوان جدید را وارد کن.",
                "amount": "💰 مبلغ جدید را وارد کن.",
                "note": "🗒 یادداشت جدید را وارد کن. برای حذف یادداشت «-» بفرست.",
            }[field]
            await callback.answer()
            await callback.message.answer(prompt)

        async def edit_text_value(message: Message, state: FSMContext):
            data = await state.get_data()
            expense = dict(data["expense"])
            field = data["field"]
            if field == "amount":
                try:
                    expense["amount"] = str(module.parse_number(message.text or ""))
                except ValueError:
                    await message.answer("❌ مبلغ معتبر وارد کن.")
                    return
                if expense.get("split_mode") == "exact":
                    expense["split_mode"] = "equal"
                    expense["split_values"] = None
            elif field == "title":
                value = (message.text or "").strip()
                if not value:
                    await message.answer("عنوان خالی نباشد.")
                    return
                expense["title"] = value[:160]
            else:
                value = (message.text or "").strip()
                expense["note"] = None if value == "-" else value[:1000]
            ok = await save_expense(message, data, expense)
            if ok:
                await state.clear()

        async def edit_category(callback: CallbackQuery):
            _, _, group_raw, expense_raw = callback.data.split(":")
            group_id, expense_id = int(group_raw), int(expense_raw)
            user = await module.authorize(callback, group_id)
            if not user:
                return
            custom = await categories(group_id, user["id"])
            rows = [
                [InlineKeyboardButton(text=label, callback_data=f"v11edit:catpick:{key}:{group_id}:{expense_id}")]
                for key, label in module.CATEGORY_LABELS.items()
            ]
            rows += [
                [InlineKeyboardButton(text=f"⭐ {x['name']}", callback_data=f"v11edit:catcustom:{x['id']}:{group_id}:{expense_id}")]
                for x in custom
            ]
            rows.append([InlineKeyboardButton(text="⬅️ ویرایش", callback_data=f"edit:{group_id}:{expense_id}")])
            await callback.answer()
            await callback.message.answer("🏷 دسته‌بندی جدید را انتخاب کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

        async def edit_category_builtin(callback: CallbackQuery):
            _, _, key, group_raw, expense_raw = callback.data.split(":")
            group_id, expense_id = int(group_raw), int(expense_raw)
            user = await module.authorize(callback, group_id)
            if not user:
                return
            expense = await get_expense(group_id, expense_id, user["id"])
            expense["category"] = key
            await callback.answer()
            await save_expense(callback.message, {"group_id": group_id, "expense_id": expense_id, "actor_user_id": user["id"]}, expense)

        async def edit_category_custom(callback: CallbackQuery):
            _, _, category_raw, group_raw, expense_raw = callback.data.split(":")
            group_id, expense_id, category_id = int(group_raw), int(expense_raw), int(category_raw)
            user = await module.authorize(callback, group_id)
            if not user:
                return
            custom = await categories(group_id, user["id"])
            item = next((x for x in custom if int(x["id"]) == category_id), None)
            if not item:
                await callback.answer("دسته‌بندی پیدا نشد.", show_alert=True)
                return
            expense = await get_expense(group_id, expense_id, user["id"])
            expense["category"] = item["name"]
            await callback.answer()
            await save_expense(callback.message, {"group_id": group_id, "expense_id": expense_id, "actor_user_id": user["id"]}, expense)

        async def edit_payer(callback: CallbackQuery):
            _, _, group_raw, expense_raw = callback.data.split(":")
            group_id, expense_id = int(group_raw), int(expense_raw)
            if not await module.authorize(callback, group_id):
                return
            members = await module.get_members(group_id)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=m["display_name"], callback_data=f"v11edit:payerpick:{m['user_id']}:{group_id}:{expense_id}")]
                for m in members
            ])
            await callback.answer()
            await callback.message.answer("💳 پرداخت‌کننده جدید را انتخاب کن:", reply_markup=kb)

        async def edit_payer_pick(callback: CallbackQuery):
            _, _, user_raw, group_raw, expense_raw = callback.data.split(":")
            group_id, expense_id, payer_id = int(group_raw), int(expense_raw), int(user_raw)
            user = await module.authorize(callback, group_id)
            if not user:
                return
            expense = await get_expense(group_id, expense_id, user["id"])
            expense["paid_by_user_id"] = payer_id
            await callback.answer()
            await save_expense(callback.message, {"group_id": group_id, "expense_id": expense_id, "actor_user_id": user["id"]}, expense)

        async def edit_participants(callback: CallbackQuery, state: FSMContext):
            _, _, group_raw, expense_raw = callback.data.split(":")
            group_id, expense_id = int(group_raw), int(expense_raw)
            user = await module.authorize(callback, group_id)
            if not user:
                return
            expense = await get_expense(group_id, expense_id, user["id"])
            selected = set(expense.get("participant_user_ids", []))
            members = await module.get_members(group_id)
            await state.update_data(v11_edit_participants={"group_id": group_id, "expense_id": expense_id, "actor_user_id": user["id"], "expense": expense, "selected": list(selected)})
            rows = [[InlineKeyboardButton(text=f"{'✅' if m['user_id'] in selected else '▫️'} {m['display_name']}", callback_data=f"v11edit:ptoggle:{m['user_id']}")] for m in members]
            rows.append([InlineKeyboardButton(text="✅ ذخیره اعضا", callback_data="v11edit:pdone")])
            await callback.answer()
            await callback.message.answer("👥 اعضای شریک را انتخاب کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

        async def render_participants(callback: CallbackQuery, state: FSMContext):
            data = await state.get_data()
            ctx = data.get("v11_edit_participants")
            if not ctx:
                await callback.answer("فرآیند ویرایش منقضی شده.", show_alert=True)
                return
            members = await module.get_members(ctx["group_id"])
            selected = set(ctx["selected"])
            rows = [[InlineKeyboardButton(text=f"{'✅' if m['user_id'] in selected else '▫️'} {m['display_name']}", callback_data=f"v11edit:ptoggle:{m['user_id']}")] for m in members]
            rows.append([InlineKeyboardButton(text="✅ ذخیره اعضا", callback_data="v11edit:pdone")])
            await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

        async def participant_toggle(callback: CallbackQuery, state: FSMContext):
            uid = int(callback.data.split(":")[2])
            data = await state.get_data()
            ctx = dict(data.get("v11_edit_participants") or {})
            if not ctx:
                await callback.answer("فرآیند ویرایش منقضی شده.", show_alert=True)
                return
            selected = set(ctx["selected"])
            selected.remove(uid) if uid in selected else selected.add(uid)
            ctx["selected"] = sorted(selected)
            await state.update_data(v11_edit_participants=ctx)
            await callback.answer()
            await render_participants(callback, state)

        async def participants_done(callback: CallbackQuery, state: FSMContext):
            data = await state.get_data()
            ctx = data.get("v11_edit_participants")
            if not ctx or not ctx["selected"]:
                await callback.answer("حداقل یک نفر باید انتخاب شود.", show_alert=True)
                return
            expense = dict(ctx["expense"])
            expense["participant_user_ids"] = ctx["selected"]
            expense["split_mode"] = "equal"
            expense["split_values"] = None
            await callback.answer()
            ok = await save_expense(callback.message, ctx, expense, success_text="✅ اعضای شریک ذخیره شدند؛ تقسیم برای سازگاری روی «مساوی» تنظیم شد.")
            if ok:
                await state.update_data(v11_edit_participants=None)

        async def edit_split(callback: CallbackQuery):
            _, _, group_raw, expense_raw = callback.data.split(":")
            group_id, expense_id = int(group_raw), int(expense_raw)
            if not await module.authorize(callback, group_id):
                return
            rows = [
                [InlineKeyboardButton(text="⚖️ مساوی", callback_data=f"v11edit:splitpick:equal:{group_id}:{expense_id}")],
                [InlineKeyboardButton(text="📊 درصدی", callback_data=f"v11edit:splitpick:percentage:{group_id}:{expense_id}")],
                [InlineKeyboardButton(text="🔢 سهمی / وزنی", callback_data=f"v11edit:splitpick:shares:{group_id}:{expense_id}")],
                [InlineKeyboardButton(text="💵 مبلغ ثابت", callback_data=f"v11edit:splitpick:exact:{group_id}:{expense_id}")],
            ]
            await callback.answer()
            await callback.message.answer("⚖️ روش تقسیم جدید را انتخاب کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

        async def prompt_edit_split(target: Message, state: FSMContext):
            data = await state.get_data()
            ctx = data["v11_edit_split"]
            ids = ctx["expense"]["participant_user_ids"]
            idx = ctx["index"]
            names = {m["user_id"]: m["display_name"] for m in await module.get_members(ctx["group_id"])}
            unit = {"percentage": "درصد", "shares": "سهم", "exact": "تومان"}[ctx["mode"]]
            await target.answer(f"مقدار {unit} برای «{escape(names.get(ids[idx], 'کاربر'))}» را وارد کن:", parse_mode="HTML")

        async def split_pick(callback: CallbackQuery, state: FSMContext):
            _, _, mode, group_raw, expense_raw = callback.data.split(":")
            group_id, expense_id = int(group_raw), int(expense_raw)
            user = await module.authorize(callback, group_id)
            if not user:
                return
            expense = await get_expense(group_id, expense_id, user["id"])
            if mode == "equal":
                expense["split_mode"] = "equal"
                expense["split_values"] = None
                await callback.answer()
                await save_expense(callback.message, {"group_id": group_id, "expense_id": expense_id, "actor_user_id": user["id"]}, expense)
                return
            await state.update_data(v11_edit_split={"group_id": group_id, "expense_id": expense_id, "actor_user_id": user["id"], "expense": expense, "mode": mode, "values": {}, "index": 0})
            await state.set_state(V11Flow.edit_split_value)
            await callback.answer()
            await prompt_edit_split(callback.message, state)

        async def split_value(message: Message, state: FSMContext):
            try:
                value = module.parse_number(message.text or "")
            except ValueError:
                await message.answer("عدد مثبت و معتبر وارد کن.")
                return
            data = await state.get_data()
            ctx = dict(data["v11_edit_split"])
            expense = dict(ctx["expense"])
            ids = expense["participant_user_ids"]
            values = dict(ctx["values"])
            values[str(ids[ctx["index"]])] = str(value)
            ctx["index"] += 1
            ctx["values"] = values
            await state.update_data(v11_edit_split=ctx)
            if ctx["index"] < len(ids):
                await prompt_edit_split(message, state)
                return
            if ctx["mode"] == "percentage" and sum(Decimal(v) for v in values.values()) != Decimal("100"):
                ctx["values"], ctx["index"] = {}, 0
                await state.update_data(v11_edit_split=ctx)
                await message.answer("❌ مجموع درصدها باید دقیقاً 100 باشد. دوباره وارد کن.")
                await prompt_edit_split(message, state)
                return
            if ctx["mode"] == "exact" and sum(Decimal(v) for v in values.values()) != Decimal(str(expense["amount"])):
                ctx["values"], ctx["index"] = {}, 0
                await state.update_data(v11_edit_split=ctx)
                await message.answer("❌ مجموع مبلغ‌های ثابت باید برابر مبلغ کل هزینه باشد. دوباره وارد کن.")
                await prompt_edit_split(message, state)
                return
            expense["split_mode"] = ctx["mode"]
            expense["split_values"] = values
            ok = await save_expense(message, ctx, expense)
            if ok:
                await state.clear()

        async def delete_preview(callback: CallbackQuery):
            group_id = int(callback.data.split(":")[2])
            user, member = await current_user_and_role(callback.from_user, group_id)
            if not member or member["role"] != "owner":
                await callback.answer("فقط مالک حساب می‌تواند حذف کامل انجام دهد.", show_alert=True)
                return
            async with module.api_client() as client:
                r = await client.get(
                    f"/api/v1/management/groups/{group_id}/delete-preview",
                    params={"actor_user_id": user["id"]},
                )
                r.raise_for_status()
                preview = r.json()
            lines = [
                "🗑 <b>حذف امن حساب</b>", "",
                f"حساب: <b>{escape(preview['group_name'])}</b>",
                f"👥 اعضا: {preview['member_count']}",
                f"🧾 هزینه‌ها: {preview['expense_count']}",
                f"🏷 دسته‌بندی اختصاصی: {preview['custom_category_count']}",
                f"↔️ بدهی‌های باز: {preview['unresolved_transfer_count']}",
                f"⏳ تسویه‌های منتظر: {preview['pending_settlement_count']}",
            ]
            if not preview["can_permanently_delete"]:
                lines += ["", "⛔ حذف کامل فعلاً مسدود است. ابتدا بدهی‌ها و تسویه‌های منتظر را نهایی کن؛ یا حساب را آرشیو کن."]
                rows = [
                    [InlineKeyboardButton(text="🗄 آرشیو به‌جای حذف", callback_data=f"archive:{group_id}")],
                    [InlineKeyboardButton(text="⬅️ پنل حساب", callback_data=f"group:{group_id}")],
                ]
            else:
                lines += ["", "⚠️ حذف کامل غیرقابل بازگشت است و همه داده‌های این حساب را پاک می‌کند."]
                rows = [
                    [InlineKeyboardButton(text="🗑 ادامه حذف کامل", callback_data=f"v11:delete-confirm:{group_id}")],
                    [InlineKeyboardButton(text="🗄 فقط آرشیو", callback_data=f"archive:{group_id}")],
                    [InlineKeyboardButton(text="⬅️ انصراف", callback_data=f"group:{group_id}")],
                ]
            await callback.answer()
            await callback.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

        async def delete_confirm(callback: CallbackQuery, state: FSMContext):
            group_id = int(callback.data.split(":")[2])
            user, member = await current_user_and_role(callback.from_user, group_id)
            if not member or member["role"] != "owner":
                await callback.answer("دسترسی نداری.", show_alert=True)
                return
            group = await module.get_group(group_id)
            await state.clear()
            await state.update_data(group_id=group_id, actor_user_id=user["id"], group_name=group["name"])
            await state.set_state(V11Flow.delete_confirmation)
            await callback.answer()
            await callback.message.answer(
                f"⚠️ برای حذف قطعی، نام حساب را دقیقاً تایپ کن:\n\n<b>{escape(group['name'])}</b>",
                parse_mode="HTML",
            )

        async def delete_confirmation(message: Message, state: FSMContext):
            data = await state.get_data()
            confirmation = (message.text or "").strip()
            if confirmation != data["group_name"]:
                await message.answer("❌ نام واردشده دقیقاً با نام حساب یکسان نیست. دوباره وارد کن یا «⬅️ برگشت» بزن.")
                return
            async with module.api_client() as client:
                r = await client.request(
                    "DELETE",
                    f"/api/v1/management/groups/{data['group_id']}",
                    json={"actor_user_id": data["actor_user_id"], "confirmation": confirmation},
                )
            if r.status_code == 409:
                await state.clear()
                await message.answer("⛔ در این فاصله فعالیت مالی بازی ایجاد شده؛ حذف لغو شد. ابتدا بدهی/تسویه را نهایی کن.", reply_markup=module.main_keyboard)
                return
            if r.status_code >= 400:
                await message.answer(f"❌ حذف انجام نشد: {r.text[:180]}")
                return
            await state.clear()
            await message.answer("✅ حساب و تمام داده‌های وابسته به آن حذف شد.", reply_markup=module.main_keyboard)

        self.callback_query.register(show_categories, F.data.startswith("v11:categories:"))
        self.callback_query.register(noop, F.data == "v11:noop")
        self.callback_query.register(category_add, F.data.startswith("v11:category-add:"))
        self.callback_query.register(category_delete, F.data.startswith("v11:category-delete:"))
        self.callback_query.register(expense_custom_categories, F.data == "v11:expense-custom-categories")
        self.callback_query.register(expense_catpick, F.data.startswith("v11:expense-catpick:"))
        self.message.register(category_name, V11Flow.category_name)

        self.callback_query.register(edit_text_start, F.data.startswith("v11edit:text:"))
        self.message.register(edit_text_value, V11Flow.edit_text)
        self.callback_query.register(edit_category, F.data.startswith("v11edit:category:"))
        self.callback_query.register(edit_category_builtin, F.data.startswith("v11edit:catpick:"))
        self.callback_query.register(edit_category_custom, F.data.startswith("v11edit:catcustom:"))
        self.callback_query.register(edit_payer, F.data.startswith("v11edit:payer:"))
        self.callback_query.register(edit_payer_pick, F.data.startswith("v11edit:payerpick:"))
        self.callback_query.register(edit_participants, F.data.startswith("v11edit:participants:"))
        self.callback_query.register(participant_toggle, F.data.startswith("v11edit:ptoggle:"))
        self.callback_query.register(participants_done, F.data == "v11edit:pdone")
        self.callback_query.register(edit_split, F.data.startswith("v11edit:split:"))
        self.callback_query.register(split_pick, F.data.startswith("v11edit:splitpick:"))
        self.message.register(split_value, V11Flow.edit_split_value)

        self.callback_query.register(delete_preview, F.data.startswith("v11:delete-preview:"))
        self.callback_query.register(delete_confirm, F.data.startswith("v11:delete-confirm:"))
        self.message.register(delete_confirmation, V11Flow.delete_confirmation)

        return await original_start_polling(self, *bots, **kwargs)

    Dispatcher.start_polling = start_polling_v11
