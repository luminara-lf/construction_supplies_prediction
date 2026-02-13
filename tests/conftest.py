from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.database as database
from app.main import app


@pytest.fixture()
def default_headers() -> dict[str, str]:
    return {
        "x-tenant-id": "test-tenant",
        "x-user-id": "tester",
        "x-user-role": "owner",
    }


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test_buildsight.db"
    database.configure_database(str(db_path))
    database.Base.metadata.drop_all(bind=database.engine)
    database.init_db()

    with TestClient(app) as test_client:
        yield test_client
