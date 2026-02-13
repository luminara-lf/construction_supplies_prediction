from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConnectorCreateRequest(BaseModel):
    supplier_name: str = Field(alias="supplierName")
    auth_type: str = Field(alias="authType")
    credentials: dict[str, Any]
    poll_interval_minutes: int = Field(default=1440, alias="pollIntervalMinutes")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("poll_interval_minutes")
    @classmethod
    def validate_poll_interval(cls, value: int) -> int:
        if value < 120 or value > 1440:
            raise ValueError("pollIntervalMinutes must be between 120 and 1440 for MVP")
        return value


class ConnectorResponse(BaseModel):
    id: str
    tenant_id: str = Field(alias="tenantId")
    supplier_name: str = Field(alias="supplierName")
    auth_type: str = Field(alias="authType")
    status: str
    poll_interval_minutes: int = Field(alias="pollIntervalMinutes")
    last_sync_at: datetime | None = Field(alias="lastSyncAt")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SyncRunRequest(BaseModel):
    connector_id: str = Field(alias="connectorId")
    mode: Literal["incremental", "full"] = "incremental"

    model_config = ConfigDict(populate_by_name=True)


class SyncRunResponse(BaseModel):
    id: str
    status: str
    mode: str
    attempts: int
    started_at: datetime = Field(alias="startedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class OrderRiskItem(BaseModel):
    order_line_id: str = Field(alias="orderLineId")
    project_id: str | None = Field(alias="projectId")
    supplier_id: str = Field(alias="supplierId")
    status: Literal["green", "yellow", "red"]
    risk_score: float = Field(alias="riskScore")
    confidence: float
    reason_codes: list[str] = Field(alias="reasonCodes")
    estimated_delay_days: int = Field(alias="estimatedDelayDays")
    impact_date: date | None = Field(alias="impactDate")
    stale: bool = False
    last_updated: datetime | None = Field(alias="lastUpdated", default=None)

    model_config = ConfigDict(populate_by_name=True)


class OrderRiskListResponse(BaseModel):
    items: list[OrderRiskItem]
    total: int


class TimelineEvent(BaseModel):
    event_type: str = Field(alias="eventType")
    timestamp: datetime
    detail: str

    model_config = ConfigDict(populate_by_name=True)


class Recommendation(BaseModel):
    title: str
    action: str
    priority: Literal["high", "medium", "low"]


class OrderDetailResponse(BaseModel):
    order_line_id: str = Field(alias="orderLineId")
    supplier_order_id: str = Field(alias="supplierOrderId")
    supplier_sku: str = Field(alias="supplierSku")
    qty_ordered: float = Field(alias="qtyOrdered")
    qty_delivered: float = Field(alias="qtyDelivered")
    eta_date: date | None = Field(alias="etaDate")
    impact_date: date | None = Field(alias="impactDate")
    current_status: str = Field(alias="currentStatus")
    current_score: float = Field(alias="currentScore")
    confidence: float
    reason_codes: list[str] = Field(alias="reasonCodes")
    estimated_delay_days: int = Field(alias="estimatedDelayDays")
    risk_history: list[dict[str, Any]] = Field(alias="riskHistory")
    timeline: list[TimelineEvent]
    recommendations: list[Recommendation]

    model_config = ConfigDict(populate_by_name=True)


class AlertFeedbackRequest(BaseModel):
    disposition: Literal["accurate", "false_positive", "too_late"]
    notes: str = ""

    @field_validator("notes")
    @classmethod
    def validate_notes_length(cls, value: str) -> str:
        if len(value) > 500:
            raise ValueError("notes must be at most 500 characters")
        return value


class AlertFeedbackResponse(BaseModel):
    id: str
    alert_id: str = Field(alias="alertId")
    user_id: str = Field(alias="userId")
    disposition: str
    notes: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ResolveAlertRequest(BaseModel):
    resolution_note: str = Field(alias="resolutionNote", default="")

    model_config = ConfigDict(populate_by_name=True)

