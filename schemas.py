from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class AccountCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1, max_length=100)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    balance: Decimal
    created_at: datetime

class BalanceResponse(BaseModel):
    account_id: UUID
    balance: Decimal
    
class TransactionCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    type: Literal["credit", "debit"]

    amount: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=2,
        allow_inf_nan=False,
    )

    description: str = Field(default="", max_length=500)

    reference_id: str = Field(min_length=1, max_length=100)


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    type: Literal["credit", "debit"]
    amount: Decimal
    description: str
    reference_id: str
    created_at: datetime

class PaginationResponse(BaseModel):
    page: int
    limit: int
    total_records: int
    total_pages: int


class TransactionHistoryResponse(BaseModel):
    items: list[TransactionResponse]
    pagination: PaginationResponse
    
class TransferCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    source_account_id: UUID
    destination_account_id: UUID

    amount: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=2,
        allow_inf_nan=False,
    )

    reference_id: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class TransferResponse(BaseModel):
    reference_id: str
    debit: TransactionResponse
    credit: TransactionResponse