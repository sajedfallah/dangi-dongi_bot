from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request

from app.core.config import settings


@dataclass(frozen=True)
class AuthContext:
    kind: str
    telegram_id: int | None = None


def verify_telegram_init_data(init_data: str) -> int:
    if not settings.telegram_bot_token:
        raise HTTPException(503, "telegram bot token is not configured")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "missing Telegram initData hash")
    auth_date_raw = pairs.get("auth_date")
    try:
        auth_date = int(auth_date_raw or "0")
    except ValueError as exc:
        raise HTTPException(401, "invalid Telegram auth_date") from exc
    now = int(time.time())
    if auth_date <= 0 or abs(now - auth_date) > settings.telegram_init_data_max_age_seconds:
        raise HTTPException(401, "Telegram initData is expired")
    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(401, "invalid Telegram initData signature")
    try:
        user = json.loads(pairs.get("user", "{}"))
        telegram_id = int(user["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Telegram initData has no valid user") from exc
    return telegram_id


def authenticate_request(request: Request) -> AuthContext:
    service_token = request.headers.get("x-service-token", "")
    if service_token and hmac.compare_digest(service_token, settings.service_api_token):
        return AuthContext(kind="service")

    init_data = request.headers.get("x-telegram-init-data", "")
    if init_data:
        return AuthContext(kind="telegram", telegram_id=verify_telegram_init_data(init_data))

    if settings.env == "development" and not settings.api_auth_required:
        return AuthContext(kind="development")
    raise HTTPException(401, "authentication required")
