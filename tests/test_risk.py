from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.services.risk import compute_risk


def test_compute_risk_fully_delivered_is_green():
    result = compute_risk(
        qty_ordered=100,
        qty_delivered=100,
        qty_available=0,
        eta_date=date.today(),
        historical_late_rate=0.9,
        eta_volatility=1.0,
        lead_time_trend_days=10,
        source_updated_at=datetime.now(timezone.utc),
    )
    assert result.status == "green"
    assert result.score == 0.0
    assert "FULLY_DELIVERED" in result.reason_codes


def test_compute_risk_low_stock_and_stale_becomes_red():
    result = compute_risk(
        qty_ordered=120,
        qty_delivered=10,
        qty_available=5,
        eta_date=date.today() - timedelta(days=1),
        historical_late_rate=0.7,
        eta_volatility=0.8,
        lead_time_trend_days=9,
        source_updated_at=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    assert result.status == "red"
    assert result.score >= 0.7
    assert "LOW_STOCK" in result.reason_codes
    assert "STALE_DATA" in result.reason_codes
