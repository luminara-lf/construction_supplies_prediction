from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import config, models


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def status_from_score(score: float) -> str:
    if score < 0.35:
        return "green"
    if score < 0.70:
        return "yellow"
    return "red"


@dataclass
class ScoreResult:
    risk_score: float
    risk_status: str
    confidence: float
    reason_codes: list[str]
    estimated_delay_days: int
    stale_data: bool
    high_priority: bool
    assessed_at: datetime


def _impact_within_high_priority_window(impact_date: date | datetime | None, now: datetime) -> bool:
    if impact_date is None:
        return False
    if isinstance(impact_date, datetime):
        impact_dt = impact_date
    else:
        impact_dt = datetime.combine(impact_date, datetime.min.time())
    return impact_dt <= now + timedelta(days=config.HIGH_PRIORITY_IMPACT_DAYS)


def compute_order_risk(db: Session, order_line: models.OrderLine) -> ScoreResult:
    now = utcnow()
    latest_inventory = (
        db.query(models.SupplierInventorySnapshot)
        .filter(
            models.SupplierInventorySnapshot.connector_id == order_line.supplier_id,
            models.SupplierInventorySnapshot.supplier_sku == order_line.supplier_sku,
        )
        .order_by(models.SupplierInventorySnapshot.source_timestamp.desc())
        .first()
    )

    qty_available = latest_inventory.qty_available if latest_inventory else 0.0
    remaining_qty = max(order_line.qty_ordered - order_line.qty_delivered, 0.0)
    coverage_ratio = 1.0 if remaining_qty == 0 else qty_available / max(remaining_qty, 1.0)
    inventory_component = clamp(1.0 - min(coverage_ratio, 1.0), 0.0, 1.0)

    historical_orders = (
        db.query(models.OrderLine)
        .filter(
            models.OrderLine.tenant_id == order_line.tenant_id,
            models.OrderLine.supplier_id == order_line.supplier_id,
            models.OrderLine.supplier_sku == order_line.supplier_sku,
            models.OrderLine.status.in_(["delivered", "delayed"]),
            models.OrderLine.id != order_line.id,
        )
        .all()
    )
    has_history = len(historical_orders) > 0

    if has_history:
        delayed_count = sum(1 for item in historical_orders if item.status == "delayed")
        late_rate_component = delayed_count / len(historical_orders)
        historical_lead = [item.lead_time_days for item in historical_orders if item.lead_time_days and item.lead_time_days > 0]
        if historical_lead and order_line.lead_time_days > 0:
            avg_lead = sum(historical_lead) / len(historical_lead)
            lead_time_component = clamp((order_line.lead_time_days - avg_lead) / max(avg_lead, 1.0), 0.0, 1.0)
        else:
            lead_time_component = 0.0
        score = (
            0.45 * inventory_component
            + 0.25 * late_rate_component
            + 0.20 * clamp(order_line.eta_variance_days / 7.0, 0.0, 1.0)
            + 0.10 * lead_time_component
        )
        confidence = 0.78
    else:
        late_rate_component = 0.0
        lead_time_component = 0.0
        score = 0.70 * inventory_component + 0.30 * clamp(order_line.eta_variance_days / 7.0, 0.0, 1.0)
        confidence = 0.45

    stale_data = False
    if not latest_inventory:
        stale_data = True
    else:
        age_hours = (now - latest_inventory.source_timestamp).total_seconds() / 3600.0
        stale_data = age_hours > config.STALE_DATA_THRESHOLD_HOURS

    eta_volatility_component = clamp(order_line.eta_variance_days / 7.0, 0.0, 1.0)
    reason_codes: list[str] = []
    if inventory_component >= 0.45:
        reason_codes.append("LOW_STOCK")
    if has_history and late_rate_component >= 0.40:
        reason_codes.append("SUPPLIER_LATE_HISTORY")
    if eta_volatility_component >= 0.40:
        reason_codes.append("ETA_VOLATILITY")
    if has_history and lead_time_component >= 0.35:
        reason_codes.append("LEAD_TIME_UPTREND")
    if not has_history:
        reason_codes.append("NO_HISTORY")
    if order_line.qty_delivered > 0 and remaining_qty > 0:
        reason_codes.append("PARTIAL_DELIVERY")

    if stale_data:
        reason_codes.append("STALE_DATA")
        confidence -= 0.15

    if remaining_qty <= 0:
        score = 0.05

    score = clamp(float(score), 0.0, 0.99)
    risk_status = status_from_score(score)
    if stale_data and risk_status == "green":
        score = max(score, 0.36)
        risk_status = "yellow"

    if not reason_codes:
        reason_codes.append("HEURISTIC_BASELINE")

    confidence = clamp(confidence, 0.2, 0.95)
    estimated_delay_days = int(math.ceil(score * 10)) if remaining_qty > 0 else 0
    high_priority = risk_status == "red" and _impact_within_high_priority_window(order_line.impact_date, now)
    return ScoreResult(
        risk_score=round(score, 4),
        risk_status=risk_status,
        confidence=round(confidence, 4),
        reason_codes=reason_codes,
        estimated_delay_days=estimated_delay_days,
        stale_data=stale_data,
        high_priority=high_priority,
        assessed_at=now,
    )

