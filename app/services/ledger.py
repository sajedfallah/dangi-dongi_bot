from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.entities import Expense, ExpenseShare, GroupMember, Settlement

CENT = Decimal("0.01")


def q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def split_equal(amount: Decimal, participant_ids: list[int]) -> dict[int, Decimal]:
    if not participant_ids:
        raise ValueError("participant list cannot be empty")
    ids = list(dict.fromkeys(participant_ids))
    base = q(amount / Decimal(len(ids)))
    result = {uid: base for uid in ids}
    diff = q(amount - sum(result.values(), Decimal("0")))
    step = Decimal("0.01") if diff > 0 else Decimal("-0.01")
    i = 0
    while diff != Decimal("0.00"):
        uid = ids[i % len(ids)]
        result[uid] = q(result[uid] + step)
        diff = q(diff - step)
        i += 1
    return result


async def create_expense(session: AsyncSession, group_id: int, payload) -> Expense:
    member_ids = set((await session.execute(
        select(GroupMember.user_id).where(GroupMember.group_id == group_id)
    )).scalars().all())
    participants = list(dict.fromkeys(payload.participant_user_ids))
    if payload.paid_by_user_id not in member_ids:
        raise ValueError("payer is not a member of this group")
    if any(uid not in member_ids for uid in participants):
        raise ValueError("all participants must be group members")

    expense = Expense(
        group_id=group_id,
        paid_by_user_id=payload.paid_by_user_id,
        amount=q(payload.amount),
        title=payload.title,
        category=payload.category,
        note=payload.note,
    )
    session.add(expense)
    await session.flush()

    shares = split_equal(q(payload.amount), participants)
    for user_id, share_amount in shares.items():
        session.add(ExpenseShare(expense_id=expense.id, user_id=user_id, amount=share_amount))
    await session.commit()
    await session.refresh(expense)
    return expense


async def calculate_balances(session: AsyncSession, group_id: int) -> dict[int, Decimal]:
    member_ids = (await session.execute(
        select(GroupMember.user_id).where(GroupMember.group_id == group_id)
    )).scalars().all()
    balances = {uid: Decimal("0.00") for uid in member_ids}

    expenses = (await session.execute(
        select(Expense).where(Expense.group_id == group_id).options(selectinload(Expense.shares))
    )).scalars().all()
    for expense in expenses:
        balances[expense.paid_by_user_id] = q(balances.get(expense.paid_by_user_id, Decimal("0")) + expense.amount)
        for share in expense.shares:
            balances[share.user_id] = q(balances.get(share.user_id, Decimal("0")) - share.amount)

    settlements = (await session.execute(
        select(Settlement).where(Settlement.group_id == group_id)
    )).scalars().all()
    for st in settlements:
        balances[st.from_user_id] = q(balances.get(st.from_user_id, Decimal("0")) + st.amount)
        balances[st.to_user_id] = q(balances.get(st.to_user_id, Decimal("0")) - st.amount)

    return {uid: q(v) for uid, v in balances.items()}


def simplify_debts(balances: dict[int, Decimal]) -> list[dict]:
    creditors = [[uid, q(amount)] for uid, amount in balances.items() if amount > 0]
    debtors = [[uid, q(-amount)] for uid, amount in balances.items() if amount < 0]
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    result: list[dict] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor_id, debt = debtors[i]
        creditor_id, credit = creditors[j]
        amount = q(min(debt, credit))
        if amount > 0:
            result.append({"from_user_id": debtor_id, "to_user_id": creditor_id, "amount": amount})
        debtors[i][1] = q(debt - amount)
        creditors[j][1] = q(credit - amount)
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return result
