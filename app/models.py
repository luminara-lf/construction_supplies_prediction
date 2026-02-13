from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="coordinator")
    notification_preferences: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_target_dates: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SupplierConnector(Base):
    __tablename__ = "supplier_connectors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "supplier_name", name="uq_supplier_connector_tenant_supplier"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    supplier_name: Mapped[str] = mapped_column(String(128), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_validation")
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1440)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stale_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SupplierInventorySnapshot(Base):
    __tablename__ = "supplier_inventory_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("supplier_connectors.id"), nullable=False, index=True)
    supplier_sku: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    qty_available: Mapped[float] = mapped_column(Float, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_payload_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "supplier_order_id", "supplier_sku", name="uq_orderline_tenant_supplier_order_sku"),
        Index("ix_order_lines_tenant_status_eta", "tenant_id", "status", "eta_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("supplier_connectors.id"), nullable=False, index=True)
    supplier_order_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    supplier_sku: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    qty_ordered: Mapped[float] = mapped_column(Float, nullable=False)
    qty_delivered: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    eta_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    impact_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    eta_variance_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    lead_time_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        Index("ix_risk_assessments_order_line_assessed", "order_line_id", "assessed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_line_id: Mapped[str] = mapped_column(String(36), ForeignKey("order_lines.id"), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="heuristic_v1")
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_status: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_delay_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_tenant_severity_status_created", "tenant_id", "severity", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    order_line_id: Mapped[str] = mapped_column(String(36), ForeignKey("order_lines.id"), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AlertFeedback(Base):
    __tablename__ = "alert_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("alerts.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="heuristic_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("supplier_connectors.id"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="incremental")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    impacted_orders_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


