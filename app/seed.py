from __future__ import annotations

from app import config, models
from app.services.sync import queue_sync_run, run_sync_job


def seed_demo_data(db) -> None:
    existing_orders = db.query(models.OrderLine).filter(models.OrderLine.tenant_id == config.DEFAULT_TENANT_ID).count()
    if existing_orders > 0:
        return

    user = (
        db.query(models.User)
        .filter(models.User.tenant_id == config.DEFAULT_TENANT_ID, models.User.email == "owner@demo.local")
        .first()
    )
    if not user:
        db.add(
            models.User(
                tenant_id=config.DEFAULT_TENANT_ID,
                email="owner@demo.local",
                role="owner",
                notification_preferences='{"email": true, "sms": false}',
            )
        )

    project = db.query(models.Project).filter(models.Project.tenant_id == config.DEFAULT_TENANT_ID).first()
    if not project:
        db.add(
            models.Project(
                tenant_id=config.DEFAULT_TENANT_ID,
                name="Riverside Duplex Build",
            )
        )
    db.commit()

    connector_names = ["MetroLumber", "BuildPro"]
    connectors: list[models.SupplierConnector] = []
    for supplier in connector_names:
        connector = (
            db.query(models.SupplierConnector)
            .filter(models.SupplierConnector.tenant_id == config.DEFAULT_TENANT_ID, models.SupplierConnector.supplier_name == supplier)
            .first()
        )
        if not connector:
            connector = models.SupplierConnector(
                tenant_id=config.DEFAULT_TENANT_ID,
                supplier_name=supplier,
                auth_type="api_key",
                secret_ref=f"secret://{config.DEFAULT_TENANT_ID}/{supplier.lower()}",
                status="pending_validation",
                poll_interval_minutes=1440,
            )
            db.add(connector)
            db.commit()
            db.refresh(connector)
        connectors.append(connector)

    for connector in connectors:
        run = queue_sync_run(db, connector.id, "incremental")
        run_sync_job(run.id)

