from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import config, models
from app.services.recommendations import recommendations_for_reasons
from app.services.scoring import ScoreResult


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def latest_risk_assessment(db: Session, order_line_id: str) -> models.RiskAssessment | None:
    return (
        db.query(models.RiskAssessment)
        .filter(models.RiskAssessment.order_line_id == order_line_id)
        .order_by(models.RiskAssessment.assessed_at.desc())
        .first()
    )


def _within_cooldown(db: Session, order_line_id: str, severity: str, now: datetime) -> bool:
    threshold = now - config.ALERT_COOLDOWN
    existing = (
        db.query(models.Alert)
        .filter(
            models.Alert.order_line_id == order_line_id,
            models.Alert.severity == severity,
            models.Alert.created_at >= threshold,
        )
        .first()
    )
    return existing is not None


def _severity_for_risk(score: ScoreResult) -> str:
    if score.risk_status == "red" and score.high_priority:
        return "high"
    if score.risk_status == "red":
        return "medium"
    return "low"


def _should_trigger(previous_status: str | None, score: ScoreResult) -> bool:
    if score.risk_status not in {"yellow", "red"}:
        return False
    if previous_status is None:
        return True
    if previous_status == score.risk_status:
        return score.risk_status == "red" and score.high_priority
    rank = {"green": 0, "yellow": 1, "red": 2}
    return rank.get(score.risk_status, 0) >= rank.get(previous_status, 0)


def maybe_create_alert(
    db: Session,
    order_line: models.OrderLine,
    score: ScoreResult,
    previous_status: str | None,
) -> models.Alert | None:
    now = utcnow()
    if not _should_trigger(previous_status, score):
        return None

    severity = _severity_for_risk(score)
    if _within_cooldown(db, order_line.id, severity, now):
        return None

    recommendations = recommendations_for_reasons(order_line, score.reason_codes)
    next_step = recommendations[0]["action"] if recommendations else "Review this line with procurement."
    impact_text = str(order_line.impact_date) if order_line.impact_date else "unknown"
    reason_text = ", ".join(score.reason_codes[:3])
    message = (
        f"Risk is {score.risk_status.upper()} ({score.risk_score:.2f}) due to {reason_text}. "
        f"Next step: {next_step} Impact date: {impact_text}."
    )

    alert = models.Alert(
        tenant_id=order_line.tenant_id,
        order_line_id=order_line.id,
        severity=severity,
        status="open",
        message=message,
    )
    db.add(alert)
    db.flush()
    return alert

