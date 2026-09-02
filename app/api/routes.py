from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.entities import Group, GroupMember, Settlement, User
from app.schemas.common import (
    BalanceItem, ExpenseCreate, ExpenseOut, GroupCreate, GroupOut, MemberAdd,
    SettlementCreate, TransferSuggestion, UserCreate, UserOut,
)
from app.services.ledger import calculate_balances, create_expense, q, simplify_debts

router = APIRouter(prefix="/api/v1")


@router.post("/users", response_model=UserOut)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    if payload.telegram_id is not None:
        existing = (await db.execute(select(User).where(User.telegram_id == payload.telegram_id))).scalar_one_or_none()
        if existing:
            return existing
    user = User(**payload.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


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


@router.post("/groups/{group_id}/members")
async def add_member(group_id: int, payload: MemberAdd, db: AsyncSession = Depends(get_db)):
    if not await db.get(Group, group_id):
        raise HTTPException(404, "group not found")
    if not await db.get(User, payload.user_id):
        raise HTTPException(404, "user not found")
    existing = (await db.execute(select(GroupMember).where(
        GroupMember.group_id == group_id, GroupMember.user_id == payload.user_id
    ))).scalar_one_or_none()
    if existing:
        return {"ok": True, "member_id": existing.id}
    member = GroupMember(group_id=group_id, user_id=payload.user_id)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return {"ok": True, "member_id": member.id}


@router.post("/groups/{group_id}/expenses", response_model=ExpenseOut)
async def add_expense(group_id: int, payload: ExpenseCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await create_expense(db, group_id, payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/groups/{group_id}/balances", response_model=list[BalanceItem])
async def balances(group_id: int, db: AsyncSession = Depends(get_db)):
    values = await calculate_balances(db, group_id)
    return [BalanceItem(user_id=uid, balance=amount) for uid, amount in values.items()]


@router.get("/groups/{group_id}/settlement-plan", response_model=list[TransferSuggestion])
async def settlement_plan(group_id: int, db: AsyncSession = Depends(get_db)):
    values = await calculate_balances(db, group_id)
    return [TransferSuggestion(**item) for item in simplify_debts(values)]


@router.post("/groups/{group_id}/settlements")
async def settle(group_id: int, payload: SettlementCreate, db: AsyncSession = Depends(get_db)):
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
