from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import database
from app.main import create_app


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_buildsight.db"
    database.reset_engine(f"sqlite:///{db_path}")
    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test_api_buildsight.db"
    database.reset_engine(f"sqlite:///{db_path}")
    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)
    app = create_app(seed_demo=False)
    with TestClient(app) as test_client:
        yield test_client

