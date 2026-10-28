from decimal import Decimal

import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import event
from sqlalchemy.orm import Session


def create_account(client):
    response = client.post("/accounts", json={"name": "Test User"})
    assert response.status_code == 201
    return response.json()["id"]


def add_transaction(client, account_id, transaction_type, amount, reference):
    return client.post(
        f"/accounts/{account_id}/transactions",
        json={
            "type": transaction_type,
            "amount": amount,
            "reference_id": reference,
            "description": "Test transaction",
        },
    )


def balance(client, account_id):
    response = client.get(f"/accounts/{account_id}/balance")
    assert response.status_code == 200
    return Decimal(response.json()["balance"])


def history(client, account_id, **params):
    response = client.get(
        f"/accounts/{account_id}/transactions",
        params=params,
    )
    assert response.status_code == 200
    return response.json()


def test_account_starts_at_zero(client):
    account_id = create_account(client)

    assert balance(client, account_id) == Decimal("0.00")


def test_credit_and_debit(client):
    account_id = create_account(client)

    credit = add_transaction(
        client, account_id, "credit", "100.00", "deposit-1"
    )
    debit = add_transaction(
        client, account_id, "debit", "30.00", "payment-1"
    )

    assert credit.status_code == 201
    assert debit.status_code == 201
    assert balance(client, account_id) == Decimal("70.00")
    assert history(client, account_id)["pagination"]["total_records"] == 2


def test_duplicate_does_not_change_balance_or_history(client):
    account_id = create_account(client)

    first = add_transaction(
        client, account_id, "credit", "100.00", "deposit-1"
    )
    duplicate = add_transaction(
        client, account_id, "credit", "100.00", "deposit-1"
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_transaction"
    assert balance(client, account_id) == Decimal("100.00")
    assert history(client, account_id)["pagination"]["total_records"] == 1


def test_insufficient_funds_does_not_create_transaction(client):
    account_id = create_account(client)

    add_transaction(client, account_id, "credit", "50.00", "deposit-1")

    rejected = add_transaction(
        client, account_id, "debit", "60.00", "payment-1"
    )

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "insufficient_balance"
    assert balance(client, account_id) == Decimal("50.00")
    assert history(client, account_id)["pagination"]["total_records"] == 1


def test_same_reference_allowed_for_different_accounts(client):
    first_id = create_account(client)
    second_id = create_account(client)

    first = add_transaction(
        client, first_id, "credit", "10.00", "shared-reference"
    )
    second = add_transaction(
        client, second_id, "credit", "20.00", "shared-reference"
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert balance(client, first_id) == Decimal("10.00")
    assert balance(client, second_id) == Decimal("20.00")


def test_history_filter_and_pagination(client):
    account_id = create_account(client)

    add_transaction(client, account_id, "credit", "100.00", "deposit-1")
    add_transaction(client, account_id, "debit", "10.00", "payment-1")
    add_transaction(client, account_id, "credit", "20.00", "deposit-2")

    result = history(
        client, account_id, type="credit", page=1, limit=1
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["reference_id"] == "deposit-2"
    assert result["pagination"] == {
        "page": 1,
        "limit": 1,
        "total_records": 2,
        "total_pages": 2,
    }

    second_page = history(
        client, account_id, type="credit", page=2, limit=1
    )

    assert second_page["items"][0]["reference_id"] == "deposit-1"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": "   "},
        {"name": "Alice", "balance": 100},
    ],
)
def test_invalid_account_data(client, body):
    response = client.post("/accounts", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    
def test_failure_before_commit_rolls_back_both_changes(client):
    account_id = create_account(client)

    deposit = add_transaction(
        client, account_id, "credit", "100.00", "deposit-1"
    )
    assert deposit.status_code == 201

    def fail_before_commit(session):
        raise RuntimeError("Simulated failure before commit")

    # Temporarily inject a failure at the commit boundary.
    event.listen(Session, "before_commit", fail_before_commit)

    try:
        # TestClient propagates unexpected server exceptions by default.
        with pytest.raises(
            RuntimeError,
            match="Simulated failure before commit",
        ):
            add_transaction(
                client, account_id, "debit", "30.00", "payment-1"
            )
    finally:
        event.remove(Session, "before_commit", fail_before_commit)

    assert balance(client, account_id) == Decimal("100.00")

    result = history(client, account_id)
    assert result["pagination"]["total_records"] == 1
    assert result["items"][0]["reference_id"] == "deposit-1"
    
def test_concurrent_debits_cannot_overdraw_account(client):
    account_id = create_account(client)

    deposit = add_transaction(
        client, account_id, "credit", "100.00", "deposit-1"
    )
    assert deposit.status_code == 201

    start = Barrier(2)

    def debit(reference):
        # Make both workers start their requests together.
        start.wait(timeout=10)

        return add_transaction(
            client, account_id, "debit", "80.00", reference
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(debit, "payment-1")
        second = executor.submit(debit, "payment-2")

        responses = [first.result(), second.result()]

    assert sorted(response.status_code for response in responses) == [
        201,
        409,
    ]

    rejected = next(
        response for response in responses
        if response.status_code == 409
    )

    assert rejected.json()["error"]["code"] == "insufficient_balance"
    assert balance(client, account_id) == Decimal("20.00")
    assert history(client, account_id)["pagination"]["total_records"] == 2

def test_transfer_and_duplicate_protection(client):
    source_id = create_account(client)
    destination_id = create_account(client)

    assert add_transaction(
        client, source_id, "credit", "100.00", "source-deposit"
    ).status_code == 201

    assert add_transaction(
        client, destination_id, "credit", "50.00", "destination-deposit"
    ).status_code == 201

    body = {
        "source_account_id": source_id,
        "destination_account_id": destination_id,
        "amount": "30.00",
        "reference_id": "transfer-1",
        "description": "Test transfer",
    }

    response = client.post("/transfers", json=body)

    assert response.status_code == 201
    assert balance(client, source_id) == Decimal("70.00")
    assert balance(client, destination_id) == Decimal("80.00")

    duplicate = client.post("/transfers", json=body)

    assert duplicate.status_code == 409
    assert balance(client, source_id) == Decimal("70.00")
    assert balance(client, destination_id) == Decimal("80.00")

    source_history = history(client, source_id)
    destination_history = history(client, destination_id)

    assert source_history["pagination"]["total_records"] == 2
    assert destination_history["pagination"]["total_records"] == 2