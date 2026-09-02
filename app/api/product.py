from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import DebtReminderState, Expense, Group, GroupMember, Settlement, User
from app.services.ledger import calculate_balances, simplify_debts

router = APIRouter(prefix="/api/v1/product", tags=["product"])


class PaymentProfileUpdate(BaseModel):
    bank_name: str | None = Field(default=None, max_length=80)
    account_holder: str | None = Field(default=None, max_length=120)
    card_number: str | None = Field(default=None, max_length=32)
    iban: str | None = Field(default=None, max_length=40)
    account_number: str | None = Field(default=None, max_length=40)
    reminder_enabled: bool = True


class ReceiptAttach(BaseModel):
    actor_user_id: int
    receipt_file_id: str = Field(min_length=1, max_length=255)
    receipt_kind: str = Field(pattern="^(photo|document)$")


class ReminderSent(BaseModel):
    group_id: int
    debtor_user_id: int
    creditor_user_id: int
    amount: Decimal = Field(gt=0)


async def _member(db: AsyncSession, group_id: int, user_id: int) -> GroupMember:
    row = (await db.execute(select(GroupMember).where(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
    ))).scalar_one_or_none()
    if not row:
        raise HTTPException(403, "group membership required")
    return row


@router.get("/users/{user_id}/payment-profile")
async def get_payment_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return {
        "user_id": user.id,
        "display_name": user.display_name,
        "bank_name": user.bank_name,
        "account_holder": user.account_holder,
        "card_number": user.card_number,
        "iban": user.iban,
        "account_number": user.account_number,
        "reminder_enabled": user.reminder_enabled,
    }


@router.put("/users/{user_id}/payment-profile")
async def update_payment_profile(user_id: int, payload: PaymentProfileUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    for key, value in payload.model_dump().items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(user, key, value)
    await db.commit()
    return await get_payment_profile(user_id, db)


@router.get("/groups/{group_id}/reports/debts")
async def debt_report(group_id: int, actor_user_id: int, db: AsyncSession = Depends(get_db)):
    await _member(db, group_id, actor_user_id)
    members = (await db.execute(
        select(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
    )).all()
    names = {user.id: user.display_name for _, user in members}
    balances = await calculate_balances(db, group_id)
    transfers = simplify_debts(balances)
    return {
        "balances": [
            {
                "user_id": uid,
                "display_name": names.get(uid, "کاربر"),
                "balance": str(amount),
                "status": "creditor" if amount > 0 else "debtor" if amount < 0 else "settled",
            }
            for uid, amount in balances.items()
        ],
        "transfers": [
            {
                **item,
                "from_name": names.get(item["from_user_id"], "کاربر"),
                "to_name": names.get(item["to_user_id"], "کاربر"),
                "amount": str(item["amount"]),
            }
            for item in transfers
        ],
    }


@router.get("/groups/{group_id}/reports/expenses")
async def expense_report(group_id: int, actor_user_id: int, db: AsyncSession = Depends(get_db)):
    await _member(db, group_id, actor_user_id)
    total = (await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.group_id == group_id)
    )).scalar_one()
    count = (await db.execute(
        select(func.count(Expense.id)).where(Expense.group_id == group_id)
    )).scalar_one()
    rows = (await db.execute(
        select(
            func.coalesce(Expense.category, "other"),
            func.sum(Expense.amount),
            func.count(Expense.id),
        )
        .where(Expense.group_id == group_id)
        .group_by(func.coalesce(Expense.category, "other"))
        .order_by(func.sum(Expense.amount).desc())
    )).all()
    return {
        "total_amount": str(total),
        "expense_count": int(count),
        "categories": [
            {"category": category, "amount": str(amount), "count": int(items)}
            for category, amount, items in rows
        ],
    }


@router.post("/groups/{group_id}/settlements/{settlement_id}/receipt")
async def attach_receipt(group_id: int, settlement_id: int, payload: ReceiptAttach, db: AsyncSession = Depends(get_db)):
    await _member(db, group_id, payload.actor_user_id)
    st = await db.get(Settlement, settlement_id)
    if not st or st.group_id != group_id:
        raise HTTPException(404, "settlement not found")
    if st.from_user_id != payload.actor_user_id:
        raise HTTPException(403, "only debtor can attach receipt")
    if st.status != "pending":
        raise HTTPException(409, "receipt can only be attached to pending settlement")
    st.receipt_file_id = payload.receipt_file_id
    st.receipt_kind = payload.receipt_kind
    await db.commit()
    return {
        "ok": True,
        "settlement_id": st.id,
        "receipt_file_id": st.receipt_file_id,
        "receipt_kind": st.receipt_kind,
    }


@router.get("/groups/{group_id}/settlements/{settlement_id}/receipt")
async def settlement_receipt(group_id: int, settlement_id: int, actor_user_id: int, db: AsyncSession = Depends(get_db)):
    await _member(db, group_id, actor_user_id)
    st = await db.get(Settlement, settlement_id)
    if not st or st.group_id != group_id:
        raise HTTPException(404, "settlement not found")
    return {
        "settlement_id": st.id,
        "receipt_file_id": st.receipt_file_id,
        "receipt_kind": st.receipt_kind,
    }


@router.get("/reminders/due")
async def due_reminders(force: bool = False, db: AsyncSession = Depends(get_db)):
    groups = (await db.execute(select(Group).where(Group.is_archived.is_(False)))).scalars().all()
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=24)
    result = []
    for group in groups:
        transfers = simplify_debts(await calculate_balances(db, group.id))
        if not transfers:
            continue
        user_ids = {x["from_user_id"] for x in transfers} | {x["to_user_id"] for x in transfers}
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        by_id = {u.id: u for u in users}
        for transfer in transfers:
            debtor = by_id.get(transfer["from_user_id"])
            creditor = by_id.get(transfer["to_user_id"])
            if not debtor or not creditor or not debtor.telegram_id or not debtor.reminder_enabled:
                continue
            state = (await db.execute(select(DebtReminderState).where(
                DebtReminderState.group_id == group.id,
                DebtReminderState.debtor_user_id == debtor.id,
                DebtReminderState.creditor_user_id == creditor.id,
            ))).scalar_one_or_none()
            if not force and state and state.last_sent_at and state.last_sent_at > cutoff:
                continue
            result.append({
                "group_id": group.id,
                "group_name": group.name,
                "debtor_user_id": debtor.id,
                "debtor_name": debtor.display_name,
                "debtor_telegram_id": debtor.telegram_id,
                "creditor_user_id": creditor.id,
                "creditor_name": creditor.display_name,
                "amount": str(transfer["amount"]),
                "payment": {
                    "bank_name": creditor.bank_name,
                    "account_holder": creditor.account_holder,
                    "card_number": creditor.card_number,
                    "iban": creditor.iban,
                    "account_number": creditor.account_number,
                },
            })
    return result


@router.post("/reminders/sent")
async def mark_reminder_sent(payload: ReminderSent, db: AsyncSession = Depends(get_db)):
    state = (await db.execute(select(DebtReminderState).where(
        DebtReminderState.group_id == payload.group_id,
        DebtReminderState.debtor_user_id == payload.debtor_user_id,
        DebtReminderState.creditor_user_id == payload.creditor_user_id,
    ))).scalar_one_or_none()
    if not state:
        state = DebtReminderState(
            group_id=payload.group_id,
            debtor_user_id=payload.debtor_user_id,
            creditor_user_id=payload.creditor_user_id,
            last_amount=payload.amount,
        )
        db.add(state)
    state.last_amount = payload.amount
    state.last_sent_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "sent_at": state.last_sent_at}
