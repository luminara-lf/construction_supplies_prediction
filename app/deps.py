from __future__ import annotations

from dataclasses import dataclass
from typing import Generator

from fastapi import Header
from sqlalchemy.orm import Session

from app import config
from app import database


@dataclass
class RequestContext:
    tenant_id: str
    user_id: str
    role: str


def get_db() -> Generator[Session, None, None]:
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_request_context(
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> RequestContext:
    return RequestContext(
        tenant_id=x_tenant_id or config.DEFAULT_TENANT_ID,
        user_id=x_user_id or config.DEFAULT_USER_ID,
        role=(x_user_role or config.DEFAULT_USER_ROLE).lower(),
    )

