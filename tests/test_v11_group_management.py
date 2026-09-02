import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.group_management import router as management_router
from app.api.routes import router as api_router
from app.db.session import get_db
from app.models.entities import Base


@pytest.mark.asyncio
async def test_custom_categories_and_safe_group_delete():
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
    app.include_router(management_router)

    async def override_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        owner = (await client.post("/api/v1/users", json={"telegram_id": 9101, "display_name": "Owner"})).json()
        member = (await client.post("/api/v1/users", json={"telegram_id": 9102, "display_name": "Member"})).json()
        group = (await client.post("/api/v1/groups", json={
            "name": "V11 Trip", "owner_user_id": owner["id"], "currency": "IRT"
        })).json()
        await client.post(f"/api/v1/groups/{group['id']}/members", json={"user_id": member["id"]})

        created = await client.post(
            f"/api/v1/management/groups/{group['id']}/categories",
            json={"actor_user_id": owner["id"], "name": "عوارض"},
        )
        assert created.status_code == 200
        category = created.json()
        assert category["already_exists"] is False

        listed = await client.get(
            f"/api/v1/management/groups/{group['id']}/categories",
            params={"actor_user_id": member["id"]},
        )
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()] == ["عوارض"]

        expense = (await client.post(f"/api/v1/groups/{group['id']}/expenses", json={
            "actor_user_id": owner["id"],
            "paid_by_user_id": owner["id"],
            "amount": "100000",
            "title": "Road fee",
            "participant_user_ids": [owner["id"], member["id"]],
            "split_mode": "equal",
            "category": "عوارض",
        })).json()

        preview = (await client.get(
            f"/api/v1/management/groups/{group['id']}/delete-preview",
            params={"actor_user_id": owner["id"]},
        )).json()
        assert preview["can_permanently_delete"] is False
        assert preview["unresolved_transfer_count"] == 1
        assert preview["expense_count"] == 1
        assert preview["custom_category_count"] == 1

        blocked = await client.request(
            "DELETE",
            f"/api/v1/management/groups/{group['id']}",
            json={"actor_user_id": owner["id"], "confirmation": "V11 Trip"},
        )
        assert blocked.status_code == 409

        removed_expense = await client.request(
            "DELETE",
            f"/api/v1/groups/{group['id']}/expenses/{expense['id']}",
            json={"actor_user_id": owner["id"]},
        )
        assert removed_expense.status_code == 200

        allowed = (await client.get(
            f"/api/v1/management/groups/{group['id']}/delete-preview",
            params={"actor_user_id": owner["id"]},
        )).json()
        assert allowed["can_permanently_delete"] is True

        wrong = await client.request(
            "DELETE",
            f"/api/v1/management/groups/{group['id']}",
            json={"actor_user_id": owner["id"], "confirmation": "wrong"},
        )
        assert wrong.status_code == 400

        deleted = await client.request(
            "DELETE",
            f"/api/v1/management/groups/{group['id']}",
            json={"actor_user_id": owner["id"], "confirmation": "V11 Trip"},
        )
        assert deleted.status_code == 200
        assert deleted.json()["ok"] is True

        missing = await client.get(f"/api/v1/groups/{group['id']}")
        assert missing.status_code == 404

    await engine.dispose()
