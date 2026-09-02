import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.dashboard import router as dashboard_router
from app.api.routes import router as api_router
from app.db.session import get_db
from app.models.entities import Base


@pytest.mark.asyncio
async def test_dashboard_keeps_owned_groups_separate_from_memberships():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(api_router)
    app.include_router(dashboard_router)

    async def override_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        alice = (await client.post("/api/v1/users", json={"telegram_id": 8101, "display_name": "Alice"})).json()
        bob = (await client.post("/api/v1/users", json={"telegram_id": 8102, "display_name": "Bob"})).json()

        alice_group = (await client.post("/api/v1/dashboard/groups", json={
            "name": "Alice Trip", "owner_user_id": alice["id"], "currency": "IRT"
        })).json()
        bob_group = (await client.post("/api/v1/dashboard/groups", json={
            "name": "Bob Trip", "owner_user_id": bob["id"], "currency": "IRT"
        })).json()
        await client.post(f"/api/v1/groups/{bob_group['id']}/members", json={"user_id": alice["id"]})

        groups = (await client.get(f"/api/v1/dashboard/users/{alice['id']}/groups")).json()
        assert len(groups) == 2
        owner_row = next(item for item in groups if item["id"] == alice_group["id"])
        member_row = next(item for item in groups if item["id"] == bob_group["id"])
        assert owner_row["role"] == "owner"
        assert owner_row["counts_toward_free_limit"] is True
        assert member_row["role"] == "member"
        assert member_row["counts_toward_free_limit"] is False

        summary = (await client.get(f"/api/v1/dashboard/users/{alice['id']}/summary")).json()
        assert summary["owned_active_groups"] == 1
        assert summary["total_memberships"] == 2

        archived = await client.patch(
            f"/api/v1/dashboard/groups/{alice_group['id']}/archive",
            json={"actor_user_id": alice["id"], "is_archived": True},
        )
        assert archived.status_code == 200
        active_groups = (await client.get(f"/api/v1/dashboard/users/{alice['id']}/groups")).json()
        assert all(item["id"] != alice_group["id"] for item in active_groups)
        archived_groups = (await client.get(
            f"/api/v1/dashboard/users/{alice['id']}/groups", params={"archived": "true"}
        )).json()
        assert any(item["id"] == alice_group["id"] for item in archived_groups)

        restored = await client.patch(
            f"/api/v1/dashboard/groups/{alice_group['id']}/archive",
            json={"actor_user_id": alice["id"], "is_archived": False},
        )
        assert restored.status_code == 200

    await engine.dispose()
