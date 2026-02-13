from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.auth import RequestContext
from app.models import Alert, OrderLine, RiskAssessment, SupplierConnector, SupplierInventorySnapshot, SyncRun
from app.services.risk import compute_risk
from app.services.suppliers import generate_supplier_payload


ALERT_COOLDOWN_HOURS = 12


def _json(data: list[str] | dict[str, int | str | float]) -> str:
    return json.dumps(data, separators=(",", ":"))


def _upsert_order_line(
    db: Session,
    *,
    tenant_id: str,
    connector_id: str,
    row,
) -> OrderLine:
    existing = db.execute(
        select(OrderLine).where(
            and_(
                OrderLine.tenant_id == tenant_id,
                OrderLine.connector_id == connector_id,
                OrderLine.supplier_order_id == row.supplier_order_id,
                OrderLine.supplier_sku == row.supplier_sku,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = OrderLine(
            id=str(uuid4()),
            tenant_id=tenant_id,
            connector_id=connector_id,
            project_id=row.project_id,
            supplier_order_id=row.supplier_order_id,
            supplier_sku=row.supplier_sku,
            material_name=row.material_name,
            qty_ordered=row.qty_ordered,
            qty_delivered=row.qty_delivered,
            eta_date=row.eta_date,
            status="open" if row.qty_delivered < row.qty_ordered else "delivered",
            historical_late_rate=row.historical_late_rate,
            eta_volatility=row.eta_volatility,
            lead_time_trend_days=row.lead_time_trend_days,
            last_source_update=row.source_updated_at,
        )
        db.add(existing)
        return existing

    existing.project_id = row.project_id
    existing.material_name = row.material_name
    existing.qty_ordered = row.qty_ordered
    existing.qty_delivered = row.qty_delivered
    existing.eta_date = row.eta_date
    existing.status = "open" if row.qty_delivered < row.qty_ordered else "delivered"
    existing.historical_late_rate = row.historical_late_rate
    existing.eta_volatility = row.eta_volatility
    existing.lead_time_trend_days = row.lead_time_trend_days
    existing.last_source_update = row.source_updated_at
    return existing


def _latest_assessment(db: Session, order_line_id: str) -> RiskAssessment | None:
    return db.execute(
        select(RiskAssessment)
        .where(RiskAssessment.order_line_id == order_line_id)
        .order_by(desc(RiskAssessment.assessed_at))
        .limit(1)
    ).scalar_one_or_none()


def _recent_alert_exists(db: Session, tenant_id: str, order_line_id: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ALERT_COOLDOWN_HOURS)
    count = db.execute(
        select(func.count(Alert.id)).where(
            and_(
                Alert.tenant_id == tenant_id,
                Alert.order_line_id == order_line_id,
                Alert.created_at >= cutoff,
            )
        )
    ).scalar_one()
    return count > 0


def _alert_message(order: OrderLine, reason_codes: list[str], status: str) -> str:
    reason_text = ", ".join(reason_codes) if reason_codes else "insufficient confidence"
    return (
        f"{status.upper()} risk for {order.material_name} "
        f"(PO {order.supplier_order_id}, SKU {order.supplier_sku}) due to {reason_text}."
    )


def run_sync(db: Session, ctx: RequestContext, connector: SupplierConnector, mode: str) -> dict[str, int | str]:
    sync_run = SyncRun(
        id=str(uuid4()),
        connector_id=connector.id,
        tenant_id=ctx.tenant_id,
        mode=mode,
        status="running",
        metrics_json="{}",
        started_at=datetime.now(timezone.utc),
    )
    db.add(sync_run)
    db.flush()

    processed_orders = 0
    processed_inventory = 0
    assessed_orders = 0
    generated_alerts = 0

    try:
        payload = generate_supplier_payload(connector.supplier_name, connector.id)
        inventory_by_sku: dict[str, float] = {}

        for inv in payload.inventory:
            snapshot = SupplierInventorySnapshot(
                id=str(uuid4()),
                tenant_id=ctx.tenant_id,
                connector_id=connector.id,
                supplier_sku=inv.supplier_sku,
                qty_available=inv.qty_available,
                captured_at=inv.captured_at,
                raw_payload_ref=_json({"source": connector.supplier_name}),
            )
            db.add(snapshot)
            inventory_by_sku[inv.supplier_sku] = inv.qty_available
            processed_inventory += 1

        db.flush()

        for order_row in payload.orders:
            order = _upsert_order_line(
                db,
                tenant_id=ctx.tenant_id,
                connector_id=connector.id,
                row=order_row,
            )
            processed_orders += 1
            db.flush()

            qty_available = inventory_by_sku.get(order.supplier_sku, 0.0)
            risk = compute_risk(
                qty_ordered=order.qty_ordered,
                qty_delivered=order.qty_delivered,
                qty_available=qty_available,
                eta_date=order.eta_date,
                historical_late_rate=order.historical_late_rate,
                eta_volatility=order.eta_volatility,
                lead_time_trend_days=order.lead_time_trend_days,
                source_updated_at=order.last_source_update,
            )

            previous = _latest_assessment(db, order.id)
            assessment = RiskAssessment(
                id=str(uuid4()),
                order_line_id=order.id,
                model_version="heuristic_v1",
                risk_score=risk.score,
                risk_status=risk.status,
                confidence=risk.confidence,
                reason_codes_json=_json(risk.reason_codes),
                estimated_delay_days=risk.estimated_delay_days,
                assessed_at=datetime.now(timezone.utc),
            )
            db.add(assessment)
            assessed_orders += 1

            transitioned = previous is None or previous.risk_status != risk.status
            needs_alert = risk.status in {"yellow", "red"} and transitioned
            if needs_alert and not _recent_alert_exists(db, ctx.tenant_id, order.id):
                alert = Alert(
                    id=str(uuid4()),
                    tenant_id=ctx.tenant_id,
                    order_line_id=order.id,
                    severity="high" if risk.status == "red" else "medium",
                    status="open",
                    message=_alert_message(order, risk.reason_codes, risk.status),
                    recommendations_json=_json(risk.recommended_actions),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(alert)
                generated_alerts += 1

        connector.status = "active"
        connector.last_sync_at = datetime.now(timezone.utc)
        connector.last_error = None
        sync_run.status = "success"
        sync_run.completed_at = datetime.now(timezone.utc)
        sync_run.metrics_json = _json(
            {
                "processed_orders": processed_orders,
                "processed_inventory_rows": processed_inventory,
                "assessed_orders": assessed_orders,
                "generated_alerts": generated_alerts,
            }
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        connector.status = "degraded"
        connector.last_error = str(exc)
        sync_run.status = "failed"
        sync_run.completed_at = datetime.now(timezone.utc)
        sync_run.metrics_json = _json({"error": str(exc)})
        db.commit()
        raise

    return {
        "job_id": sync_run.id,
        "status": "queued",
        "processed_orders": processed_orders,
        "processed_inventory_rows": processed_inventory,
        "assessed_orders": assessed_orders,
        "generated_alerts": generated_alerts,
    }
