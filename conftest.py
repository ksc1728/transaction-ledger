from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Base, engine
from main import app, get_db


@pytest.fixture
def client():
    
    schema = f"test_{uuid4().hex}"

    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    
    test_engine = engine.execution_options(
        schema_translate_map={None: schema}
    )

    try:
        Base.metadata.create_all(bind=test_engine)

        def override_get_db():
            with Session(test_engine) as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as test_client:
            yield test_client

    finally:
        app.dependency_overrides.pop(get_db, None)

        # Remove only this test's generated schema and its tables.
        with engine.begin() as connection:
            connection.execute(
                text(f'DROP SCHEMA "{schema}" CASCADE')
            )