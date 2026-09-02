from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import (
    AuditLog,
    DebtReminderState,
    Expense,
    ExpenseShare,
    Group,
    GroupCategory,
    GroupMember,
    Settlement,
)
from app.services.ledger import calculate_balances, simplify_debts

router = APIRouter(prefix="/api/v1/management", tags=["group-management"])


class CategoryCreate(BaseModel):
    actor_user_id: int
    name: str = Field(min_length=1, max_length=60)


class CategoryDelete(BaseModel):
    actor_user_id: int


class GroupDeleteRequest(BaseModel):
    actor_user_id: int
    confirmation: str


async def _group(db: AsyncSession, group_id: int) -> Group:
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "group not found")
    return group


async def _member(db: AsyncSession, group_id: int, user_id: int) -> GroupMember:
    row = (await db.execute(select(GroupMember).where(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
    ))).scalar_one_or_none()
    if not row:
        raise HTTPException(403, "group membership required")
    return row


async def _manager(db: AsyncSession, group_id: int, user_id: int) -> GroupMember:
    row = await _member(db, group_id, user_id)
    if row.role not in {"owner", "admin"}:
        raise HTTPException(403, "owner or admin role required")
    return row


async def _owner(db: AsyncSession, group_id: int, user_id: int) -> GroupMember:
    row = await _member(db, group_id, user_id)
    if row.role != "owner":
        raise HTTPException(403, "only the owner can permanently delete this group")
    return row


@router.get("/groups/{group_id}/categories")
async def list_categories(group_id: int, actor_user_id: int, db: AsyncSession = Depends(get_db)):
    await _member(db, group_id, actor_user_id)
    rows = (await db.execute(
        select(GroupCategory)
        .where(GroupCategory.group_id == group_id)
        .order_by(GroupCategory.name.asc())
    )).scalars().all()
    return [
        {
            "id": row.id,
            "group_id": row.group_id,
            "name": row.name,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/groups/{group_id}/categories")
async def create_category(group_id: int, payload: CategoryCreate, db: AsyncSession = Depends(get_db)):
    await _group(db, group_id)
    await _manager(db, group_id, payload.actor_user_id)
    name = " ".join(payload.name.strip().split())
    if not name:
        raise HTTPException(400, "category name cannot be empty")
    existing = (await db.execute(select(GroupCategory).where(
        GroupCategory.group_id == group_id,
        func.lower(GroupCategory.name) == name.lower(),
    ))).scalar_one_or_none()
    if existing:
        return {"ok": True, "category_id": existing.id, "name": existing.name, "already_exists": True}
    row = GroupCategory(group_id=group_id, name=name, created_by_user_id=payload.actor_user_id)
    db.add(row)
    await db.flush()
    db.add(AuditLog(
        group_id=group_id,
        actor_user_id=payload.actor_user_id,
        action="category.created",
        entity_type="category",
        entity_id=row.id,
        details=name,
    ))
    await db.commit()
    await db.refresh(row)
    return {"ok": True, "category_id": row.id, "name": row.name, "already_exists": False}


@router.delete("/groups/{group_id}/categories/{category_id}")
async def delete_category(group_id: int, category_id: int, payload: CategoryDelete, db: AsyncSession = Depends(get_db)):
    await _manager(db, group_id, payload.actor_user_id)
    row = await db.get(GroupCategory, category_id)
    if not row or row.group_id != group_id:
        raise HTTPException(404, "category not found")
    # Historical expenses intentionally keep their category text for reporting/audit integrity.
    db.add(AuditLog(
        group_id=group_id,
        actor_user_id=payload.actor_user_id,
        action="category.deleted",
        entity_type="category",
        entity_id=row.id,
        details=row.name,
    ))
    await db.delete(row)
    await db.commit()
    return {"ok": True, "category_id": category_id, "historical_expenses_preserved": True}


@router.get("/groups/{group_id}/delete-preview")
async def delete_preview(group_id: int, actor_user_id: int, db: AsyncSession = Depends(get_db)):
    group = await _group(db, group_id)
    await _owner(db, group_id, actor_user_id)

    transfers = simplify_debts(await calculate_balances(db, group_id))
    unresolved_total = sum((Decimal(str(item["amount"])) for item in transfers), Decimal("0"))
    pending = int((await db.execute(select(func.count(Settlement.id)).where(
        Settlement.group_id == group_id,
        Settlement.status == "pending",
    ))).scalar_one())
    expense_count = int((await db.execute(select(func.count(Expense.id)).where(Expense.group_id == group_id))).scalar_one())
    member_count = int((await db.execute(select(func.count(GroupMember.id)).where(GroupMember.group_id == group_id))).scalar_one())
    category_count = int((await db.execute(select(func.count(GroupCategory.id)).where(GroupCategory.group_id == group_id))).scalar_one())
    blocked = bool(transfers or pending)
    reasons = []
    if transfers:
        reasons.append("unresolved_debts")
    if pending:
        reasons.append("pending_settlements")
    return {
        "group_id": group.id,
        "group_name": group.name,
        "is_archived": group.is_archived,
        "can_permanently_delete": not blocked,
        "blocked_reasons": reasons,
        "unresolved_transfer_count": len(transfers),
        "unresolved_total": str(unresolved_total),
        "pending_settlement_count": pending,
        "expense_count": expense_count,
        "member_count": member_count,
        "custom_category_count": category_count,
        "required_confirmation": group.name,
    }


@router.delete("/groups/{group_id}")
async def permanently_delete_group(group_id: int, payload: GroupDeleteRequest, db: AsyncSession = Depends(get_db)):
    group = await _group(db, group_id)
    await _owner(db, group_id, payload.actor_user_id)
    if payload.confirmation.strip() != group.name:
        raise HTTPException(400, "confirmation must exactly match group name")

    transfers = simplify_debts(await calculate_balances(db, group_id))
    pending = int((await db.execute(select(func.count(Settlement.id)).where(
        Settlement.group_id == group_id,
        Settlement.status == "pending",
    ))).scalar_one())
    if transfers or pending:
        raise HTTPException(409, {
            "message": "group has unresolved financial activity",
            "unresolved_transfer_count": len(transfers),
            "pending_settlement_count": pending,
            "suggestion": "settle debts or archive the group instead",
        })

    expense_ids = list((await db.execute(select(Expense.id).where(Expense.group_id == group_id))).scalars().all())
    if expense_ids:
        await db.execute(delete(ExpenseShare).where(ExpenseShare.expense_id.in_(expense_ids)))
    await db.execute(delete(DebtReminderState).where(DebtReminderState.group_id == group_id))
    await db.execute(delete(Settlement).where(Settlement.group_id == group_id))
    await db.execute(delete(AuditLog).where(AuditLog.group_id == group_id))
    await db.execute(delete(GroupCategory).where(GroupCategory.group_id == group_id))
    await db.execute(delete(Expense).where(Expense.group_id == group_id))
    await db.execute(delete(GroupMember).where(GroupMember.group_id == group_id))
    await db.delete(group)
    await db.commit()
    return {"ok": True, "deleted_group_id": group_id, "deleted_group_name": group.name}
