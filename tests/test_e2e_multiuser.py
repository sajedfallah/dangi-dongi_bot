import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.routes import router
from app.core.config import settings
from app.core.middleware import SecurityMiddleware
from app.db.session import get_db
from app.models.entities import Base


@pytest_asyncio.fixture
async def secure_client(monkeypatch):
    monkeypatch.setattr(settings, "service_api_token", "e2e-service-token")
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.add_middleware(SecurityMiddleware)
    app.include_router(router)

    async def override_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Service-Token": "e2e-service-token"},
    ) as client:
        yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_multi_user_expense_and_confirmed_settlement_e2e(secure_client: AsyncClient):
    alice = (await secure_client.post("/api/v1/users", json={
        "telegram_id": 10001,
        "display_name": "Alice",
    })).json()
    bob = (await secure_client.post("/api/v1/users", json={
        "telegram_id": 10002,
        "display_name": "Bob",
    })).json()

    group_response = await secure_client.post("/api/v1/groups", json={
        "name": "Weekend",
        "owner_user_id": alice["id"],
        "currency": "IRT",
    })
    assert group_response.status_code == 200
    group = group_response.json()
    assert (await secure_client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": bob["id"]},
    )).status_code == 200

    expense = await secure_client.post(f"/api/v1/groups/{group['id']}/expenses", json={
        "actor_user_id": alice["id"],
        "paid_by_user_id": alice["id"],
        "amount": "200000",
        "title": "Dinner",
        "participant_user_ids": [alice["id"], bob["id"]],
        "split_mode": "equal",
    })
    assert expense.status_code == 200

    balances = (await secure_client.get(f"/api/v1/groups/{group['id']}/balances")).json()
    by_user = {item["user_id"]: item["balance"] for item in balances}
    assert by_user[alice["id"]] == "100000.00"
    assert by_user[bob["id"]] == "-100000.00"

    plan = (await secure_client.get(f"/api/v1/groups/{group['id']}/settlement-plan")).json()
    assert len(plan) == 1
    assert plan[0]["from_user_id"] == bob["id"]
    assert plan[0]["to_user_id"] == alice["id"]

    requested = await secure_client.post(f"/api/v1/groups/{group['id']}/settlements", json={
        "actor_user_id": bob["id"],
        "from_user_id": bob["id"],
        "to_user_id": alice["id"],
        "amount": "100000",
    })
    assert requested.status_code == 200
    settlement = requested.json()
    assert settlement["status"] == "pending"

    pending_balances = (await secure_client.get(f"/api/v1/groups/{group['id']}/balances")).json()
    pending_by_user = {item["user_id"]: item["balance"] for item in pending_balances}
    assert pending_by_user == by_user

    confirmed = await secure_client.post(
        f"/api/v1/groups/{group['id']}/settlements/{settlement['id']}/confirm",
        json={"actor_user_id": alice["id"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    final_balances = (await secure_client.get(f"/api/v1/groups/{group['id']}/balances")).json()
    assert all(item["balance"] == "0.00" for item in final_balances)
