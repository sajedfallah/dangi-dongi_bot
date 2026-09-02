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
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    await engine.dispose()


async def create_user(client: AsyncClient, telegram_id: int, name: str) -> dict:
    response = await client.post("/api/v1/users", json={"telegram_id": telegram_id, "display_name": name})
    assert response.status_code == 200
    return response.json()


async def create_group(client: AsyncClient, owner_id: int) -> dict:
    response = await client.post("/api/v1/groups", json={
        "name": "Trip",
        "owner_user_id": owner_id,
        "currency": "IRT",
    })
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_expense_delete_rbac_and_audit(client: AsyncClient):
    owner = await create_user(client, 101, "Owner")
    member = await create_user(client, 102, "Member")
    group = await create_group(client, owner["id"])

    add_member = await client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": member["id"]},
    )
    assert add_member.status_code == 200

    expense = await client.post(f"/api/v1/groups/{group['id']}/expenses", json={
        "actor_user_id": owner["id"],
        "paid_by_user_id": member["id"],
        "amount": "100000",
        "title": "Dinner",
        "participant_user_ids": [owner["id"], member["id"]],
    })
    assert expense.status_code == 200
    expense_id = expense.json()["id"]

    denied = await client.request(
        "DELETE",
        f"/api/v1/groups/{group['id']}/expenses/{expense_id}",
        json={"actor_user_id": member["id"]},
    )
    assert denied.status_code == 403

    audit_denied = await client.get(
        f"/api/v1/groups/{group['id']}/audit",
        params={"actor_user_id": member["id"]},
    )
    assert audit_denied.status_code == 403

    deleted = await client.request(
        "DELETE",
        f"/api/v1/groups/{group['id']}/expenses/{expense_id}",
        json={"actor_user_id": owner["id"]},
    )
    assert deleted.status_code == 200

    audit = await client.get(
        f"/api/v1/groups/{group['id']}/audit",
        params={"actor_user_id": owner["id"]},
    )
    assert audit.status_code == 200
    actions = [item["action"] for item in audit.json()]
    assert "expense.created" in actions
    assert "expense.deleted" in actions


@pytest.mark.asyncio
async def test_owner_can_promote_admin_and_admin_can_manage_expense(client: AsyncClient):
    owner = await create_user(client, 201, "Owner")
    admin = await create_user(client, 202, "Admin")
    group = await create_group(client, owner["id"])
    await client.post(f"/api/v1/groups/{group['id']}/members", json={"user_id": admin["id"]})

    promoted = await client.patch(
        f"/api/v1/groups/{group['id']}/members/{admin['id']}/role",
        json={"actor_user_id": owner["id"], "role": "admin"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    expense = await client.post(f"/api/v1/groups/{group['id']}/expenses", json={
        "actor_user_id": owner["id"],
        "paid_by_user_id": owner["id"],
        "amount": "50000",
        "title": "Taxi",
        "participant_user_ids": [owner["id"], admin["id"]],
    })
    assert expense.status_code == 200

    deleted = await client.request(
        "DELETE",
        f"/api/v1/groups/{group['id']}/expenses/{expense.json()['id']}",
        json={"actor_user_id": admin["id"]},
    )
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_settlement_cannot_be_registered_for_another_debtor(client: AsyncClient):
    owner = await create_user(client, 301, "Owner")
    debtor = await create_user(client, 302, "Debtor")
    group = await create_group(client, owner["id"])
    await client.post(f"/api/v1/groups/{group['id']}/members", json={"user_id": debtor["id"]})

    response = await client.post(f"/api/v1/groups/{group['id']}/settlements", json={
        "actor_user_id": owner["id"],
        "from_user_id": debtor["id"],
        "to_user_id": owner["id"],
        "amount": "1000",
    })
    assert response.status_code == 403
