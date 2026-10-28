from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func, text

from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Account(Base):
    __tablename__ = "accounts"

    __table_args__ = (
        CheckConstraint("balance >= 0", name="accounts_balance_nonnegative"),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="accounts_name_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        server_default=text("0.00"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
class Transaction(Base):
    __tablename__ = "transactions"

    __table_args__ = (
        CheckConstraint(
            "type IN ('credit', 'debit')",
            name="transactions_valid_type",
        ),
        CheckConstraint(
            "amount > 0",
            name="transactions_positive_amount",
        ),
        CheckConstraint(
            "length(trim(reference_id)) > 0",
            name="transactions_reference_not_blank",
        ),
        UniqueConstraint(
            "account_id",
            "reference_id",
            name="transactions_account_reference_unique",
        ),
        Index(
            "transactions_account_history_idx",
            "account_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    type: Mapped[str] = mapped_column(
        String(6),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        server_default=text("''"),
    )

    reference_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )