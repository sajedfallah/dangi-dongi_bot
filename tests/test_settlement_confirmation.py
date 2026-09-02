import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.routes import router
from app.db.session import get_db
from app.models.entities import Base


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await engine.dispose()


async def user(client, telegram_id, name):
    r = await client.post("/api/v1/users", json={"telegram_id": telegram_id, "display_name": name})
    assert r.status_code == 200
    return r.json()


@pytest.mark.asyncio
async def test_pending_settlement_does_not_change_balance_until_creditor_confirms(client: AsyncClient):
    owner = await user(client, 501, "Owner")
    debtor = await user(client, 502, "Debtor")
    group = (await client.post("/api/v1/groups", json={
        "name": "Trip", "owner_user_id": owner["id"], "currency": "IRT",
    })).json()
    await client.post(f"/api/v1/groups/{group['id']}/members", json={"user_id": debtor["id"]})

    expense = await client.post(f"/api/v1/groups/{group['id']}/expenses", json={
        "actor_user_id": owner["id"],
        "paid_by_user_id": owner["id"],
        "amount": "1000",
        "title": "Dinner",
        "participant_user_ids": [owner["id"], debtor["id"]],
    })
    assert expense.status_code == 200

    before = {x["user_id"]: x["balance"] for x in (await client.get(f"/api/v1/groups/{group['id']}/balances")).json()}
    assert before[owner["id"]] == "500.00"
    assert before[debtor["id"]] == "-500.00"

    requested = await client.post(f"/api/v1/groups/{group['id']}/settlements", json={
        "actor_user_id": debtor["id"],
        "from_user_id": debtor["id"],
        "to_user_id": owner["id"],
        "amount": "500",
    })
    assert requested.status_code == 200
    st = requested.json()
    assert st["status"] == "pending"

    still_pending = {x["user_id"]: x["balance"] for x in (await client.get(f"/api/v1/groups/{group['id']}/balances")).json()}
    assert still_pending == before

    wrong_actor = await client.post(
        f"/api/v1/groups/{group['id']}/settlements/{st['id']}/confirm",
        json={"actor_user_id": debtor["id"]},
    )
    assert wrong_actor.status_code == 403

    confirmed = await client.post(
        f"/api/v1/groups/{group['id']}/settlements/{st['id']}/confirm",
        json={"actor_user_id": owner["id"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    after = {x["user_id"]: x["balance"] for x in (await client.get(f"/api/v1/groups/{group['id']}/balances")).json()}
    assert after[owner["id"]] == "0.00"
    assert after[debtor["id"]] == "0.00"


@pytest.mark.asyncio
async def test_rejected_settlement_never_changes_balance(client: AsyncClient):
    owner = await user(client, 601, "Owner")
    debtor = await user(client, 602, "Debtor")
    group = (await client.post("/api/v1/groups", json={
        "name": "Home", "owner_user_id": owner["id"], "currency": "IRT",
    })).json()
    await client.post(f"/api/v1/groups/{group['id']}/members", json={"user_id": debtor["id"]})
    await client.post(f"/api/v1/groups/{group['id']}/expenses", json={
        "actor_user_id": owner["id"], "paid_by_user_id": owner["id"], "amount": "2000",
        "title": "Groceries", "participant_user_ids": [owner["id"], debtor["id"]],
    })

    requested = (await client.post(f"/api/v1/groups/{group['id']}/settlements", json={
        "actor_user_id": debtor["id"], "from_user_id": debtor["id"], "to_user_id": owner["id"], "amount": "1000",
    })).json()
    rejected = await client.post(
        f"/api/v1/groups/{group['id']}/settlements/{requested['id']}/reject",
        json={"actor_user_id": owner["id"]},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    balances = {x["user_id"]: x["balance"] for x in (await client.get(f"/api/v1/groups/{group['id']}/balances")).json()}
    assert balances[owner["id"]] == "1000.00"
    assert balances[debtor["id"]] == "-1000.00"
