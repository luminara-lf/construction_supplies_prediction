from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SupplierCredentials(BaseModel):
    apiKey: str = Field(min_length=3)


class CreateSupplierConnectorRequest(BaseModel):
    supplierName: str = Field(min_length=2)
    authType: str = Field(default="api_key")
    credentials: SupplierCredentials
    pollIntervalMinutes: int = Field(default=1440, ge=120, le=1440)

    @field_validator("authType")
    @classmethod
    def auth_type_supported(cls, value: str) -> str:
        if value != "api_key":
            raise ValueError("Only api_key authType is supported in MVP.")
        return value


class SupplierConnectorResponse(BaseModel):
    id: str
    supplierName: str
    status: str
    pollIntervalMinutes: int
    createdAt: datetime


class SyncRunRequest(BaseModel):
    connectorId: str = Field(min_length=10)
    mode: str = Field(default="incremental")

    @field_validator("mode")
    @classmethod
    def mode_supported(cls, value: str) -> str:
        if value not in {"incremental", "full"}:
            raise ValueError("mode must be incremental or full")
        return value


class SyncRunResponse(BaseModel):
    jobId: str
    status: str
    processedOrders: int
    processedInventoryRows: int
    assessedOrders: int
    generatedAlerts: int


class RiskOrderItem(BaseModel):
    orderLineId: str
    supplierOrderId: str
    projectId: str
    supplierSku: str
    materialName: str
    etaDate: date
    status: str
    riskScore: float
    confidence: float
    reasonCodes: list[str]
    estimatedDelayDays: int
    recommendedActions: list[str]
    lastUpdatedAt: datetime


class PaginatedRiskOrders(BaseModel):
    items: list[RiskOrderItem]
    total: int
    page: int
    pageSize: int


class RiskHistoryPoint(BaseModel):
    assessedAt: datetime
    riskScore: float
    riskStatus: str
    confidence: float
    reasonCodes: list[str]
    estimatedDelayDays: int


class AlertView(BaseModel):
    id: str
    severity: str
    status: str
    message: str
    recommendations: list[str]
    createdAt: datetime
    acknowledgedAt: datetime | None
    resolvedAt: datetime | None


class OrderRiskDetail(BaseModel):
    orderLineId: str
    supplierOrderId: str
    projectId: str
    supplierSku: str
    materialName: str
    qtyOrdered: float
    qtyDelivered: float
    etaDate: date
    status: str
    latestRisk: RiskOrderItem | None
    riskHistory: list[RiskHistoryPoint]
    alerts: list[AlertView]


class AlertFeedbackRequest(BaseModel):
    disposition: str
    notes: str = Field(default="", max_length=500)

    @field_validator("disposition")
    @classmethod
    def validate_disposition(cls, value: str) -> str:
        allowed = {"accurate", "false_positive", "too_late"}
        if value not in allowed:
            raise ValueError(f"disposition must be one of {sorted(allowed)}")
        return value


class AlertFeedbackResponse(BaseModel):
    id: str
    alertId: str
    disposition: str
    notes: str
    createdAt: datetime


class DashboardSummaryResponse(BaseModel):
    syncHealth: str
    lastSyncAt: datetime | None
    redCount: int
    yellowCount: int
    greenCount: int
    openAlerts: int


class AlertActionResponse(BaseModel):
    alertId: str
    status: str
    updatedAt: datetime


class ListAlertsResponse(BaseModel):
    items: list[AlertView]
    total: int


class ErrorResponse(BaseModel):
    detail: str | dict[str, Any] | list[Any]
