import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.api_security import verify_telegram_init_data
from app.core.config import settings
from app.core.middleware import SecurityMiddleware


def build_init_data(bot_token: str, telegram_id: int, auth_date: int | None = None) -> str:
    values = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAEAA-test-query",
        "user": json.dumps({"id": telegram_id, "first_name": "Test"}, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_valid_and_tampered_telegram_init_data(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST_TOKEN")
    init_data = build_init_data(settings.telegram_bot_token, 998877)
    assert verify_telegram_init_data(init_data) == 998877

    tampered = init_data.replace("998877", "998878")
    with pytest.raises(Exception):
        verify_telegram_init_data(tampered)


def test_expired_telegram_init_data(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST_TOKEN")
    monkeypatch.setattr(settings, "telegram_init_data_max_age_seconds", 60)
    init_data = build_init_data(settings.telegram_bot_token, 1001, int(time.time()) - 3600)
    with pytest.raises(Exception):
        verify_telegram_init_data(init_data)


@pytest.mark.asyncio
async def test_api_requires_auth_and_accepts_service_token(monkeypatch):
    monkeypatch.setattr(settings, "service_api_token", "unit-test-service-token")
    monkeypatch.setattr(settings, "api_auth_required", True)

    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.get("/api/v1/protected")
    async def protected():
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/api/v1/protected")
        assert denied.status_code == 401

        allowed = await client.get(
            "/api/v1/protected",
            headers={"X-Service-Token": "unit-test-service-token"},
        )
        assert allowed.status_code == 200
        assert allowed.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_rate_limit_for_authenticated_telegram_client(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST_TOKEN")
    monkeypatch.setattr(settings, "api_auth_required", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.get("/api/v1/protected")
    async def protected():
        return {"ok": True}

    init_data = build_init_data(settings.telegram_bot_token, 777)
    headers = {"X-Telegram-Init-Data": init_data}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/protected", headers=headers)).status_code == 200
        assert (await client.get("/api/v1/protected", headers=headers)).status_code == 200
        limited = await client.get("/api/v1/protected", headers=headers)
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers
