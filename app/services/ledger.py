from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import Expense, ExpenseShare, GroupMember, Settlement

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _allocate_weighted(amount: Decimal, weights: dict[int, Decimal]) -> dict[int, Decimal]:
    if not weights or any(value <= 0 for value in weights.values()):
        raise ValueError("all split weights must be positive")
    total_weight = sum(weights.values(), Decimal("0"))
    raw = {uid: (amount * weight / total_weight) for uid, weight in weights.items()}
    result = {uid: q(value) for uid, value in raw.items()}
    diff = q(amount - sum(result.values(), Decimal("0")))
    if diff:
        step = CENT if diff > 0 else -CENT
        ordered = sorted(
            weights,
            key=lambda uid: (raw[uid] - result[uid], -uid),
            reverse=diff > 0,
        )
        i = 0
        while diff != Decimal("0.00"):
            uid = ordered[i % len(ordered)]
            result[uid] = q(result[uid] + step)
            diff = q(diff - step)
            i += 1
    return result


def split_equal(amount: Decimal, participant_ids: list[int]) -> dict[int, Decimal]:
    ids = list(dict.fromkeys(participant_ids))
    if not ids:
        raise ValueError("participant list cannot be empty")
    return _allocate_weighted(q(amount), {uid: Decimal("1") for uid in ids})


def calculate_split(
    amount: Decimal,
    participant_ids: list[int],
    split_mode: str = "equal",
    split_values: dict[int, Decimal] | None = None,
) -> dict[int, Decimal]:
    ids = list(dict.fromkeys(participant_ids))
    if not ids:
        raise ValueError("participant list cannot be empty")
    total = q(amount)
    if split_mode == "equal":
        return split_equal(total, ids)

    values = {int(uid): Decimal(str(value)) for uid, value in (split_values or {}).items()}
    if set(values) != set(ids):
        raise ValueError("split values must be provided for every participant")

    if split_mode == "percentage":
        if any(value < 0 for value in values.values()):
            raise ValueError("percentages cannot be negative")
        if q(sum(values.values(), Decimal("0"))) != q(HUNDRED):
            raise ValueError("percentages must total 100")
        return _allocate_weighted(total, values)

    if split_mode == "shares":
        return _allocate_weighted(total, values)

    if split_mode == "exact":
        exact = {uid: q(value) for uid, value in values.items()}
        if any(value < 0 for value in exact.values()):
            raise ValueError("exact split amounts cannot be negative")
        if q(sum(exact.values(), Decimal("0"))) != total:
            raise ValueError("exact split amounts must equal expense total")
        return exact

    raise ValueError("unsupported split mode")


async def validate_expense_members(session: AsyncSession, group_id: int, payer_id: int, participants: list[int]) -> list[int]:
    member_ids = set((await session.execute(
        select(GroupMember.user_id).where(GroupMember.group_id == group_id)
    )).scalars().all())
    participant_ids = list(dict.fromkeys(participants))
    if payer_id not in member_ids:
        raise ValueError("payer is not a member of this group")
    if any(uid not in member_ids for uid in participant_ids):
        raise ValueError("all participants must be group members")
    return participant_ids


async def replace_expense_shares(
    session: AsyncSession,
    expense_id: int,
    amount: Decimal,
    participant_ids: list[int],
    split_mode: str = "equal",
    split_values: dict[int, Decimal] | None = None,
) -> None:
    await session.execute(delete(ExpenseShare).where(ExpenseShare.expense_id == expense_id))
    shares = calculate_split(q(amount), participant_ids, split_mode, split_values)
    for user_id, share_amount in shares.items():
        session.add(ExpenseShare(expense_id=expense_id, user_id=user_id, amount=share_amount))


def serialize_split_config(split_values: dict[int, Decimal] | None) -> str | None:
    if not split_values:
        return None
    return json.dumps({str(uid): str(value) for uid, value in split_values.items()}, separators=(",", ":"))


def deserialize_split_config(value: str | None) -> dict[int, Decimal] | None:
    if not value:
        return None
    raw = json.loads(value)
    return {int(uid): Decimal(str(amount)) for uid, amount in raw.items()}


async def create_expense(session: AsyncSession, group_id: int, payload) -> Expense:
    participants = await validate_expense_members(
        session, group_id, payload.paid_by_user_id, payload.participant_user_ids
    )
    split_values = payload.split_values or None
    calculate_split(payload.amount, participants, payload.split_mode, split_values)
    expense = Expense(
        group_id=group_id,
        paid_by_user_id=payload.paid_by_user_id,
        created_by_user_id=payload.actor_user_id,
        amount=q(payload.amount),
        title=payload.title,
        split_mode=payload.split_mode,
        split_config=serialize_split_config(split_values),
        category=payload.category,
        note=payload.note,
    )
    session.add(expense)
    await session.flush()
    await replace_expense_shares(
        session, expense.id, payload.amount, participants, payload.split_mode, split_values
    )
    await session.commit()
    await session.refresh(expense)
    return expense


async def update_expense(session: AsyncSession, expense: Expense, payload) -> Expense:
    participants = await validate_expense_members(
        session, expense.group_id, payload.paid_by_user_id, payload.participant_user_ids
    )
    split_values = payload.split_values or None
    calculate_split(payload.amount, participants, payload.split_mode, split_values)
    expense.paid_by_user_id = payload.paid_by_user_id
    expense.amount = q(payload.amount)
    expense.title = payload.title
    expense.split_mode = payload.split_mode
    expense.split_config = serialize_split_config(split_values)
    expense.category = payload.category
    expense.note = payload.note
    await replace_expense_shares(
        session, expense.id, payload.amount, participants, payload.split_mode, split_values
    )
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
        select(Settlement).where(
            Settlement.group_id == group_id,
            Settlement.status == "confirmed",
        )
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
