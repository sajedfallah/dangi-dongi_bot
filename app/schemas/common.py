from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

SplitMode = Literal["equal", "percentage", "shares", "exact"]


class UserCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    telegram_id: int | None = None


class UserOut(UserCreate):
    id: int
    model_config = {"from_attributes": True}


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner_user_id: int
    currency: str = "IRR"


class GroupOut(BaseModel):
    id: int
    name: str
    currency: str
    owner_user_id: int
    model_config = {"from_attributes": True}


class MemberAdd(BaseModel):
    user_id: int


class MemberRoleUpdate(BaseModel):
    actor_user_id: int
    role: str = Field(pattern="^(admin|member)$")


class MemberOut(BaseModel):
    user_id: int
    display_name: str
    telegram_id: int | None = None
    role: str


class ExpenseCreate(BaseModel):
    actor_user_id: int
    paid_by_user_id: int
    amount: Decimal = Field(gt=0)
    title: str = Field(min_length=1, max_length=160)
    participant_user_ids: list[int] = Field(min_length=1)
    split_mode: SplitMode = "equal"
    split_values: dict[int, Decimal] | None = None
    category: str | None = None
    note: str | None = None


class ExpenseUpdate(BaseModel):
    actor_user_id: int
    paid_by_user_id: int
    amount: Decimal = Field(gt=0)
    title: str = Field(min_length=1, max_length=160)
    participant_user_ids: list[int] = Field(min_length=1)
    split_mode: SplitMode = "equal"
    split_values: dict[int, Decimal] | None = None
    category: str | None = None
    note: str | None = None


class ExpenseDelete(BaseModel):
    actor_user_id: int


class ExpenseShareOut(BaseModel):
    user_id: int
    amount: Decimal


class ExpenseOut(BaseModel):
    id: int
    group_id: int
    paid_by_user_id: int
    created_by_user_id: int | None = None
    amount: Decimal
    title: str
    split_mode: str = "equal"
    category: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ExpenseDetailOut(ExpenseOut):
    participant_user_ids: list[int]
    split_values: dict[int, Decimal] | None = None
    note: str | None = None
    shares: list[ExpenseShareOut]


class ExpenseHistoryItem(BaseModel):
    id: int
    title: str
    amount: Decimal
    paid_by_user_id: int
    paid_by_name: str
    created_by_user_id: int | None = None
    split_mode: str = "equal"
    category: str | None = None
    created_at: datetime


class SettlementCreate(BaseModel):
    actor_user_id: int
    from_user_id: int
    to_user_id: int
    amount: Decimal = Field(gt=0)


class SettlementAction(BaseModel):
    actor_user_id: int


class SettlementOut(BaseModel):
    id: int
    group_id: int
    from_user_id: int
    to_user_id: int
    amount: Decimal
    status: str
    created_at: datetime
    responded_at: datetime | None = None
    model_config = {"from_attributes": True}


class TransferSuggestion(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: Decimal


class BalanceItem(BaseModel):
    user_id: int
    balance: Decimal


class AuditLogOut(BaseModel):
    id: int
    actor_user_id: int
    action: str
    entity_type: str
    entity_id: int | None = None
    details: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}
