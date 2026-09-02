import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.entities import AuditLog, Expense, ExpenseShare, Group, GroupMember, Settlement, User
from app.schemas.common import (
    AuditLogOut,
    BalanceItem,
    ExpenseCreate,
    ExpenseDelete,
    ExpenseDetailOut,
    ExpenseHistoryItem,
    ExpenseOut,
    ExpenseShareOut,
    ExpenseUpdate,
    GroupCreate,
    GroupOut,
    MemberAdd,
    MemberOut,
    MemberRoleUpdate,
    SettlementCreate,
    TransferSuggestion,
    UserCreate,
    UserOut,
)
from app.services.ledger import (
    calculate_balances,
    create_expense,
    deserialize_split_config,
    q,
    simplify_debts,
    update_expense,
)

router = APIRouter(prefix="/api/v1")


async def require_group(db: AsyncSession, group_id: int) -> Group:
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "group not found")
    return group


async def require_member(db: AsyncSession, group_id: int, user_id: int) -> GroupMember:
    member = (await db.execute(select(GroupMember).where(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
    ))).scalar_one_or_none()
    if not member:
        raise HTTPException(403, "user is not a member of this group")
    return member


async def require_manager(db: AsyncSession, group_id: int, user_id: int) -> GroupMember:
    member = await require_member(db, group_id, user_id)
    if member.role not in {"owner", "admin"}:
        raise HTTPException(403, "owner or admin role required")
    return member


async def require_expense_manager(db: AsyncSession, expense: Expense, actor_user_id: int) -> GroupMember:
    member = await require_member(db, expense.group_id, actor_user_id)
    if member.role in {"owner", "admin"}:
        return member
    if expense.created_by_user_id != actor_user_id:
        raise HTTPException(403, "you can only manage expenses you created")
    return member


def audit(db, group_id, actor_user_id, action, entity_type, entity_id, details=None):
    db.add(AuditLog(
        group_id=group_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=json.dumps(details, ensure_ascii=False, default=str) if details else None,
    ))


@router.post("/users", response_model=UserOut)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    if payload.telegram_id is not None:
        existing = (await db.execute(select(User).where(User.telegram_id == payload.telegram_id))).scalar_one_or_none()
        if existing:
            if existing.display_name != payload.display_name:
                existing.display_name = payload.display_name
                await db.commit()
                await db.refresh(existing)
            return existing
    user = User(**payload.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/users/{user_id}/groups", response_model=list[GroupOut])
async def user_groups(user_id: int, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, user_id):
        raise HTTPException(404, "user not found")
    rows = await db.execute(select(Group).join(GroupMember).where(GroupMember.user_id == user_id).order_by(Group.created_at.desc()))
    return list(rows.scalars().all())


@router.post("/groups", response_model=GroupOut)
async def create_group(payload: GroupCreate, db: AsyncSession = Depends(get_db)):
    owner = await db.get(User, payload.owner_user_id)
    if not owner:
        raise HTTPException(404, "owner user not found")
    group = Group(**payload.model_dump())
    db.add(group)
    await db.flush()
    db.add(GroupMember(group_id=group.id, user_id=owner.id, role="owner"))
    audit(db, group.id, owner.id, "group.created", "group", group.id, {"name": group.name})
    await db.commit()
    await db.refresh(group)
    return group


@router.get("/groups/{group_id}", response_model=GroupOut)
async def group_detail(group_id: int, db: AsyncSession = Depends(get_db)):
    return await require_group(db, group_id)


@router.get("/groups/{group_id}/members", response_model=list[MemberOut])
async def group_members(group_id: int, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    rows = await db.execute(select(GroupMember, User).join(User, User.id == GroupMember.user_id).where(GroupMember.group_id == group_id).order_by(GroupMember.joined_at.asc()))
    return [MemberOut(user_id=user.id, display_name=user.display_name, telegram_id=user.telegram_id, role=member.role) for member, user in rows.all()]


@router.post("/groups/{group_id}/members")
async def add_member(group_id: int, payload: MemberAdd, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    if not await db.get(User, payload.user_id):
        raise HTTPException(404, "user not found")
    existing = (await db.execute(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == payload.user_id))).scalar_one_or_none()
    if existing:
        return {"ok": True, "member_id": existing.id, "already_member": True}
    member = GroupMember(group_id=group_id, user_id=payload.user_id)
    db.add(member)
    audit(db, group_id, payload.user_id, "member.joined", "member", payload.user_id)
    await db.commit()
    await db.refresh(member)
    return {"ok": True, "member_id": member.id, "already_member": False}


@router.patch("/groups/{group_id}/members/{user_id}/role")
async def change_member_role(group_id: int, user_id: int, payload: MemberRoleUpdate, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    actor = await require_member(db, group_id, payload.actor_user_id)
    if actor.role != "owner":
        raise HTTPException(403, "only the owner can change member roles")
    target = await require_member(db, group_id, user_id)
    if target.role == "owner":
        raise HTTPException(400, "owner role cannot be changed here")
    old_role = target.role
    target.role = payload.role
    audit(db, group_id, payload.actor_user_id, "member.role_changed", "member", user_id, {"old_role": old_role, "new_role": payload.role})
    await db.commit()
    return {"ok": True, "user_id": user_id, "role": target.role}


@router.post("/groups/{group_id}/expenses", response_model=ExpenseOut)
async def add_expense(group_id: int, payload: ExpenseCreate, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    await require_member(db, group_id, payload.actor_user_id)
    try:
        expense = await create_expense(db, group_id, payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    audit(db, group_id, payload.actor_user_id, "expense.created", "expense", expense.id, {
        "amount": expense.amount, "title": expense.title, "paid_by_user_id": expense.paid_by_user_id, "split_mode": expense.split_mode,
    })
    await db.commit()
    await db.refresh(expense)
    return expense


@router.get("/groups/{group_id}/expenses/{expense_id}", response_model=ExpenseDetailOut)
async def expense_detail(group_id: int, expense_id: int, actor_user_id: int, db: AsyncSession = Depends(get_db)):
    await require_member(db, group_id, actor_user_id)
    expense = (await db.execute(select(Expense).where(Expense.id == expense_id, Expense.group_id == group_id).options(selectinload(Expense.shares)))).scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "expense not found")
    return ExpenseDetailOut(
        id=expense.id,
        group_id=expense.group_id,
        paid_by_user_id=expense.paid_by_user_id,
        created_by_user_id=expense.created_by_user_id,
        amount=expense.amount,
        title=expense.title,
        split_mode=expense.split_mode,
        split_values=deserialize_split_config(expense.split_config),
        participant_user_ids=[share.user_id for share in expense.shares],
        shares=[ExpenseShareOut(user_id=share.user_id, amount=share.amount) for share in expense.shares],
        category=expense.category,
        note=expense.note,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
    )


@router.put("/groups/{group_id}/expenses/{expense_id}", response_model=ExpenseOut)
async def edit_expense(group_id: int, expense_id: int, payload: ExpenseUpdate, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    expense = await db.get(Expense, expense_id)
    if not expense or expense.group_id != group_id:
        raise HTTPException(404, "expense not found")
    await require_expense_manager(db, expense, payload.actor_user_id)
    before = {"amount": expense.amount, "title": expense.title, "paid_by_user_id": expense.paid_by_user_id, "split_mode": expense.split_mode}
    try:
        expense = await update_expense(db, expense, payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    audit(db, group_id, payload.actor_user_id, "expense.updated", "expense", expense.id, {
        "before": before,
        "after": {"amount": expense.amount, "title": expense.title, "paid_by_user_id": expense.paid_by_user_id, "split_mode": expense.split_mode},
    })
    await db.commit()
    await db.refresh(expense)
    return expense


@router.delete("/groups/{group_id}/expenses/{expense_id}")
async def remove_expense(group_id: int, expense_id: int, payload: ExpenseDelete, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    expense = await db.get(Expense, expense_id)
    if not expense or expense.group_id != group_id:
        raise HTTPException(404, "expense not found")
    await require_expense_manager(db, expense, payload.actor_user_id)
    snapshot = {"amount": expense.amount, "title": expense.title, "paid_by_user_id": expense.paid_by_user_id, "created_by_user_id": expense.created_by_user_id, "split_mode": expense.split_mode}
    await db.execute(delete(ExpenseShare).where(ExpenseShare.expense_id == expense.id))
    await db.delete(expense)
    audit(db, group_id, payload.actor_user_id, "expense.deleted", "expense", expense_id, snapshot)
    await db.commit()
    return {"ok": True, "expense_id": expense_id}


@router.get("/groups/{group_id}/expenses", response_model=list[ExpenseHistoryItem])
async def expense_history(group_id: int, limit: int = 20, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    safe_limit = min(max(limit, 1), 100)
    rows = await db.execute(select(Expense, User).join(User, User.id == Expense.paid_by_user_id).where(Expense.group_id == group_id).order_by(Expense.created_at.desc()).limit(safe_limit))
    return [ExpenseHistoryItem(id=e.id, title=e.title, amount=e.amount, paid_by_user_id=u.id, paid_by_name=u.display_name, created_by_user_id=e.created_by_user_id, split_mode=e.split_mode, category=e.category, created_at=e.created_at) for e, u in rows.all()]


@router.get("/groups/{group_id}/audit", response_model=list[AuditLogOut])
async def audit_history(group_id: int, actor_user_id: int, limit: int = 50, db: AsyncSession = Depends(get_db)):
    await require_manager(db, group_id, actor_user_id)
    safe_limit = min(max(limit, 1), 200)
    rows = await db.execute(select(AuditLog).where(AuditLog.group_id == group_id).order_by(AuditLog.created_at.desc()).limit(safe_limit))
    return list(rows.scalars().all())


@router.get("/groups/{group_id}/balances", response_model=list[BalanceItem])
async def balances(group_id: int, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    values = await calculate_balances(db, group_id)
    return [BalanceItem(user_id=uid, balance=amount) for uid, amount in values.items()]


@router.get("/groups/{group_id}/settlement-plan", response_model=list[TransferSuggestion])
async def settlement_plan(group_id: int, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    return [TransferSuggestion(**item) for item in simplify_debts(await calculate_balances(db, group_id))]


@router.post("/groups/{group_id}/settlements")
async def settle(group_id: int, payload: SettlementCreate, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    await require_member(db, group_id, payload.actor_user_id)
    if payload.actor_user_id != payload.from_user_id:
        raise HTTPException(403, "only the debtor can register this settlement")
    if payload.from_user_id == payload.to_user_id:
        raise HTTPException(400, "from and to users must differ")
    members = set((await db.execute(select(GroupMember.user_id).where(GroupMember.group_id == group_id))).scalars().all())
    if payload.from_user_id not in members or payload.to_user_id not in members:
        raise HTTPException(400, "both users must be group members")
    st = Settlement(group_id=group_id, amount=q(payload.amount), from_user_id=payload.from_user_id, to_user_id=payload.to_user_id)
    db.add(st)
    await db.flush()
    audit(db, group_id, payload.actor_user_id, "settlement.created", "settlement", st.id, {"from_user_id": st.from_user_id, "to_user_id": st.to_user_id, "amount": st.amount})
    await db.commit()
    await db.refresh(st)
    return {"ok": True, "settlement_id": st.id}
