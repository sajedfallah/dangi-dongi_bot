from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import AuditLog, Group, GroupMember, Settlement, User

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class DashboardGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner_user_id: int
    currency: str = "IRR"


class ArchiveAction(BaseModel):
    actor_user_id: int
    is_archived: bool = True


@router.get("/users/{user_id}/groups")
async def dashboard_groups(user_id: int, archived: bool = False, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, user_id):
        raise HTTPException(404, "user not found")
    rows = await db.execute(
        select(Group, GroupMember)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user_id, Group.is_archived == archived)
        .order_by(Group.created_at.desc())
    )
    return [
        {
            "id": group.id,
            "name": group.name,
            "currency": group.currency,
            "owner_user_id": group.owner_user_id,
            "role": membership.role,
            "is_archived": group.is_archived,
            "is_owned_by_user": group.owner_user_id == user_id,
            "counts_toward_free_limit": group.owner_user_id == user_id and not group.is_archived,
        }
        for group, membership in rows.all()
    ]


@router.get("/users/{user_id}/summary")
async def dashboard_summary(user_id: int, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, user_id):
        raise HTTPException(404, "user not found")
    owned_active = int((await db.execute(
        select(func.count(Group.id)).where(Group.owner_user_id == user_id, Group.is_archived.is_(False))
    )).scalar_one())
    memberships = int((await db.execute(
        select(func.count(GroupMember.id)).where(GroupMember.user_id == user_id)
    )).scalar_one())
    return {
        "owned_active_groups": owned_active,
        "total_memberships": memberships,
        "free_owned_group_limit": settings.free_owned_group_limit,
        "can_create_free_group": owned_active < settings.free_owned_group_limit,
        "remaining_free_groups": max(0, settings.free_owned_group_limit - owned_active),
    }


@router.post("/groups")
async def create_dashboard_group(payload: DashboardGroupCreate, db: AsyncSession = Depends(get_db)):
    owner = await db.get(User, payload.owner_user_id)
    if not owner:
        raise HTTPException(404, "owner user not found")
    owned_active = int((await db.execute(
        select(func.count(Group.id)).where(
            Group.owner_user_id == payload.owner_user_id,
            Group.is_archived.is_(False),
        )
    )).scalar_one())
    if owned_active >= settings.free_owned_group_limit:
        raise HTTPException(
            402,
            f"free plan allows {settings.free_owned_group_limit} active owned groups; upgrade is required",
        )
    group = Group(
        name=payload.name,
        owner_user_id=payload.owner_user_id,
        currency=payload.currency,
        is_archived=False,
    )
    db.add(group)
    await db.flush()
    db.add(GroupMember(group_id=group.id, user_id=owner.id, role="owner"))
    db.add(AuditLog(
        group_id=group.id,
        actor_user_id=owner.id,
        action="group.created",
        entity_type="group",
        entity_id=group.id,
        details=f'{{"name": "{group.name}"}}',
    ))
    await db.commit()
    await db.refresh(group)
    return {
        "id": group.id,
        "name": group.name,
        "currency": group.currency,
        "owner_user_id": group.owner_user_id,
        "is_archived": group.is_archived,
    }


@router.patch("/groups/{group_id}/archive")
async def archive_group(group_id: int, payload: ArchiveAction, db: AsyncSession = Depends(get_db)):
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "group not found")
    membership = (await db.execute(select(GroupMember).where(
        GroupMember.group_id == group_id,
        GroupMember.user_id == payload.actor_user_id,
    ))).scalar_one_or_none()
    if not membership or membership.role not in {"owner", "admin"}:
        raise HTTPException(403, "owner or admin role required")
    group.is_archived = payload.is_archived
    db.add(AuditLog(
        group_id=group_id,
        actor_user_id=payload.actor_user_id,
        action="group.archived" if payload.is_archived else "group.restored",
        entity_type="group",
        entity_id=group_id,
    ))
    await db.commit()
    return {"ok": True, "group_id": group_id, "is_archived": group.is_archived}


@router.get("/users/{user_id}/notifications")
async def dashboard_notifications(user_id: int, limit: int = 30, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, user_id):
        raise HTTPException(404, "user not found")
    group_ids = list((await db.execute(
        select(GroupMember.group_id).where(GroupMember.user_id == user_id)
    )).scalars().all())
    if not group_ids:
        return []
    safe_limit = min(max(limit, 1), 100)
    pending = (await db.execute(
        select(Settlement)
        .where(
            Settlement.group_id.in_(group_ids),
            Settlement.status == "pending",
            (Settlement.from_user_id == user_id) | (Settlement.to_user_id == user_id),
        )
        .order_by(Settlement.created_at.desc())
        .limit(safe_limit)
    )).scalars().all()
    notifications = [
        {
            "type": "settlement.pending",
            "group_id": item.group_id,
            "settlement_id": item.id,
            "from_user_id": item.from_user_id,
            "to_user_id": item.to_user_id,
            "amount": str(item.amount),
            "created_at": item.created_at,
            "requires_action": item.to_user_id == user_id,
        }
        for item in pending
    ]
    return notifications
