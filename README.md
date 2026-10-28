# Transaction Ledger API

A Python backend for creating accounts, recording credits and debits,
retrieving balances and transaction history, and transferring money.

## Technology

- Python 3.12
- FastAPI
- SQLAlchemy 2.0
- PostgreSQL, hosted on Supabase
- Psycopg
- pytest

## Setup

Prerequisites:

- Python 3.12
- A PostgreSQL database
- Database credentials with permission to create tables

Create and activate a virtual environment.

Windows Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and enter your database credentials.

For Supabase, use the Session pooler details from the project's
Connect dialog. Use your database password.


Check connectivity:

```bash
python test_connection.py
```

Create tables:

```bash
python create_tables.py
```

Start the API:

```bash
python -m uvicorn main:app --reload
```

Interactive API documentation:

http://127.0.0.1:8000/docs

OpenAPI specification:

http://127.0.0.1:8000/openapi.json

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | /accounts | Create an account |
| GET | /accounts/{account_id}/balance | Retrieve balance |
| POST | /accounts/{account_id}/transactions | Credit or debit |
| GET | /accounts/{account_id}/transactions | Retrieve history |
| POST | /transfers | Transfer between accounts |

### Create an account

POST /accounts

```json
{
  "name": "Alice"
}
```

Returns 201 Created.

Only `name` is accepted. The server generates the ID and timestamp.
The initial balance is zero.

### Add a transaction

POST /accounts/{account_id}/transactions

```json
{
  "type": "credit",
  "amount": "100.00",
  "description": "Initial deposit",
  "reference_id": "deposit-001"
}
```

Returns 201 Created with the recorded transaction.

Type must be `credit` or `debit`.
Amount must be positive, with at most two decimal places.
Description is optional.

A reference must be unique within its account.
A repeated reference returns 409 without changing the balance.

### Retrieve balance

GET /accounts/{account_id}/balance

Example response:

```json
{
  "account_id": "4c3bab73-1bc8-43db-84cc-7728d71cd02a",
  "balance": "100.00"
}
```

### Retrieve history

GET /accounts/{account_id}/transactions?type=credit&page=1&limit=20

Query parameters:

- `type`: optional; `credit` or `debit`
- `page`: default 1; minimum 1
- `limit`: default 20; minimum 1; maximum 100

Results are ordered by created_at descending, then ID descending
to break timestamp ties.

Pagination metadata includes page, limit, total_records, and total_pages.
Counts reflect the selected filter.

An empty result has zero total pages.
A page beyond the final page returns an empty items list.

### Transfer money

POST /transfers

```json
{
  "source_account_id": "4c3bab73-1bc8-43db-84cc-7728d71cd02a",
  "destination_account_id": "75b5090e-0d79-48b5-8d56-05d021454b8e",
  "amount": "30.00",
  "reference_id": "transfer-001",
  "description": "Transfer to another account"
}
```

Returns 201 Created with the debit and credit entries.

Both accounts must exist and must be different.
The source must have sufficient funds.

The same reference is recorded on both accounts.
If that reference already exists on either account, the transfer
is rejected in full.

## Error responses

Errors use a consistent structure:

```json
{
  "error": {
    "code": "insufficient_balance",
    "message": "The account has insufficient balance.",
    "details": []
  }
}
```

| Status | Meaning |
|---|---|
| 404 | Account or route not found |
| 409 | Duplicate reference, insufficient funds, or balance limit exceeded |
| 422 | Invalid body, fields, UUID, pagination, or self-transfer |
| 500 | Unexpected database or application failure |

## Data integrity

- Balances and amounts use exact decimal arithmetic.
- Database constraints enforce valid transaction types, positive
  amounts, nonnegative balances, and unique account/reference pairs.
- Foreign keys prevent transactions referencing nonexistent accounts.
- Each ledger write and its balance update share one database transaction.
- Account rows are locked before balance-changing decisions.
- Transfers lock both accounts in consistent ID order.
- Transaction update and delete operations are not exposed through the API.

## Tests

Run:

```bash
python -m pytest -q --tb=short
```

Tests use temporary PostgreSQL schemas and remove them afterward.
The database user needs permission to create and drop those schemas.
Use a test project, not a production database.

Tests cover account validation, credits and debits, duplicate protection,
insufficient funds, history filtering and pagination, concurrent debits,
rollback before commit, and transfer success and rejection cases.

An internet connection is required when using hosted Supabase.
A network failure during cleanup may leave a temporary test schema.

## Project structure

- database.py: connection configuration and session factory
- models.py: database tables and constraints
- schemas.py: request and response validation
- main.py: API endpoints and ledger operations
- error_handlers.py: consistent error responses
- create_tables.py: initial table creation
- test_connection.py: connectivity check
- tests/: integration tests
