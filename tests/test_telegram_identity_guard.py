import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.core.middleware as middleware_module
from app.api.routes import router
from app.core.config import settings
from app.core.middleware import SecurityMiddleware
from app.db.session import get_db
from app.models.entities import Base


def make_init_data(bot_token: str, telegram_id: int) -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "identity-test",
        "user": json.dumps({"id": telegram_id, "first_name": "Identity"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


@pytest.mark.asyncio
async def test_telegram_user_cannot_impersonate_another_internal_user(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:IDENTITY_TOKEN")
    monkeypatch.setattr(settings, "service_api_token", "identity-service-token")
    monkeypatch.setattr(settings, "api_auth_required", True)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(middleware_module, "SessionLocal", sessions)

    app = FastAPI()
    app.add_middleware(SecurityMiddleware)
    app.include_router(router)

    async def override_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        service_headers = {"X-Service-Token": "identity-service-token"}
        alice = (await client.post("/api/v1/users", headers=service_headers, json={
            "telegram_id": 501,
            "display_name": "Alice",
        })).json()
        bob = (await client.post("/api/v1/users", headers=service_headers, json={
            "telegram_id": 502,
            "display_name": "Bob",
        })).json()

        telegram_headers = {"X-Telegram-Init-Data": make_init_data(settings.telegram_bot_token, 501)}

        own = await client.get(f"/api/v1/users/{alice['id']}/groups", headers=telegram_headers)
        assert own.status_code == 200

        impersonation = await client.get(f"/api/v1/users/{bob['id']}/groups", headers=telegram_headers)
        assert impersonation.status_code == 403

        forged_owner = await client.post("/api/v1/groups", headers=telegram_headers, json={
            "name": "Forged",
            "owner_user_id": bob["id"],
            "currency": "IRT",
        })
        assert forged_owner.status_code == 403

        valid_group = await client.post("/api/v1/groups", headers=telegram_headers, json={
            "name": "Alice group",
            "owner_user_id": alice["id"],
            "currency": "IRT",
        })
        assert valid_group.status_code == 200

    await engine.dispose()
