from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.auth import RequestContext, get_request_context, require_roles
from app.database import get_db, init_db
from app.models import Alert, AlertFeedback, OrderLine, RiskAssessment, SupplierConnector, SupplierInventorySnapshot
from app.schemas import (
    AlertActionResponse,
    AlertFeedbackRequest,
    AlertFeedbackResponse,
    AlertView,
    CreateSupplierConnectorRequest,
    DashboardSummaryResponse,
    ListAlertsResponse,
    OrderRiskDetail,
    PaginatedRiskOrders,
    RiskHistoryPoint,
    RiskOrderItem,
    SupplierConnectorResponse,
    SyncRunRequest,
    SyncRunResponse,
)
from app.services.query import dashboard_summary, parse_json_list
from app.services.risk import recommended_actions
from app.services.suppliers import SUPPORTED_SUPPLIERS, supplier_supported
from app.services.sync import run_sync


app = FastAPI(
    title="Build Sight MVP API",
    description="Construction material delay early warning and recovery hub.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory="/workspace/app/static"), name="static")
templates = Jinja2Templates(directory="/workspace/app/templates")


@app.on_event("startup")
def startup() -> None:
    init_db()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mask_secret(_: str) -> str:
    return f"secret://{uuid4()}"


def _latest_inventory_qty(db: Session, connector_id: str, sku: str, tenant_id: str) -> float:
    row = db.execute(
        select(SupplierInventorySnapshot)
        .where(
            and_(
                SupplierInventorySnapshot.connector_id == connector_id,
                SupplierInventorySnapshot.supplier_sku == sku,
                SupplierInventorySnapshot.tenant_id == tenant_id,
            )
        )
        .order_by(desc(SupplierInventorySnapshot.captured_at))
        .limit(1)
    ).scalar_one_or_none()
    return row.qty_available if row else 0.0


def _latest_risk_for_order(db: Session, order_line_id: str) -> RiskAssessment | None:
    return db.execute(
        select(RiskAssessment)
        .where(RiskAssessment.order_line_id == order_line_id)
        .order_by(desc(RiskAssessment.assessed_at))
        .limit(1)
    ).scalar_one_or_none()


def _risk_item(order: OrderLine, risk: RiskAssessment) -> RiskOrderItem:
    reasons = parse_json_list(risk.reason_codes_json)
    return RiskOrderItem(
        orderLineId=order.id,
        supplierOrderId=order.supplier_order_id,
        projectId=order.project_id,
        supplierSku=order.supplier_sku,
        materialName=order.material_name,
        etaDate=order.eta_date,
        status=risk.risk_status,
        riskScore=risk.risk_score,
        confidence=risk.confidence,
        reasonCodes=reasons,
        estimatedDelayDays=risk.estimated_delay_days,
        recommendedActions=recommended_actions(reasons),
        lastUpdatedAt=risk.assessed_at,
    )


def _alert_view(alert: Alert) -> AlertView:
    return AlertView(
        id=alert.id,
        severity=alert.severity,
        status=alert.status,
        message=alert.message,
        recommendations=parse_json_list(alert.recommendations_json),
        createdAt=alert.created_at,
        acknowledgedAt=alert.acknowledged_at,
        resolvedAt=alert.resolved_at,
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"supported_suppliers": SUPPORTED_SUPPLIERS},
    )


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta/suppliers")
def list_supported_suppliers() -> dict[str, list[str]]:
    return {"suppliers": SUPPORTED_SUPPLIERS}


@app.post("/api/integrations/suppliers", response_model=SupplierConnectorResponse, status_code=201)
def create_connector(
    payload: CreateSupplierConnectorRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> SupplierConnectorResponse:
    if not supplier_supported(payload.supplierName):
        raise HTTPException(status_code=400, detail="supplierName is not supported in MVP")

    existing = db.execute(
        select(SupplierConnector).where(
            and_(
                SupplierConnector.tenant_id == ctx.tenant_id,
                SupplierConnector.supplier_name == payload.supplierName,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Connector already exists for this supplier.")

    connector = SupplierConnector(
        id=str(uuid4()),
        tenant_id=ctx.tenant_id,
        supplier_name=payload.supplierName,
        auth_type=payload.authType,
        secret_ref=_mask_secret(payload.credentials.apiKey),
        status="pending_validation",
        poll_interval_minutes=payload.pollIntervalMinutes,
        created_at=_utcnow(),
    )
    db.add(connector)
    db.commit()
    db.refresh(connector)

    return SupplierConnectorResponse(
        id=connector.id,
        supplierName=connector.supplier_name,
        status=connector.status,
        pollIntervalMinutes=connector.poll_interval_minutes,
        createdAt=connector.created_at,
    )


@app.get("/api/integrations/suppliers")
def list_connectors(
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> dict[str, list[dict[str, str | int | None]]]:
    rows = db.execute(
        select(SupplierConnector)
        .where(SupplierConnector.tenant_id == ctx.tenant_id)
        .order_by(SupplierConnector.created_at.desc())
    ).scalars()
    items = [
        {
            "id": row.id,
            "supplierName": row.supplier_name,
            "status": row.status,
            "pollIntervalMinutes": row.poll_interval_minutes,
            "lastSyncAt": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "createdAt": row.created_at.isoformat(),
        }
        for row in rows
    ]
    return {"items": items}


@app.post("/api/sync/run", response_model=SyncRunResponse, status_code=202)
def run_sync_job(
    payload: SyncRunRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> SyncRunResponse:
    connector = db.execute(
        select(SupplierConnector).where(
            and_(SupplierConnector.id == payload.connectorId, SupplierConnector.tenant_id == ctx.tenant_id)
        )
    ).scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found.")

    if connector.last_sync_at and (_utcnow() - connector.last_sync_at) < timedelta(seconds=30):
        raise HTTPException(status_code=429, detail="Manual sync is rate-limited. Try again shortly.")

    metrics = run_sync(db, ctx, connector, payload.mode)
    return SyncRunResponse(
        jobId=str(metrics["job_id"]),
        status=str(metrics["status"]),
        processedOrders=int(metrics["processed_orders"]),
        processedInventoryRows=int(metrics["processed_inventory_rows"]),
        assessedOrders=int(metrics["assessed_orders"]),
        generatedAlerts=int(metrics["generated_alerts"]),
    )


@app.get("/api/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> DashboardSummaryResponse:
    summary = dashboard_summary(db, ctx.tenant_id)
    return DashboardSummaryResponse(
        syncHealth=str(summary["sync_health"]),
        lastSyncAt=summary["last_sync_at"],
        redCount=int(summary["red_count"]),
        yellowCount=int(summary["yellow_count"]),
        greenCount=int(summary["green_count"]),
        openAlerts=int(summary["open_alerts"]),
    )


@app.get("/api/orders/risk", response_model=PaginatedRiskOrders)
def list_risk_orders(
    status: str | None = Query(default=None, pattern="^(green|yellow|red)$"),
    projectId: str | None = Query(default=None),
    supplierId: str | None = Query(default=None),
    impactBefore: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> PaginatedRiskOrders:
    query = select(OrderLine).where(and_(OrderLine.tenant_id == ctx.tenant_id, OrderLine.status == "open"))
    if projectId:
        query = query.where(OrderLine.project_id == projectId)
    if supplierId:
        query = query.where(OrderLine.connector_id == supplierId)
    if impactBefore:
        query = query.where(OrderLine.eta_date <= impactBefore)

    orders = db.execute(query.order_by(OrderLine.eta_date.asc())).scalars().all()
    rows: list[RiskOrderItem] = []
    for order in orders:
        latest = _latest_risk_for_order(db, order.id)
        if latest is None:
            continue
        if status and latest.risk_status != status:
            continue
        rows.append(_risk_item(order, latest))

    severity_weight = {"red": 0, "yellow": 1, "green": 2}
    rows.sort(key=lambda r: (severity_weight.get(r.status, 3), r.etaDate))

    total = len(rows)
    start = (page - 1) * pageSize
    end = start + pageSize
    return PaginatedRiskOrders(items=rows[start:end], total=total, page=page, pageSize=pageSize)


@app.get("/api/orders/{order_id}", response_model=OrderRiskDetail)
def get_order_detail(
    order_id: str,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> OrderRiskDetail:
    order = db.execute(
        select(OrderLine).where(and_(OrderLine.id == order_id, OrderLine.tenant_id == ctx.tenant_id))
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")

    latest = _latest_risk_for_order(db, order.id)
    latest_item = _risk_item(order, latest) if latest else None

    history_rows = db.execute(
        select(RiskAssessment).where(RiskAssessment.order_line_id == order.id).order_by(RiskAssessment.assessed_at.desc())
    ).scalars()
    history = [
        RiskHistoryPoint(
            assessedAt=row.assessed_at,
            riskScore=row.risk_score,
            riskStatus=row.risk_status,
            confidence=row.confidence,
            reasonCodes=parse_json_list(row.reason_codes_json),
            estimatedDelayDays=row.estimated_delay_days,
        )
        for row in history_rows
    ]

    alert_rows = db.execute(
        select(Alert).where(and_(Alert.order_line_id == order.id, Alert.tenant_id == ctx.tenant_id)).order_by(Alert.created_at.desc())
    ).scalars()
    alerts = [_alert_view(alert) for alert in alert_rows]

    return OrderRiskDetail(
        orderLineId=order.id,
        supplierOrderId=order.supplier_order_id,
        projectId=order.project_id,
        supplierSku=order.supplier_sku,
        materialName=order.material_name,
        qtyOrdered=order.qty_ordered,
        qtyDelivered=order.qty_delivered,
        etaDate=order.eta_date,
        status=order.status,
        latestRisk=latest_item,
        riskHistory=history,
        alerts=alerts,
    )


@app.get("/api/alerts", response_model=ListAlertsResponse)
def list_alerts(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> ListAlertsResponse:
    query = select(Alert).where(Alert.tenant_id == ctx.tenant_id)
    if status:
        query = query.where(Alert.status == status)
    if severity:
        query = query.where(Alert.severity == severity)
    rows = db.execute(query.order_by(Alert.created_at.desc()).limit(200)).scalars().all()
    return ListAlertsResponse(items=[_alert_view(row) for row in rows], total=len(rows))


@app.post("/api/alerts/{alert_id}/feedback", response_model=AlertFeedbackResponse, status_code=201)
def submit_alert_feedback(
    alert_id: str,
    payload: AlertFeedbackRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> AlertFeedbackResponse:
    alert = db.execute(
        select(Alert).where(and_(Alert.id == alert_id, Alert.tenant_id == ctx.tenant_id))
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    feedback = AlertFeedback(
        id=str(uuid4()),
        tenant_id=ctx.tenant_id,
        alert_id=alert_id,
        user_id=ctx.user_id,
        disposition=payload.disposition,
        notes=payload.notes,
        created_at=_utcnow(),
    )
    db.add(feedback)
    db.commit()
    return AlertFeedbackResponse(
        id=feedback.id,
        alertId=feedback.alert_id,
        disposition=feedback.disposition,
        notes=feedback.notes,
        createdAt=feedback.created_at,
    )


@app.post("/api/alerts/{alert_id}/acknowledge", response_model=AlertActionResponse)
def acknowledge_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> AlertActionResponse:
    require_roles(ctx, "owner", "pm", "coordinator")
    alert = db.execute(
        select(Alert).where(and_(Alert.id == alert_id, Alert.tenant_id == ctx.tenant_id))
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    alert.status = "acknowledged"
    alert.acknowledged_at = _utcnow()
    db.commit()
    return AlertActionResponse(alertId=alert.id, status=alert.status, updatedAt=alert.acknowledged_at)


@app.post("/api/alerts/{alert_id}/resolve", response_model=AlertActionResponse)
def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> AlertActionResponse:
    require_roles(ctx, "owner", "pm")
    alert = db.execute(
        select(Alert).where(and_(Alert.id == alert_id, Alert.tenant_id == ctx.tenant_id))
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    alert.status = "resolved"
    alert.resolved_at = _utcnow()
    db.commit()
    return AlertActionResponse(alertId=alert.id, status=alert.status, updatedAt=alert.resolved_at)
