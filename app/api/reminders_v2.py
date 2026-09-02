from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import DebtReminderState, Group, User
from app.services.ledger import calculate_balances, simplify_debts

router = APIRouter(prefix="/api/v1/reminders-v2", tags=["reminders-v2"])

FIRST_REMINDER_DELAY = timedelta(hours=24)
REPEAT_REMINDER_DELAY = timedelta(days=3)


class ReminderSent(BaseModel):
    group_id: int
    debtor_user_id: int
    creditor_user_id: int
    amount: Decimal = Field(gt=0)


@router.get("/due")
async def due_reminders(db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    first_cutoff = now - FIRST_REMINDER_DELAY
    repeat_cutoff = now - REPEAT_REMINDER_DELAY
    groups = (await db.execute(select(Group).where(Group.is_archived.is_(False)))).scalars().all()

    result: list[dict] = []
    active_pairs: set[tuple[int, int, int]] = set()

    for group in groups:
        transfers = simplify_debts(await calculate_balances(db, group.id))
        if not transfers:
            continue

        user_ids = {x["from_user_id"] for x in transfers} | {x["to_user_id"] for x in transfers}
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        by_id = {user.id: user for user in users}

        for transfer in transfers:
            debtor_id = int(transfer["from_user_id"])
            creditor_id = int(transfer["to_user_id"])
            pair = (group.id, debtor_id, creditor_id)
            active_pairs.add(pair)

            debtor = by_id.get(debtor_id)
            creditor = by_id.get(creditor_id)
            if not debtor or not creditor:
                continue

            state = (await db.execute(select(DebtReminderState).where(
                DebtReminderState.group_id == group.id,
                DebtReminderState.debtor_user_id == debtor_id,
                DebtReminderState.creditor_user_id == creditor_id,
            ))).scalar_one_or_none()

            amount = Decimal(str(transfer["amount"]))
            if state is None:
                state = DebtReminderState(
                    group_id=group.id,
                    debtor_user_id=debtor_id,
                    creditor_user_id=creditor_id,
                    last_amount=amount,
                    first_seen_at=now,
                    last_sent_at=None,
                )
                db.add(state)
                continue

            state.last_amount = amount

            if not debtor.telegram_id or not debtor.reminder_enabled:
                continue

            if state.last_sent_at is None:
                if state.first_seen_at > first_cutoff:
                    continue
            elif state.last_sent_at > repeat_cutoff:
                continue

            result.append({
                "group_id": group.id,
                "group_name": group.name,
                "debtor_user_id": debtor.id,
                "debtor_name": debtor.display_name,
                "debtor_telegram_id": debtor.telegram_id,
                "creditor_user_id": creditor.id,
                "creditor_name": creditor.display_name,
                "amount": str(amount),
                "payment": {
                    "bank_name": creditor.bank_name,
                    "account_holder": creditor.account_holder,
                    "card_number": creditor.card_number,
                    "iban": creditor.iban,
                    "account_number": creditor.account_number,
                },
            })

    existing_states = (await db.execute(select(DebtReminderState))).scalars().all()
    for state in existing_states:
        pair = (state.group_id, state.debtor_user_id, state.creditor_user_id)
        if pair not in active_pairs:
            await db.delete(state)

    await db.commit()
    return result


@router.post("/sent")
async def mark_reminder_sent(payload: ReminderSent, db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    state = (await db.execute(select(DebtReminderState).where(
        DebtReminderState.group_id == payload.group_id,
        DebtReminderState.debtor_user_id == payload.debtor_user_id,
        DebtReminderState.creditor_user_id == payload.creditor_user_id,
    ))).scalar_one_or_none()

    if state is None:
        state = DebtReminderState(
            group_id=payload.group_id,
            debtor_user_id=payload.debtor_user_id,
            creditor_user_id=payload.creditor_user_id,
            last_amount=payload.amount,
            first_seen_at=now,
            last_sent_at=now,
        )
        db.add(state)
    else:
        state.last_amount = payload.amount
        state.last_sent_at = now

    await db.commit()
    return {"ok": True, "sent_at": state.last_sent_at}
