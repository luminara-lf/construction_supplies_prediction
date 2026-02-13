from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.deps import RequestContext, get_db, get_request_context
from app.services.recommendations import recommendations_for_reasons
from app.services.sync import queue_sync_run, run_sync_job

router = APIRouter(prefix="/api", tags=["api"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _trace_id() -> str:
    return str(uuid.uuid4())


@router.post(
    "/integrations/suppliers",
    response_model=schemas.ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_connector(
    payload: schemas.ConnectorCreateRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
):
    if payload.supplier_name not in config.SUPPORTED_SUPPLIERS:
        raise HTTPException(status_code=400, detail="supplierName is not supported")
    if payload.auth_type != "api_key":
        raise HTTPException(status_code=400, detail="authType must be api_key for MVP")
    if not payload.credentials.get("apiKey"):
        raise HTTPException(status_code=400, detail="credentials.apiKey is required")

    connector = models.SupplierConnector(
        tenant_id=ctx.tenant_id,
        supplier_name=payload.supplier_name,
        auth_type=payload.auth_type,
        secret_ref=f"secret://{ctx.tenant_id}/connectors/{uuid.uuid4()}",
        status="pending_validation",
        poll_interval_minutes=payload.poll_interval_minutes,
    )
    db.add(connector)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="connector already exists for tenant + supplier") from None
    db.refresh(connector)
    return schemas.ConnectorResponse.model_validate(
        {
            "id": connector.id,
            "tenantId": connector.tenant_id,
            "supplierName": connector.supplier_name,
            "authType": connector.auth_type,
            "status": connector.status,
            "pollIntervalMinutes": connector.poll_interval_minutes,
            "lastSyncAt": connector.last_sync_at,
            "createdAt": connector.created_at,
        }
    )


@router.get("/integrations/suppliers", response_model=list[schemas.ConnectorResponse])
def list_supplier_connectors(
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
):
    connectors = (
        db.query(models.SupplierConnector)
        .filter(models.SupplierConnector.tenant_id == ctx.tenant_id)
        .order_by(models.SupplierConnector.created_at.desc())
        .all()
    )
    return [
        schemas.ConnectorResponse.model_validate(
            {
                "id": row.id,
                "tenantId": row.tenant_id,
                "supplierName": row.supplier_name,
                "authType": row.auth_type,
                "status": row.status,
                "pollIntervalMinutes": row.poll_interval_minutes,
                "lastSyncAt": row.last_sync_at,
                "createdAt": row.created_at,
            }
        )
        for row in connectors
    ]


@router.post("/sync/run", response_model=schemas.SyncRunResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_sync_run(
    payload: schemas.SyncRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
):
    connector = (
        db.query(models.SupplierConnector)
        .filter(models.SupplierConnector.id == payload.connector_id, models.SupplierConnector.tenant_id == ctx.tenant_id)
        .first()
    )
    if not connector:
        raise HTTPException(status_code=404, detail="connector not found")

    one_minute_ago = utcnow() - timedelta(seconds=60)
    recent = (
        db.query(models.SyncRun)
        .filter(models.SyncRun.connector_id == connector.id, models.SyncRun.started_at >= one_minute_ago)
        .order_by(models.SyncRun.started_at.desc())
        .first()
    )
    if recent:
        raise HTTPException(status_code=429, detail="manual sync is rate limited")

    run = queue_sync_run(db, connector.id, payload.mode)
    background_tasks.add_task(run_sync_job, run.id)
    return schemas.SyncRunResponse.model_validate(
        {
            "id": run.id,
            "status": run.status,
            "mode": run.mode,
            "attempts": run.attempts,
            "startedAt": run.started_at,
        }
    )


@router.post("/integrations/{connector_id}/retry", response_model=schemas.SyncRunResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_connector_sync(
    connector_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
):
    connector = (
        db.query(models.SupplierConnector)
        .filter(models.SupplierConnector.id == connector_id, models.SupplierConnector.tenant_id == ctx.tenant_id)
        .first()
    )
    if not connector:
        raise HTTPException(status_code=404, detail="connector not found")
    run = queue_sync_run(db, connector.id, "incremental")
    background_tasks.add_task(run_sync_job, run.id)
    return schemas.SyncRunResponse.model_validate(
        {
            "id": run.id,
            "status": run.status,
            "mode": run.mode,
            "attempts": run.attempts,
            "startedAt": run.started_at,
        }
    )


def _latest_assessment_subquery(db: Session):
    return (
        db.query(
            models.RiskAssessment.order_line_id.label("order_line_id"),
            func.max(models.RiskAssessment.assessed_at).label("assessed_at"),
        )
        .group_by(models.RiskAssessment.order_line_id)
        .subquery()
    )


@router.get("/orders/risk", response_model=schemas.OrderRiskListResponse)
def list_order_risk(
    status_filter: str | None = Query(default=None, alias="status"),
    project_id: str | None = Query(default=None, alias="projectId"),
    supplier_id: str | None = Query(default=None, alias="supplierId"),
    impact_before: date | None = Query(default=None, alias="impactBefore"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, alias="pageSize", ge=1, le=200),
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
):
    if status_filter and status_filter not in {"green", "yellow", "red"}:
        raise HTTPException(status_code=400, detail="invalid status filter")

    latest = _latest_assessment_subquery(db)
    query = (
        db.query(models.OrderLine, models.RiskAssessment)
        .join(latest, models.OrderLine.id == latest.c.order_line_id)
        .join(
            models.RiskAssessment,
            and_(
                models.RiskAssessment.order_line_id == latest.c.order_line_id,
                models.RiskAssessment.assessed_at == latest.c.assessed_at,
            ),
        )
        .filter(models.OrderLine.tenant_id == ctx.tenant_id)
    )

    if status_filter:
        query = query.filter(models.RiskAssessment.risk_status == status_filter)
    if project_id:
        query = query.filter(models.OrderLine.project_id == project_id)
    if supplier_id:
        query = query.filter(models.OrderLine.supplier_id == supplier_id)
    if impact_before:
        query = query.filter(models.OrderLine.impact_date <= impact_before)

    status_rank = case(
        (models.RiskAssessment.risk_status == "red", 0),
        (models.RiskAssessment.risk_status == "yellow", 1),
        else_=2,
    )
    total = query.count()
    rows = (
        query.order_by(status_rank, models.OrderLine.impact_date.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for order_line, assessment in rows:
        reason_codes = json.loads(assessment.reason_codes_json)
        items.append(
            schemas.OrderRiskItem.model_validate(
                {
                    "orderLineId": order_line.id,
                    "projectId": order_line.project_id,
                    "supplierId": order_line.supplier_id,
                    "status": assessment.risk_status,
                    "riskScore": assessment.risk_score,
                    "confidence": assessment.confidence,
                    "reasonCodes": reason_codes,
                    "estimatedDelayDays": assessment.estimated_delay_days,
                    "impactDate": order_line.impact_date,
                    "stale": assessment.stale_data,
                    "lastUpdated": assessment.assessed_at,
                }
            )
        )
    return schemas.OrderRiskListResponse(items=items, total=total)


@router.get("/orders/{order_id}", response_model=schemas.OrderDetailResponse)
def get_order_detail(
    order_id: str,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
):
    order_line = db.query(models.OrderLine).filter(models.OrderLine.id == order_id).first()
    if not order_line:
        raise HTTPException(status_code=404, detail="order not found")
    if order_line.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="cross-tenant access denied")

    assessments = (
        db.query(models.RiskAssessment)
        .filter(models.RiskAssessment.order_line_id == order_line.id)
        .order_by(models.RiskAssessment.assessed_at.desc())
        .all()
    )
    if not assessments:
        trace_id = _trace_id()
        raise HTTPException(status_code=500, detail=f"risk assessment missing; trace_id={trace_id}")

    latest = assessments[0]
    reason_codes = json.loads(latest.reason_codes_json)
    recommendations = recommendations_for_reasons(order_line, reason_codes)

    alerts = (
        db.query(models.Alert)
        .filter(models.Alert.order_line_id == order_line.id)
        .order_by(models.Alert.created_at.desc())
        .all()
    )
    timeline = [
        {
            "eventType": "risk_assessed",
            "timestamp": item.assessed_at,
            "detail": f"{item.risk_status.upper()} ({item.risk_score:.2f})",
        }
        for item in assessments
    ]
    timeline.extend(
        {
            "eventType": "alert_created",
            "timestamp": alert.created_at,
            "detail": alert.message,
        }
        for alert in alerts
    )
    timeline = sorted(timeline, key=lambda x: x["timestamp"], reverse=True)

    return schemas.OrderDetailResponse.model_validate(
        {
            "orderLineId": order_line.id,
            "supplierOrderId": order_line.supplier_order_id,
            "supplierSku": order_line.supplier_sku,
            "qtyOrdered": order_line.qty_ordered,
            "qtyDelivered": order_line.qty_delivered,
            "etaDate": order_line.eta_date,
            "impactDate": order_line.impact_date,
            "currentStatus": latest.risk_status,
            "currentScore": latest.risk_score,
            "confidence": latest.confidence,
            "reasonCodes": reason_codes,
            "estimatedDelayDays": latest.estimated_delay_days,
            "riskHistory": [
                {
                    "assessedAt": item.assessed_at.isoformat(),
                    "riskStatus": item.risk_status,
                    "riskScore": item.risk_score,
                    "confidence": item.confidence,
                    "reasonCodes": json.loads(item.reason_codes_json),
                }
                for item in assessments
            ],
            "timeline": timeline[:50],
            "recommendations": recommendations,
        }
    )


@router.get("/alerts")
def list_alerts(
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
):
    alerts = (
        db.query(models.Alert)
        .filter(models.Alert.tenant_id == ctx.tenant_id)
        .order_by(models.Alert.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": alert.id,
            "orderLineId": alert.order_line_id,
            "severity": alert.severity,
            "status": alert.status,
            "message": alert.message,
            "createdAt": alert.created_at,
            "acknowledgedAt": alert.acknowledged_at,
            "resolvedAt": alert.resolved_at,
        }
        for alert in alerts
    ]


@router.post("/alerts/{alert_id}/feedback", response_model=schemas.AlertFeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_alert_feedback(
    alert_id: str,
    payload: schemas.AlertFeedbackRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
):
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    if alert.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="cross-tenant access denied")

    latest = (
        db.query(models.RiskAssessment)
        .join(models.OrderLine, models.RiskAssessment.order_line_id == models.OrderLine.id)
        .filter(models.OrderLine.id == alert.order_line_id)
        .order_by(models.RiskAssessment.assessed_at.desc())
        .first()
    )
    model_version = latest.model_version if latest else "heuristic_v1"
    feedback = models.AlertFeedback(
        alert_id=alert.id,
        user_id=ctx.user_id,
        disposition=payload.disposition,
        notes=payload.notes,
        model_version=model_version,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return schemas.AlertFeedbackResponse.model_validate(
        {
            "id": feedback.id,
            "alertId": feedback.alert_id,
            "userId": feedback.user_id,
            "disposition": feedback.disposition,
            "notes": feedback.notes,
            "createdAt": feedback.created_at,
        }
    )


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    payload: schemas.ResolveAlertRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
):
    if ctx.role not in {"owner", "pm"}:
        raise HTTPException(status_code=403, detail="only owner/pm can resolve red alerts")

    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    if alert.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="cross-tenant access denied")

    alert.status = "resolved"
    alert.resolved_at = utcnow()
    db.commit()
    return {
        "id": alert.id,
        "status": alert.status,
        "resolvedAt": alert.resolved_at,
        "resolutionNote": payload.resolution_note,
    }

