from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.security import make_join_payload
from app.db.session import get_db
from app.models.entities import AuditLog, DebtReminderState, Expense, ExpenseShare, Group, GroupMember, Settlement, User
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


class HistoricalShareApply(BaseModel):
    actor_user_id: int
    member_user_id: int
    mode: str = Field(pattern="^(equal|percentage|exact)$")
    value: Decimal | None = None


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


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _distribute(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    if not weights or sum(weights) <= 0:
        raise HTTPException(400, "cannot redistribute existing shares")
    total = _money(total)
    weight_sum = sum(weights)
    amounts = [(total * w / weight_sum).quantize(Decimal("0.01"), rounding=ROUND_DOWN) for w in weights]
    remainder = total - sum(amounts)
    amounts[0] += remainder
    return amounts


@router.get("/groups/{group_id}/invite")
async def group_invite(group_id: int, actor_user_id: int, db: AsyncSession = Depends(get_db)):
    await _member(db, group_id, actor_user_id)
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "group not found")
    return {
        "group_id": group.id,
        "group_name": group.name,
        "start_parameter": make_join_payload(group.id),
    }


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
        select(func.coalesce(Expense.category, "other"), func.sum(Expense.amount), func.count(Expense.id))
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


@router.get("/groups/{group_id}/historical-expenses/{member_user_id}")
async def historical_expenses_for_member(group_id: int, member_user_id: int, actor_user_id: int, db: AsyncSession = Depends(get_db)):
    await _manager(db, group_id, actor_user_id)
    await _member(db, group_id, member_user_id)
    rows = (await db.execute(
        select(Expense)
        .where(Expense.group_id == group_id)
        .options(selectinload(Expense.shares))
        .order_by(Expense.created_at.desc())
    )).scalars().all()
    return [
        {
            "id": exp.id,
            "title": exp.title,
            "amount": str(exp.amount),
            "category": exp.category,
            "created_at": exp.created_at,
            "already_participant": any(s.user_id == member_user_id for s in exp.shares),
            "participant_count": len(exp.shares),
        }
        for exp in rows
    ]


@router.post("/groups/{group_id}/expenses/{expense_id}/historical-member")
async def apply_historical_member(group_id: int, expense_id: int, payload: HistoricalShareApply, db: AsyncSession = Depends(get_db)):
    await _manager(db, group_id, payload.actor_user_id)
    await _member(db, group_id, payload.member_user_id)
    expense = (await db.execute(
        select(Expense)
        .where(Expense.id == expense_id, Expense.group_id == group_id)
        .options(selectinload(Expense.shares))
    )).scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "expense not found")
    if any(s.user_id == payload.member_user_id for s in expense.shares):
        raise HTTPException(409, "member already participates in this expense")
    if not expense.shares:
        raise HTTPException(409, "expense has no existing shares")

    total = _money(Decimal(expense.amount))
    old_shares = list(expense.shares)
    old_weights = [Decimal(s.amount) for s in old_shares]

    if payload.mode == "equal":
        all_weights = [Decimal("1")] * (len(old_shares) + 1)
        amounts = _distribute(total, all_weights)
        old_amounts, new_amount = amounts[:-1], amounts[-1]
    else:
        if payload.value is None:
            raise HTTPException(400, "value is required for percentage/exact")
        if payload.mode == "percentage":
            if payload.value <= 0 or payload.value >= 100:
                raise HTTPException(400, "percentage must be between 0 and 100")
            new_amount = _money(total * Decimal(payload.value) / Decimal("100"))
        else:
            new_amount = _money(Decimal(payload.value))
            if new_amount <= 0 or new_amount >= total:
                raise HTTPException(400, "exact amount must be greater than zero and less than total expense")
        old_amounts = _distribute(total - new_amount, old_weights)

    for share, amount in zip(old_shares, old_amounts):
        share.amount = amount
    db.add(ExpenseShare(expense_id=expense.id, user_id=payload.member_user_id, amount=new_amount))
    db.add(AuditLog(
        group_id=group_id,
        actor_user_id=payload.actor_user_id,
        action="expense.member_added_retroactively",
        entity_type="expense",
        entity_id=expense.id,
        details=f'{{"member_user_id": {payload.member_user_id}, "mode": "{payload.mode}", "new_share": "{new_amount}"}}',
    ))
    await db.commit()
    return {
        "ok": True,
        "expense_id": expense.id,
        "member_user_id": payload.member_user_id,
        "mode": payload.mode,
        "new_share": str(new_amount),
        "total": str(total),
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
    return {"ok": True, "settlement_id": st.id, "receipt_file_id": st.receipt_file_id, "receipt_kind": st.receipt_kind}


@router.get("/groups/{group_id}/settlements/{settlement_id}/receipt")
async def settlement_receipt(group_id: int, settlement_id: int, actor_user_id: int, db: AsyncSession = Depends(get_db)):
    await _member(db, group_id, actor_user_id)
    st = await db.get(Settlement, settlement_id)
    if not st or st.group_id != group_id:
        raise HTTPException(404, "settlement not found")
    return {"settlement_id": st.id, "receipt_file_id": st.receipt_file_id, "receipt_kind": st.receipt_kind}


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
