from __future__ import annotations

import json
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app import config, database, models
from app.deps import RequestContext, get_db, get_request_context
from app.routers.api import router as api_router
from app.seed import seed_demo_data

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app(seed_demo: bool = True) -> FastAPI:
    app = FastAPI(title="Build Sight MVP", version="0.1.0")
    app.include_router(api_router)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.on_event("startup")
    def startup() -> None:
        database.Base.metadata.create_all(bind=database.engine)
        if not seed_demo:
            return
        db = database.SessionLocal()
        try:
            seed_demo_data(db)
        finally:
            db.close()

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/dashboard")

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        db: Session = Depends(get_db),
        ctx: RequestContext = Depends(get_request_context),
    ):
        latest = (
            db.query(
                models.RiskAssessment.order_line_id.label("order_line_id"),
                func.max(models.RiskAssessment.assessed_at).label("assessed_at"),
            )
            .group_by(models.RiskAssessment.order_line_id)
            .subquery()
        )
        rows = (
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
            .order_by(models.RiskAssessment.risk_status.desc())
            .all()
        )
        counts = {"green": 0, "yellow": 0, "red": 0}
        table = []
        for order_line, risk in rows:
            counts[risk.risk_status] = counts.get(risk.risk_status, 0) + 1
            table.append(
                {
                    "id": order_line.id,
                    "supplier_order_id": order_line.supplier_order_id,
                    "supplier_sku": order_line.supplier_sku,
                    "status": risk.risk_status,
                    "risk_score": risk.risk_score,
                    "confidence": risk.confidence,
                    "impact_date": order_line.impact_date,
                    "reason_codes": ", ".join(json.loads(risk.reason_codes_json)),
                }
            )
        connectors = (
            db.query(models.SupplierConnector)
            .filter(models.SupplierConnector.tenant_id == ctx.tenant_id)
            .order_by(models.SupplierConnector.created_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "counts": counts,
                "rows": table,
                "connectors": connectors,
            },
        )

    @app.get("/alerts", response_class=HTMLResponse)
    def alerts_page(
        request: Request,
        db: Session = Depends(get_db),
        ctx: RequestContext = Depends(get_request_context),
    ):
        alerts = (
            db.query(models.Alert)
            .filter(models.Alert.tenant_id == ctx.tenant_id)
            .order_by(models.Alert.created_at.desc())
            .limit(100)
            .all()
        )
        return templates.TemplateResponse("alerts.html", {"request": request, "alerts": alerts})

    @app.get("/orders/{order_id}", response_class=HTMLResponse)
    def order_detail_page(
        order_id: str,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RequestContext = Depends(get_request_context),
    ):
        order_line = (
            db.query(models.OrderLine)
            .filter(models.OrderLine.id == order_id, models.OrderLine.tenant_id == ctx.tenant_id)
            .first()
        )
        if not order_line:
            return templates.TemplateResponse(
                "order_detail.html",
                {"request": request, "order": None, "risk_history": [], "alerts": []},
                status_code=404,
            )
        risks = (
            db.query(models.RiskAssessment)
            .filter(models.RiskAssessment.order_line_id == order_line.id)
            .order_by(models.RiskAssessment.assessed_at.desc())
            .all()
        )
        alerts = (
            db.query(models.Alert)
            .filter(models.Alert.order_line_id == order_line.id)
            .order_by(models.Alert.created_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            "order_detail.html",
            {"request": request, "order": order_line, "risk_history": risks, "alerts": alerts},
        )

    @app.get("/integrations", response_class=HTMLResponse)
    def integrations_page(
        request: Request,
        db: Session = Depends(get_db),
        ctx: RequestContext = Depends(get_request_context),
    ):
        connectors = (
            db.query(models.SupplierConnector)
            .filter(models.SupplierConnector.tenant_id == ctx.tenant_id)
            .order_by(models.SupplierConnector.created_at.desc())
            .all()
        )
        return templates.TemplateResponse("integrations.html", {"request": request, "connectors": connectors})

    @app.get("/settings/notifications", response_class=HTMLResponse)
    def notification_settings_page(
        request: Request,
        db: Session = Depends(get_db),
        ctx: RequestContext = Depends(get_request_context),
    ):
        user = (
            db.query(models.User)
            .filter(models.User.tenant_id == ctx.tenant_id, models.User.email == "owner@demo.local")
            .first()
        )
        prefs = "{}"
        if user:
            prefs = user.notification_preferences
        return templates.TemplateResponse(
            "settings_notifications.html",
            {"request": request, "notification_preferences": prefs},
        )

    return app


app = create_app(seed_demo=True)

