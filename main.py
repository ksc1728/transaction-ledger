from collections.abc import Generator
from sqlalchemy.orm import Session
from uuid import UUID
from database import SessionLocal
from models import Account
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import func, select

from models import Account, Transaction
from schemas import ( AccountCreate, AccountResponse, BalanceResponse, TransactionCreate, TransactionResponse, PaginationResponse,
TransactionHistoryResponse,TransferCreate,TransferResponse)
from decimal import Decimal
from typing import Literal
from error_handlers import register_error_handlers


app = FastAPI(title="Transaction Ledger API")
register_error_handlers(app)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db


@app.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    data: AccountCreate,
    db: Session = Depends(get_db),
):
    with db.begin():
        account = Account(name=data.name)
        db.add(account)

        
        db.flush()

        
        db.refresh(account)

        
        response = AccountResponse.model_validate(account)

    return response

@app.get(
    "/accounts/{account_id}/balance",
    response_model=BalanceResponse,
)
def get_account_balance(
    account_id: UUID,
    db: Session = Depends(get_db),
):
    account = db.get(Account, account_id)

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "account_not_found",
                "message": "Account not found.",
            },
        )

    return BalanceResponse(
        account_id=account.id,
        balance=account.balance,
    )
    
@app.post(
    "/accounts/{account_id}/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_transaction(
    account_id: UUID,
    data: TransactionCreate,
    db: Session = Depends(get_db),
):
    with db.begin():
        # Lock this account until the database transaction finishes.
        account = db.execute(
            select(Account)
            .where(Account.id == account_id)
            .with_for_update()
        ).scalar_one_or_none()

        if account is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "account_not_found",
                    "message": "Account not found.",
                },
            )

        
        existing_id = db.execute(
            select(Transaction.id).where(
                Transaction.account_id == account_id,
                Transaction.reference_id == data.reference_id,
            )
        ).scalar_one_or_none()

        if existing_id is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_transaction",
                    "message": (
                        "A transaction with this reference_id "
                        "already exists for this account."
                    ),
                },
            )

        if data.type == "debit":
            if account.balance < data.amount:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "insufficient_balance",
                        "message": "The account has insufficient balance.",
                    },
                )

            new_balance = account.balance - data.amount
        else:
            new_balance = account.balance + data.amount

        
        if new_balance > Decimal("9999999999999999.99"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "balance_limit_exceeded",
                    "message": "The resulting balance exceeds the supported limit.",
                },
            )

        transaction = Transaction(
            account_id=account_id,
            type=data.type,
            amount=data.amount,
            description=data.description,
            reference_id=data.reference_id,
        )

        db.add(transaction)
        account.balance = new_balance

        
        db.flush()
        db.refresh(transaction)

        response = TransactionResponse.model_validate(transaction)

    return response

@app.get(
    "/accounts/{account_id}/transactions",
    response_model=TransactionHistoryResponse,
)
def get_transaction_history(
    account_id: UUID,
    transaction_type: Literal["credit", "debit"] | None = Query(
        default=None,
        alias="type",
    ),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Use one consistent snapshot for the account, count, and page.
    with db.begin():
        db.connection(
            execution_options={"isolation_level": "REPEATABLE READ"}
        )

        account = db.get(Account, account_id)

        if account is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "account_not_found",
                    "message": "Account not found.",
                },
            )

        filters = [Transaction.account_id == account_id]

        if transaction_type is not None:
            filters.append(Transaction.type == transaction_type)

        total_records = db.execute(
            select(func.count())
            .select_from(Transaction)
            .where(*filters)
        ).scalar_one()

        offset = (page - 1) * limit

        transactions = db.execute(
            select(Transaction)
            .where(*filters)
            .order_by(
                Transaction.created_at.desc(),
                Transaction.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        ).scalars().all()

        response = TransactionHistoryResponse(
            items=[
                TransactionResponse.model_validate(transaction)
                for transaction in transactions
            ],
            pagination=PaginationResponse(
                page=page,
                limit=limit,
                total_records=total_records,
                total_pages=(total_records + limit - 1) // limit,
            ),
        )

    return response

@app.post(
    "/transfers",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
)
def transfer_money(
    data: TransferCreate,
    db: Session = Depends(get_db),
):
    if data.source_account_id == data.destination_account_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_transfer",
                "message": "Source and destination accounts must be different.",
            },
        )

    with db.begin():
        # Lock accounts in a consistent order to avoid opposite-order locks.
        account_ids = sorted(
            [data.source_account_id, data.destination_account_id]
        )

        accounts = {}

        for account_id in account_ids:
            account = db.execute(
                select(Account)
                .where(Account.id == account_id)
                .with_for_update()
            ).scalar_one_or_none()

            if account is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "account_not_found",
                        "message": f"Account {account_id} not found.",
                    },
                )

            accounts[account_id] = account

        source = accounts[data.source_account_id]
        destination = accounts[data.destination_account_id]

        existing_id = db.execute(
            select(Transaction.id)
            .where(
                Transaction.account_id.in_(account_ids),
                Transaction.reference_id == data.reference_id,
            )
            .limit(1)
        ).scalar_one_or_none()

        if existing_id is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_transaction",
                    "message": (
                        "This reference_id already exists "
                        "on a source or destination account."
                    ),
                },
            )

        if source.balance < data.amount:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "insufficient_balance",
                    "message": "The source account has insufficient balance.",
                },
            )

        destination_balance = destination.balance + data.amount

        if destination_balance > Decimal("9999999999999999.99"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "balance_limit_exceeded",
                    "message": (
                        "The destination balance exceeds the supported limit."
                    ),
                },
            )

        debit = Transaction(
            account_id=source.id,
            type="debit",
            amount=data.amount,
            description=data.description,
            reference_id=data.reference_id,
        )

        credit = Transaction(
            account_id=destination.id,
            type="credit",
            amount=data.amount,
            description=data.description,
            reference_id=data.reference_id,
        )

        source.balance -= data.amount
        destination.balance = destination_balance

        db.add_all([debit, credit])
        db.flush()

        db.refresh(debit)
        db.refresh(credit)

        response = TransferResponse(
            reference_id=data.reference_id,
            debit=TransactionResponse.model_validate(debit),
            credit=TransactionResponse.model_validate(credit),
        )

    return response

##insufficient funds
def test_transfer_insufficient_funds_changes_nothing(client):
    source_id = create_account(client)
    destination_id = create_account(client)

    assert add_transaction(
        client, source_id, "credit", "20.00", "deposit-1"
    ).status_code == 201

    response = client.post(
        "/transfers",
        json={
            "source_account_id": source_id,
            "destination_account_id": destination_id,
            "amount": "30.00",
            "reference_id": "transfer-1",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_balance"

    assert balance(client, source_id) == Decimal("20.00")
    assert balance(client, destination_id) == Decimal("0.00")

    assert history(client, source_id)["pagination"]["total_records"] == 1
    assert history(client, destination_id)["pagination"]["total_records"] == 0

##desination reference already exists
def test_transfer_destination_reference_conflict_changes_nothing(client):
    source_id = create_account(client)
    destination_id = create_account(client)

    assert add_transaction(
        client, source_id, "credit", "100.00", "source-deposit"
    ).status_code == 201

    assert add_transaction(
        client, destination_id, "credit", "10.00", "transfer-1"
    ).status_code == 201

    response = client.post(
        "/transfers",
        json={
            "source_account_id": source_id,
            "destination_account_id": destination_id,
            "amount": "30.00",
            "reference_id": "transfer-1",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_transaction"

    assert balance(client, source_id) == Decimal("100.00")
    assert balance(client, destination_id) == Decimal("10.00")

    assert history(client, source_id)["pagination"]["total_records"] == 1
    assert history(client, destination_id)["pagination"]["total_records"] == 1
    
##failure after changes are flushed

def test_transfer_failure_before_commit_rolls_back_everything(client):
    source_id = create_account(client)
    destination_id = create_account(client)

    assert add_transaction(
        client, source_id, "credit", "100.00", "deposit-1"
    ).status_code == 201

    def fail_before_commit(session):
        raise RuntimeError("Simulated transfer failure")

    event.listen(Session, "before_commit", fail_before_commit)

    try:
        with pytest.raises(
            RuntimeError,
            match="Simulated transfer failure",
        ):
            client.post(
                "/transfers",
                json={
                    "source_account_id": source_id,
                    "destination_account_id": destination_id,
                    "amount": "30.00",
                    "reference_id": "transfer-1",
                },
            )
    finally:
        event.remove(Session, "before_commit", fail_before_commit)

    assert balance(client, source_id) == Decimal("100.00")
    assert balance(client, destination_id) == Decimal("0.00")

    assert history(client, source_id)["pagination"]["total_records"] == 1
    assert history(client, destination_id)["pagination"]["total_records"] == 0
    
##missing account and self transfer check

def test_transfer_missing_destination_changes_nothing(client):
    source_id = create_account(client)

    assert add_transaction(
        client, source_id, "credit", "100.00", "deposit-1"
    ).status_code == 201

    response = client.post(
        "/transfers",
        json={
            "source_account_id": source_id,
            "destination_account_id": (
                "00000000-0000-0000-0000-000000000000"
            ),
            "amount": "30.00",
            "reference_id": "transfer-1",
        },
    )

    assert response.status_code == 404
    assert balance(client, source_id) == Decimal("100.00")
    assert history(client, source_id)["pagination"]["total_records"] == 1


def test_self_transfer_is_rejected(client):
    account_id = create_account(client)

    response = client.post(
        "/transfers",
        json={
            "source_account_id": account_id,
            "destination_account_id": account_id,
            "amount": "10.00",
            "reference_id": "transfer-1",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_transfer"
    assert balance(client, account_id) == Decimal("0.00")
    assert history(client, account_id)["pagination"]["total_records"] == 0
    
