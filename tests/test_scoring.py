from __future__ import annotations

from datetime import timedelta

from app import models
from app.services.scoring import compute_order_risk, status_from_score, utcnow


def test_status_threshold_boundaries():
    assert status_from_score(0.34) == "green"
    assert status_from_score(0.35) == "yellow"
    assert status_from_score(0.69) == "yellow"
    assert status_from_score(0.70) == "red"


def test_red_risk_when_low_stock_and_late_history(db_session):
    now = utcnow()
    connector = models.SupplierConnector(
        tenant_id="t1",
        supplier_name="MetroLumber",
        auth_type="api_key",
        secret_ref="secret://test",
        status="healthy",
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)

    db_session.add(
        models.SupplierInventorySnapshot(
            connector_id=connector.id,
            supplier_sku="LUM-2X4-8",
            qty_available=10,
            source_timestamp=now - timedelta(hours=1),
        )
    )

    for idx in range(5):
        db_session.add(
            models.OrderLine(
                tenant_id="t1",
                supplier_id=connector.id,
                supplier_order_id=f"HIST-{idx}",
                supplier_sku="LUM-2X4-8",
                qty_ordered=100,
                qty_delivered=100,
                status="delayed" if idx < 4 else "delivered",
                lead_time_days=14,
            )
        )

    current = models.OrderLine(
        tenant_id="t1",
        supplier_id=connector.id,
        supplier_order_id="OPEN-1",
        supplier_sku="LUM-2X4-8",
        qty_ordered=120,
        qty_delivered=10,
        status="open",
        eta_variance_days=4.0,
        lead_time_days=18.0,
        impact_date=(now + timedelta(days=3)).date(),
    )
    db_session.add(current)
    db_session.commit()

    result = compute_order_risk(db_session, current)
    assert result.risk_status == "red"
    assert "LOW_STOCK" in result.reason_codes
    assert "SUPPLIER_LATE_HISTORY" in result.reason_codes


def test_stale_data_never_returns_green(db_session):
    now = utcnow()
    connector = models.SupplierConnector(
        tenant_id="t2",
        supplier_name="BuildPro",
        auth_type="api_key",
        secret_ref="secret://test2",
        status="healthy",
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)

    db_session.add(
        models.SupplierInventorySnapshot(
            connector_id=connector.id,
            supplier_sku="CONC-STD-80",
            qty_available=999,
            source_timestamp=now - timedelta(hours=80),
        )
    )
    order = models.OrderLine(
        tenant_id="t2",
        supplier_id=connector.id,
        supplier_order_id="OPEN-2",
        supplier_sku="CONC-STD-80",
        qty_ordered=30,
        qty_delivered=0,
        status="open",
        eta_variance_days=0.1,
        lead_time_days=2.0,
    )
    db_session.add(order)
    db_session.commit()

    result = compute_order_risk(db_session, order)
    assert result.risk_status == "yellow"
    assert "STALE_DATA" in result.reason_codes


def test_partial_delivery_adds_reason_code(db_session):
    now = utcnow()
    connector = models.SupplierConnector(
        tenant_id="t3",
        supplier_name="RapidRoof",
        auth_type="api_key",
        secret_ref="secret://test3",
        status="healthy",
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)

    db_session.add(
        models.SupplierInventorySnapshot(
            connector_id=connector.id,
            supplier_sku="ROOF-SHINGLE",
            qty_available=10,
            source_timestamp=now - timedelta(hours=1),
        )
    )
    order = models.OrderLine(
        tenant_id="t3",
        supplier_id=connector.id,
        supplier_order_id="OPEN-3",
        supplier_sku="ROOF-SHINGLE",
        qty_ordered=100,
        qty_delivered=40,
        status="open",
        eta_variance_days=2.0,
        lead_time_days=7.0,
    )
    db_session.add(order)
    db_session.commit()

    result = compute_order_risk(db_session, order)
    assert "PARTIAL_DELIVERY" in result.reason_codes

