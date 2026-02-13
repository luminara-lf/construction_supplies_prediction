from __future__ import annotations

import time


def _create_connector(client, supplier_name: str = "BuildPro") -> str:
    response = client.post(
        "/api/integrations/suppliers",
        json={
            "supplierName": supplier_name,
            "authType": "api_key",
            "credentials": {"apiKey": "test-key"},
            "pollIntervalMinutes": 1440,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _run_sync(client, connector_id: str) -> None:
    response = client.post("/api/sync/run", json={"connectorId": connector_id, "mode": "incremental"})
    assert response.status_code == 202


def test_create_connector_validation(client):
    response = client.post(
        "/api/integrations/suppliers",
        json={
            "supplierName": "NotRealSupplier",
            "authType": "api_key",
            "credentials": {"apiKey": "test-key"},
            "pollIntervalMinutes": 1440,
        },
    )
    assert response.status_code == 400


def test_sync_generates_risk_rows_and_alerts(client):
    connector_id = _create_connector(client, "BuildPro")
    _run_sync(client, connector_id)

    for _ in range(8):
        risks = client.get("/api/orders/risk")
        assert risks.status_code == 200
        if risks.json()["total"] > 0:
            break
        time.sleep(0.1)
    assert risks.json()["total"] > 0
    item = risks.json()["items"][0]
    assert "status" in item
    assert "reasonCodes" in item

    alerts = client.get("/api/alerts")
    assert alerts.status_code == 200
    assert len(alerts.json()) > 0


def test_manual_sync_rate_limit(client):
    connector_id = _create_connector(client, "MetroLumber")
    first = client.post("/api/sync/run", json={"connectorId": connector_id, "mode": "incremental"})
    second = client.post("/api/sync/run", json={"connectorId": connector_id, "mode": "incremental"})
    assert first.status_code == 202
    assert second.status_code == 429


def test_alert_feedback_validation_and_create(client):
    connector_id = _create_connector(client, "BuildPro")
    _run_sync(client, connector_id)
    alerts = client.get("/api/alerts").json()
    alert_id = alerts[0]["id"]

    too_long = "x" * 501
    invalid = client.post(f"/api/alerts/{alert_id}/feedback", json={"disposition": "accurate", "notes": too_long})
    assert invalid.status_code == 422

    valid = client.post(
        f"/api/alerts/{alert_id}/feedback",
        json={"disposition": "accurate", "notes": "Shipment actually arrived late"},
    )
    assert valid.status_code == 201
    assert valid.json()["disposition"] == "accurate"


def test_alert_resolve_rbac(client):
    connector_id = _create_connector(client, "BuildPro")
    _run_sync(client, connector_id)
    alert_id = client.get("/api/alerts").json()[0]["id"]

    forbidden = client.post(
        f"/api/alerts/{alert_id}/resolve",
        json={"resolutionNote": "done"},
        headers={"x-user-role": "coordinator"},
    )
    assert forbidden.status_code == 403

    allowed = client.post(
        f"/api/alerts/{alert_id}/resolve",
        json={"resolutionNote": "done"},
        headers={"x-user-role": "owner"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "resolved"

