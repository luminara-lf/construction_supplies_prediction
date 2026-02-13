import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _database_url(raw_path: str | None = None) -> str:
    raw_path = raw_path or os.getenv("BUILD_SIGHT_DB_PATH", "/workspace/buildsight.db")
    if raw_path.startswith("sqlite://"):
        return raw_path
    return f"sqlite:///{raw_path}"


DATABASE_URL = _database_url()
SQLITE_CONNECT_ARGS = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=SQLITE_CONNECT_ARGS)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def configure_database(raw_path: str) -> None:
    global DATABASE_URL, SQLITE_CONNECT_ARGS, engine

    DATABASE_URL = _database_url(raw_path)
    SQLITE_CONNECT_ARGS = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    engine = create_engine(DATABASE_URL, connect_args=SQLITE_CONNECT_ARGS)
    SessionLocal.configure(bind=engine)
