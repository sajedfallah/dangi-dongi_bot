from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.entities import Expense, Group, GroupMember, Settlement, User
from app.schemas.common import (
    BalanceItem,
    ExpenseCreate,
    ExpenseHistoryItem,
    ExpenseOut,
    GroupCreate,
    GroupOut,
    MemberAdd,
    MemberOut,
    SettlementCreate,
    TransferSuggestion,
    UserCreate,
    UserOut,
)
from app.services.ledger import calculate_balances, create_expense, q, simplify_debts

router = APIRouter(prefix="/api/v1")


async def require_group(db: AsyncSession, group_id: int) -> Group:
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "group not found")
    return group


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
    rows = await db.execute(
        select(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user_id)
        .order_by(Group.created_at.desc())
    )
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
    await db.commit()
    await db.refresh(group)
    return group


@router.get("/groups/{group_id}", response_model=GroupOut)
async def group_detail(group_id: int, db: AsyncSession = Depends(get_db)):
    return await require_group(db, group_id)


@router.get("/groups/{group_id}/members", response_model=list[MemberOut])
async def group_members(group_id: int, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    rows = await db.execute(
        select(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at.asc())
    )
    return [
        MemberOut(
            user_id=user.id,
            display_name=user.display_name,
            telegram_id=user.telegram_id,
            role=member.role,
        )
        for member, user in rows.all()
    ]


@router.post("/groups/{group_id}/members")
async def add_member(group_id: int, payload: MemberAdd, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    if not await db.get(User, payload.user_id):
        raise HTTPException(404, "user not found")
    existing = (await db.execute(select(GroupMember).where(
        GroupMember.group_id == group_id, GroupMember.user_id == payload.user_id
    ))).scalar_one_or_none()
    if existing:
        return {"ok": True, "member_id": existing.id, "already_member": True}
    member = GroupMember(group_id=group_id, user_id=payload.user_id)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return {"ok": True, "member_id": member.id, "already_member": False}


@router.post("/groups/{group_id}/expenses", response_model=ExpenseOut)
async def add_expense(group_id: int, payload: ExpenseCreate, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    try:
        return await create_expense(db, group_id, payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/groups/{group_id}/expenses", response_model=list[ExpenseHistoryItem])
async def expense_history(group_id: int, limit: int = 20, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    safe_limit = min(max(limit, 1), 100)
    rows = await db.execute(
        select(Expense, User)
        .join(User, User.id == Expense.paid_by_user_id)
        .where(Expense.group_id == group_id)
        .order_by(Expense.created_at.desc())
        .limit(safe_limit)
    )
    return [
        ExpenseHistoryItem(
            id=expense.id,
            title=expense.title,
            amount=expense.amount,
            paid_by_user_id=user.id,
            paid_by_name=user.display_name,
            category=expense.category,
            created_at=expense.created_at,
        )
        for expense, user in rows.all()
    ]


@router.get("/groups/{group_id}/balances", response_model=list[BalanceItem])
async def balances(group_id: int, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    values = await calculate_balances(db, group_id)
    return [BalanceItem(user_id=uid, balance=amount) for uid, amount in values.items()]


@router.get("/groups/{group_id}/settlement-plan", response_model=list[TransferSuggestion])
async def settlement_plan(group_id: int, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    values = await calculate_balances(db, group_id)
    return [TransferSuggestion(**item) for item in simplify_debts(values)]


@router.post("/groups/{group_id}/settlements")
async def settle(group_id: int, payload: SettlementCreate, db: AsyncSession = Depends(get_db)):
    await require_group(db, group_id)
    if payload.from_user_id == payload.to_user_id:
        raise HTTPException(400, "from and to users must differ")
    members = set((await db.execute(select(GroupMember.user_id).where(GroupMember.group_id == group_id))).scalars().all())
    if payload.from_user_id not in members or payload.to_user_id not in members:
        raise HTTPException(400, "both users must be group members")
    st = Settlement(group_id=group_id, amount=q(payload.amount), **payload.model_dump(exclude={"amount"}))
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return {"ok": True, "settlement_id": st.id}
