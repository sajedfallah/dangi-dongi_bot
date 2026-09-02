from decimal import Decimal
from pydantic import BaseModel, Field


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


class ExpenseCreate(BaseModel):
    paid_by_user_id: int
    amount: Decimal = Field(gt=0)
    title: str = Field(min_length=1, max_length=160)
    participant_user_ids: list[int] = Field(min_length=1)
    category: str | None = None
    note: str | None = None


class ExpenseOut(BaseModel):
    id: int
    group_id: int
    paid_by_user_id: int
    amount: Decimal
    title: str
    category: str | None = None
    model_config = {"from_attributes": True}


class SettlementCreate(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: Decimal = Field(gt=0)


class TransferSuggestion(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: Decimal


class BalanceItem(BaseModel):
    user_id: int
    balance: Decimal
