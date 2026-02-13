from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app import database, models
from app.services.alerts import latest_risk_assessment, maybe_create_alert
from app.services.scoring import compute_order_risk


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def queue_sync_run(db: Session, connector_id: str, mode: str = "incremental") -> models.SyncRun:
    run = models.SyncRun(connector_id=connector_id, mode=mode, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _mock_supplier_payload(connector: models.SupplierConnector) -> dict[str, list[dict[str, Any]]]:
    now = utcnow()
    source_ts = now - timedelta(hours=2)
    stale_ts = now - timedelta(hours=52)

    if connector.supplier_name == "MetroLumber":
        return {
            "inventory": [
                {"sku": "LUM-2X4-8", "qty_available": 120, "source_timestamp": source_ts.isoformat()},
                {"sku": "PLY-3Q-4X8", "qty_available": 20, "source_timestamp": source_ts.isoformat()},
            ],
            "orders": [
                {
                    "external_order_line_id": "ML-1001-L1",
                    "supplier_order_id": "ML-1001",
                    "supplier_sku": "LUM-2X4-8",
                    "qty_ordered": 150,
                    "qty_delivered": 30,
                    "eta_date": (now.date() + timedelta(days=2)).isoformat(),
                    "impact_date": (now.date() + timedelta(days=4)).isoformat(),
                    "status": "open",
                    "eta_variance_days": 2.0,
                    "lead_time_days": 7.0,
                    "source_timestamp": source_ts.isoformat(),
                },
                {
                    "external_order_line_id": "ML-1002-L1",
                    "supplier_order_id": "ML-1002",
                    "supplier_sku": "PLY-3Q-4X8",
                    "qty_ordered": 40,
                    "qty_delivered": 0,
                    "eta_date": (now.date() + timedelta(days=8)).isoformat(),
                    "impact_date": (now.date() + timedelta(days=9)).isoformat(),
                    "status": "open",
                    "eta_variance_days": 0.5,
                    "lead_time_days": 9.0,
                    "source_timestamp": source_ts.isoformat(),
                },
            ],
        }

    if connector.supplier_name == "BuildPro":
        return {
            "inventory": [
                {"sku": "CONC-STD-80", "qty_available": 10, "source_timestamp": source_ts.isoformat()},
                {"sku": "REB-10MM", "qty_available": 500, "source_timestamp": stale_ts.isoformat()},
            ],
            "orders": [
                {
                    "external_order_line_id": "BP-882-L1",
                    "supplier_order_id": "BP-882",
                    "supplier_sku": "CONC-STD-80",
                    "qty_ordered": 40,
                    "qty_delivered": 0,
                    "eta_date": (now.date() + timedelta(days=3)).isoformat(),
                    "impact_date": (now.date() + timedelta(days=3)).isoformat(),
                    "status": "open",
                    "eta_variance_days": 4.0,
                    "lead_time_days": 12.0,
                    "source_timestamp": source_ts.isoformat(),
                },
                {
                    "external_order_line_id": "BP-883-L1",
                    "supplier_order_id": "BP-883",
                    "supplier_sku": "REB-10MM",
                    "qty_ordered": 300,
                    "qty_delivered": 120,
                    "eta_date": (now.date() + timedelta(days=1)).isoformat(),
                    "impact_date": (now.date() + timedelta(days=2)).isoformat(),
                    "status": "open",
                    "eta_variance_days": 1.0,
                    "lead_time_days": 6.0,
                    "source_timestamp": stale_ts.isoformat(),
                },
            ],
        }

    return {"inventory": [], "orders": []}


def _parse_datetime(raw: str | None) -> datetime:
    if not raw:
        raise ValueError("source_timestamp is required")
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    return date.fromisoformat(raw)


def _validate_source_timestamp(source_timestamp: datetime) -> None:
    if source_timestamp is None:
        raise ValueError("source_timestamp is required")
    if source_timestamp > utcnow() + timedelta(hours=24):
        raise ValueError("source_timestamp cannot be more than 24 hours in the future")


def _validate_inventory_record(record: dict[str, Any]) -> None:
    required = {"sku", "qty_available", "source_timestamp"}
    missing = required - set(record)
    if missing:
        raise ValueError(f"inventory record missing fields: {', '.join(sorted(missing))}")
    source_timestamp = _parse_datetime(record["source_timestamp"])
    _validate_source_timestamp(source_timestamp)


def _validate_order_record(record: dict[str, Any]) -> None:
    required = {
        "external_order_line_id",
        "supplier_order_id",
        "supplier_sku",
        "qty_ordered",
        "source_timestamp",
    }
    missing = required - set(record)
    if missing:
        raise ValueError(f"order record missing fields: {', '.join(sorted(missing))}")
    source_timestamp = _parse_datetime(record["source_timestamp"])
    _validate_source_timestamp(source_timestamp)


def _upsert_inventory(db: Session, connector: models.SupplierConnector, payload: dict[str, Any]) -> None:
    for record in payload["inventory"]:
        _validate_inventory_record(record)
        snapshot = models.SupplierInventorySnapshot(
            connector_id=connector.id,
            supplier_sku=record["sku"],
            qty_available=float(record["qty_available"]),
            source_timestamp=_parse_datetime(record["source_timestamp"]),
            raw_payload_ref=f"mock://{connector.supplier_name}/{record['sku']}",
        )
        db.add(snapshot)


def _hash_record(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _upsert_orders(db: Session, connector: models.SupplierConnector, payload: dict[str, Any]) -> list[models.OrderLine]:
    upserted: list[models.OrderLine] = []
    for record in payload["orders"]:
        _validate_order_record(record)
        record_hash = _hash_record(record)
        source_ts = _parse_datetime(record["source_timestamp"])
        existing = (
            db.query(models.OrderLine)
            .filter(
                models.OrderLine.tenant_id == connector.tenant_id,
                models.OrderLine.supplier_order_id == record["supplier_order_id"],
                models.OrderLine.supplier_sku == record["supplier_sku"],
            )
            .first()
        )

        if existing and existing.source_hash == record_hash and existing.source_timestamp == source_ts:
            upserted.append(existing)
            continue

        if not existing:
            existing = models.OrderLine(
                tenant_id=connector.tenant_id,
                supplier_id=connector.id,
                supplier_order_id=record["supplier_order_id"],
                supplier_sku=record["supplier_sku"],
                qty_ordered=float(record["qty_ordered"]),
                qty_delivered=float(record.get("qty_delivered", 0)),
                eta_date=_parse_date(record.get("eta_date")),
                impact_date=_parse_date(record.get("impact_date")),
                status=record.get("status", "open"),
                source_timestamp=source_ts,
                source_hash=record_hash,
                eta_variance_days=float(record.get("eta_variance_days", 0)),
                lead_time_days=float(record.get("lead_time_days", 0)),
                last_synced_at=utcnow(),
            )
            db.add(existing)
            upserted.append(existing)
            continue

        existing.qty_ordered = float(record["qty_ordered"])
        existing.qty_delivered = float(record.get("qty_delivered", existing.qty_delivered))
        existing.eta_date = _parse_date(record.get("eta_date"))
        existing.impact_date = _parse_date(record.get("impact_date"))
        existing.status = record.get("status", existing.status)
        existing.source_timestamp = source_ts
        existing.source_hash = record_hash
        existing.eta_variance_days = float(record.get("eta_variance_days", existing.eta_variance_days))
        existing.lead_time_days = float(record.get("lead_time_days", existing.lead_time_days))
        existing.last_synced_at = utcnow()
        upserted.append(existing)
    return upserted


def _apply_scoring_and_alerts(db: Session, order_lines: list[models.OrderLine]) -> list[str]:
    impacted: list[str] = []
    for order_line in order_lines:
        if order_line.status not in {"open", "partially_delivered"}:
            continue
        previous = latest_risk_assessment(db, order_line.id)
        previous_status = previous.risk_status if previous else None
        score = compute_order_risk(db, order_line)

        assessment = models.RiskAssessment(
            order_line_id=order_line.id,
            model_version="heuristic_v1",
            risk_score=score.risk_score,
            risk_status=score.risk_status,
            confidence=score.confidence,
            reason_codes_json=json.dumps(score.reason_codes),
            estimated_delay_days=score.estimated_delay_days,
            stale_data=score.stale_data,
            assessed_at=score.assessed_at,
        )
        db.add(assessment)
        alert = maybe_create_alert(db, order_line, score, previous_status)
        if alert:
            impacted.append(order_line.id)
    return impacted


def _run_single_attempt(db: Session, connector: models.SupplierConnector, mode: str) -> list[str]:
    payload = _mock_supplier_payload(connector)
    _upsert_inventory(db, connector, payload)
    order_lines = _upsert_orders(db, connector, payload)
    impacted = _apply_scoring_and_alerts(db, order_lines)
    connector.status = "healthy"
    connector.last_sync_at = utcnow()
    connector.last_sync_error = None
    connector.stale_since = None
    return impacted


def run_sync_job(sync_run_id: str) -> None:
    db = database.SessionLocal()
    try:
        sync_run = db.query(models.SyncRun).filter(models.SyncRun.id == sync_run_id).first()
        if not sync_run:
            return
        connector = db.query(models.SupplierConnector).filter(models.SupplierConnector.id == sync_run.connector_id).first()
        if not connector:
            sync_run.status = "failed"
            sync_run.error = "connector not found"
            sync_run.completed_at = utcnow()
            db.commit()
            return

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            sync_run.attempts = attempt
            sync_run.status = "running"
            db.commit()
            try:
                impacted = _run_single_attempt(db, connector, sync_run.mode)
                sync_run.status = "success"
                sync_run.error = None
                sync_run.impacted_orders_json = json.dumps(impacted)
                sync_run.completed_at = utcnow()
                db.commit()
                return
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                sync_run = db.query(models.SyncRun).filter(models.SyncRun.id == sync_run_id).first()
                connector = db.query(models.SupplierConnector).filter(models.SupplierConnector.id == sync_run.connector_id).first()
                if not sync_run or not connector:
                    return
                sync_run.attempts = attempt
                sync_run.error = str(exc)
                if attempt < max_attempts:
                    sync_run.status = "retrying"
                    db.commit()
                    time.sleep(0.25 * (2 ** (attempt - 1)))
                    continue
                sync_run.status = "failed"
                sync_run.completed_at = utcnow()
                connector.status = "degraded"
                connector.last_sync_error = str(exc)
                connector.stale_since = utcnow()
                db.commit()
                return
    finally:
        db.close()

