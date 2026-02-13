from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SupplierConnector(Base):
    __tablename__ = "supplier_connectors"
    __table_args__ = (UniqueConstraint("tenant_id", "supplier_name", name="uq_connector_tenant_supplier"),)

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    supplier_name = Column(String, nullable=False, index=True)
    auth_type = Column(String, nullable=False)
    secret_ref = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending_validation")
    poll_interval_minutes = Column(Integer, nullable=False, default=1440)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(String, primary_key=True)
    connector_id = Column(String, ForeignKey("supplier_connectors.id"), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    mode = Column(String, nullable=False)
    status = Column(String, nullable=False)
    metrics_json = Column(Text, nullable=False, default="{}")
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class OrderLine(Base):
    __tablename__ = "order_lines"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    connector_id = Column(String, ForeignKey("supplier_connectors.id"), nullable=False, index=True)
    project_id = Column(String, nullable=False, index=True)
    supplier_order_id = Column(String, nullable=False, index=True)
    supplier_sku = Column(String, nullable=False, index=True)
    material_name = Column(String, nullable=False)
    qty_ordered = Column(Float, nullable=False)
    qty_delivered = Column(Float, nullable=False, default=0)
    eta_date = Column(Date, nullable=False, index=True)
    status = Column(String, nullable=False, default="open", index=True)
    historical_late_rate = Column(Float, nullable=True)
    eta_volatility = Column(Float, nullable=True)
    lead_time_trend_days = Column(Float, nullable=True)
    last_source_update = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    connector = relationship("SupplierConnector")


class SupplierInventorySnapshot(Base):
    __tablename__ = "supplier_inventory_snapshots"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    connector_id = Column(String, ForeignKey("supplier_connectors.id"), nullable=False, index=True)
    supplier_sku = Column(String, nullable=False, index=True)
    qty_available = Column(Float, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    raw_payload_ref = Column(Text, nullable=False, default="{}")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id = Column(String, primary_key=True)
    order_line_id = Column(String, ForeignKey("order_lines.id"), nullable=False, index=True)
    model_version = Column(String, nullable=False, default="heuristic_v1")
    risk_score = Column(Float, nullable=False)
    risk_status = Column(String, nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    reason_codes_json = Column(Text, nullable=False, default="[]")
    estimated_delay_days = Column(Integer, nullable=False, default=0)
    assessed_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    order_line = relationship("OrderLine")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    order_line_id = Column(String, ForeignKey("order_lines.id"), nullable=False, index=True)
    severity = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True, default="open")
    message = Column(Text, nullable=False)
    recommendations_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    order_line = relationship("OrderLine")


class AlertFeedback(Base):
    __tablename__ = "alert_feedback"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    alert_id = Column(String, ForeignKey("alerts.id"), nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    disposition = Column(String, nullable=False)
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    alert = relationship("Alert")
