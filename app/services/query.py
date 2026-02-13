from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Alert, OrderLine, RiskAssessment, SupplierConnector


def parse_json_list(payload: str) -> list[str]:
    try:
        value = json.loads(payload)
        if isinstance(value, list):
            return [str(item) for item in value]
    except json.JSONDecodeError:
        return []
    return []


def latest_risk_assessment_subquery():
    return (
        select(
            RiskAssessment.order_line_id.label("order_line_id"),
            func.max(RiskAssessment.assessed_at).label("max_assessed_at"),
        )
        .group_by(RiskAssessment.order_line_id)
        .subquery()
    )


def latest_risk_map_for_orders(db: Session, order_ids: Iterable[str]) -> dict[str, RiskAssessment]:
    order_ids = list(order_ids)
    if not order_ids:
        return {}

    subq = latest_risk_assessment_subquery()
    rows = db.execute(
        select(RiskAssessment).join(
            subq,
            and_(
                RiskAssessment.order_line_id == subq.c.order_line_id,
                RiskAssessment.assessed_at == subq.c.max_assessed_at,
            ),
        )
    ).scalars()

    out: dict[str, RiskAssessment] = {}
    order_id_set = set(order_ids)
    for row in rows:
        if row.order_line_id in order_id_set:
            out[row.order_line_id] = row
    return out


def dashboard_summary(db: Session, tenant_id: str) -> dict[str, int | str | None]:
    open_orders = db.execute(
        select(OrderLine.id).where(and_(OrderLine.tenant_id == tenant_id, OrderLine.status == "open"))
    ).scalars()
    order_ids = list(open_orders)
    latest_map = latest_risk_map_for_orders(db, order_ids)

    red = 0
    yellow = 0
    green = 0
    for risk in latest_map.values():
        if risk.risk_status == "red":
            red += 1
        elif risk.risk_status == "yellow":
            yellow += 1
        else:
            green += 1

    open_alerts = db.execute(
        select(func.count(Alert.id)).where(and_(Alert.tenant_id == tenant_id, Alert.status == "open"))
    ).scalar_one()

    connector = db.execute(
        select(SupplierConnector)
        .where(SupplierConnector.tenant_id == tenant_id)
        .order_by(SupplierConnector.last_sync_at.desc().nullslast())
        .limit(1)
    ).scalar_one_or_none()
    last_sync_at = connector.last_sync_at if connector else None
    sync_health = connector.status if connector else "not_connected"

    return {
        "sync_health": sync_health,
        "last_sync_at": last_sync_at,
        "red_count": red,
        "yellow_count": yellow,
        "green_count": green,
        "open_alerts": open_alerts,
    }
