from __future__ import annotations

import re
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message


_INSTALLED = False
_TG_TO_USER: dict[int, int] = {}
_JOIN_RESULT_BY_USER: dict[int, tuple[int, bool]] = {}
_MEMBER_PATH = re.compile(r"^/api/v1/groups/(\d+)/members$")


def install(module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_api_client = module.api_client

    class TrackingClient:
        def __init__(self):
            self._cm = original_api_client()
            self._client = None

        async def __aenter__(self):
            self._client = await self._cm.__aenter__()
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return await self._cm.__aexit__(exc_type, exc, tb)

        async def post(self, url, *args, **kwargs):
            response = await self._client.post(url, *args, **kwargs)
            try:
                url_text = str(url)
                if url_text == "/api/v1/users" and response.status_code < 400:
                    payload = kwargs.get("json") or {}
                    telegram_id = payload.get("telegram_id")
                    body = response.json()
                    internal_id = body.get("id")
                    if telegram_id is not None and internal_id is not None:
                        _TG_TO_USER[int(telegram_id)] = int(internal_id)
                else:
                    match = _MEMBER_PATH.match(url_text)
                    if match and response.status_code < 400:
                        payload = kwargs.get("json") or {}
                        user_id = payload.get("user_id")
                        body = response.json()
                        if user_id is not None:
                            group_id = int(match.group(1))
                            is_new = body.get("already_member") is False
                            _JOIN_RESULT_BY_USER[int(user_id)] = (group_id, is_new)
            except Exception:
                pass
            return response

        def __getattr__(self, name):
            return getattr(self._client, name)

    def tracked_api_client():
        return TrackingClient()

    module.api_client = tracked_api_client

    original_answer = Message.answer

    async def answer_with_join_notification(self: Message, text, *args, **kwargs):
        if not (isinstance(text, str) and text.startswith("✅ به حساب «") and self.from_user):
            return await original_answer(self, text, *args, **kwargs)

        internal_user_id = _TG_TO_USER.get(int(self.from_user.id))
        if internal_user_id is None:
            try:
                user = await module.ensure_user(self.from_user)
                internal_user_id = int(user["id"])
                _TG_TO_USER[int(self.from_user.id)] = internal_user_id
            except Exception:
                internal_user_id = None

        join_result = _JOIN_RESULT_BY_USER.pop(internal_user_id, None) if internal_user_id else None

        # Existing member opening the same deep-link again must not trigger a fake join notice.
        if join_result and not join_result[1]:
            group_id = join_result[0]
            try:
                group = await module.get_group(group_id)
                text = f"ℹ️ شما قبلاً عضو حساب «{escape(group['name'])}» بودید."
                kwargs["reply_markup"] = module.group_menu(group_id)
                kwargs["parse_mode"] = "HTML"
            except Exception:
                pass
            return await original_answer(self, text, *args, **kwargs)

        result = await original_answer(self, text, *args, **kwargs)

        if not join_result or not join_result[1] or internal_user_id is None:
            return result

        group_id = join_result[0]
        try:
            group = await module.get_group(group_id)
            members = await module.get_members(group_id)
            new_name = self.from_user.full_name or str(self.from_user.id)
            notice = (
                "👋 <b>عضو جدید به حساب اضافه شد</b>\n\n"
                f"<b>{escape(new_name)}</b> به حساب «<b>{escape(group['name'])}</b>» پیوست."
            )

            for member in members:
                telegram_id = member.get("telegram_id")
                member_user_id = member.get("user_id")
                if not telegram_id or member_user_id is None:
                    continue
                if int(member_user_id) == int(internal_user_id):
                    continue

                buttons = [[InlineKeyboardButton(text="💼 مشاهده حساب", callback_data=f"group:{group_id}")]]
                if member.get("role") in {"owner", "admin"}:
                    buttons.append([
                        InlineKeyboardButton(
                            text="👤 مدیریت هزینه‌های قبلی برای عضو جدید",
                            callback_data=f"retro:start:{group_id}",
                        )
                    ])
                buttons.append([InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="ux:home")])

                try:
                    await self.bot.send_message(
                        int(telegram_id),
                        notice,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                        parse_mode="HTML",
                    )
                except Exception:
                    continue
        except Exception:
            pass

        return result

    Message.answer = answer_with_join_notification
