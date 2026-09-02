from __future__ import annotations

import re
from html import escape

from aiogram.types import Message


_INSTALLED = False
_TG_TO_USER: dict[int, int] = {}
_PENDING_JOIN_BY_USER: dict[int, int] = {}
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
                if url == "/api/v1/users" and response.status_code < 400:
                    payload = kwargs.get("json") or {}
                    telegram_id = payload.get("telegram_id")
                    body = response.json()
                    if telegram_id is not None and body.get("id") is not None:
                        _TG_TO_USER[int(telegram_id)] = int(body["id"])
                else:
                    match = _MEMBER_PATH.match(str(url))
                    if match and response.status_code < 400:
                        payload = kwargs.get("json") or {}
                        user_id = payload.get("user_id")
                        body = response.json()
                        if user_id is not None and body.get("already_member") is False:
                            _PENDING_JOIN_BY_USER[int(user_id)] = int(match.group(1))
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
        result = await original_answer(self, text, *args, **kwargs)

        if isinstance(text, str) and text.startswith("✅ به حساب «") and self.from_user:
            internal_user_id = _TG_TO_USER.get(int(self.from_user.id))
            group_id = _PENDING_JOIN_BY_USER.pop(internal_user_id, None) if internal_user_id else None
            if group_id:
                try:
                    group = await module.get_group(group_id)
                    members = await module.get_members(group_id)
                    new_name = self.from_user.full_name or str(self.from_user.id)
                    notice = (
                        "👋 <b>عضو جدید</b>\n\n"
                        f"<b>{escape(new_name)}</b> به حساب «<b>{escape(group['name'])}</b>» پیوست."
                    )
                    for member in members:
                        telegram_id = member.get("telegram_id")
                        if not telegram_id or int(member["user_id"]) == int(internal_user_id):
                            continue
                        try:
                            await self.bot.send_message(int(telegram_id), notice, parse_mode="HTML")
                        except Exception:
                            continue
                except Exception:
                    pass

        return result

    Message.answer = answer_with_join_notification
