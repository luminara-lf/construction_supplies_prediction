from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable


GREEN_THRESHOLD = 0.35
RED_THRESHOLD = 0.70
STALE_HOURS_THRESHOLD = 48


@dataclass(frozen=True)
class RiskScore:
    score: float
    status: str
    confidence: float
    reason_codes: list[str]
    estimated_delay_days: int
    recommended_actions: list[str]


def _clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def status_from_score(score: float) -> str:
    if score >= RED_THRESHOLD:
        return "red"
    if score >= GREEN_THRESHOLD:
        return "yellow"
    return "green"


def recommended_actions(reason_codes: Iterable[str]) -> list[str]:
    reasons = set(reason_codes)
    actions: list[str] = []
    if "LOW_STOCK" in reasons:
        actions.append("Source from backup distributor and split the order.")
    if "HIGH_LATE_RATE" in reasons:
        actions.append("Escalate with supplier and request firm ship confirmation.")
    if "ETA_VOLATILITY" in reasons or "LEAD_TIME_DRIFT" in reasons:
        actions.append("Re-sequence crew tasks to protect near-term schedule.")
    if "STALE_DATA" in reasons:
        actions.append("Run connector sync and confirm ETA with supplier rep.")
    if "ETA_PASSED" in reasons:
        actions.append("Trigger contingency procurement for immediate replacement.")
    if not actions:
        actions.append("Continue monitoring daily inventory and ETA trends.")
    return actions


def compute_risk(
    *,
    qty_ordered: float,
    qty_delivered: float,
    qty_available: float,
    eta_date: date,
    historical_late_rate: float | None,
    eta_volatility: float | None,
    lead_time_trend_days: float | None,
    source_updated_at: datetime,
) -> RiskScore:
    reason_codes: list[str] = []
    remaining_qty = max(qty_ordered - qty_delivered, 0.0)
    if remaining_qty <= 0:
        return RiskScore(
            score=0.0,
            status="green",
            confidence=0.99,
            reason_codes=["FULLY_DELIVERED"],
            estimated_delay_days=0,
            recommended_actions=["No action needed; order line is fully delivered."],
        )

    coverage_ratio = qty_available / remaining_qty if remaining_qty else 1.0
    stock_risk = _clamp(1.0 - coverage_ratio)
    if stock_risk > 0.15:
        reason_codes.append("LOW_STOCK")

    missing_history = historical_late_rate is None
    late_rate = _clamp(historical_late_rate if historical_late_rate is not None else 0.5)
    if late_rate >= 0.45:
        reason_codes.append("HIGH_LATE_RATE")

    volatility = _clamp(eta_volatility if eta_volatility is not None else 0.4)
    if volatility >= 0.50:
        reason_codes.append("ETA_VOLATILITY")

    lead_trend = 0.0
    if lead_time_trend_days is not None:
        lead_trend = _clamp(max(lead_time_trend_days, 0.0) / 14.0)
        if lead_trend >= 0.40:
            reason_codes.append("LEAD_TIME_DRIFT")

    score = 0.45 * stock_risk + 0.25 * late_rate + 0.20 * volatility + 0.10 * lead_trend

    today = datetime.now(timezone.utc).date()
    if eta_date < today:
        score += 0.2
        reason_codes.append("ETA_PASSED")

    staleness_hours = (datetime.now(timezone.utc) - source_updated_at).total_seconds() / 3600.0
    is_stale = staleness_hours > STALE_HOURS_THRESHOLD
    if is_stale:
        score += 0.1
        reason_codes.append("STALE_DATA")

    if missing_history:
        reason_codes.append("NO_HISTORY")

    score = _clamp(score)
    status = status_from_score(score)

    confidence = 0.9
    if missing_history:
        confidence -= 0.2
    if is_stale:
        confidence -= 0.15
    if not reason_codes:
        confidence += 0.05
    confidence = _clamp(confidence)

    estimated_delay_days = int(round(max(0.0, (score - 0.3) * 14)))
    actions = recommended_actions(reason_codes)

    return RiskScore(
        score=round(score, 4),
        status=status,
        confidence=round(confidence, 4),
        reason_codes=sorted(set(reason_codes)),
        estimated_delay_days=estimated_delay_days,
        recommended_actions=actions,
    )
