from __future__ import annotations


def _create_connector(client, headers):
    response = client.post(
        "/api/integrations/suppliers",
        headers=headers,
        json={
            "supplierName": "MetroLumber",
            "authType": "api_key",
            "credentials": {"apiKey": "demo-secret-key"},
            "pollIntervalMinutes": 1440,
        },
    )
    assert response.status_code == 201
    return response.json()


def _run_sync(client, headers, connector_id):
    response = client.post(
        "/api/sync/run",
        headers=headers,
        json={"connectorId": connector_id, "mode": "incremental"},
    )
    assert response.status_code == 202
    return response.json()


def test_create_connector_and_conflict(client, default_headers):
    first = _create_connector(client, default_headers)
    assert first["supplierName"] == "MetroLumber"
    assert first["status"] == "pending_validation"

    second = client.post(
        "/api/integrations/suppliers",
        headers=default_headers,
        json={
            "supplierName": "MetroLumber",
            "authType": "api_key",
            "credentials": {"apiKey": "demo-secret-key"},
            "pollIntervalMinutes": 1440,
        },
    )
    assert second.status_code == 409


def test_sync_generates_risk_orders_and_dashboard(client, default_headers):
    connector = _create_connector(client, default_headers)
    sync = _run_sync(client, default_headers, connector["id"])
    assert sync["processedOrders"] > 0
    assert sync["assessedOrders"] > 0

    orders = client.get("/api/orders/risk?pageSize=100", headers=default_headers)
    assert orders.status_code == 200
    payload = orders.json()
    assert payload["total"] > 0
    assert payload["items"][0]["status"] in {"green", "yellow", "red"}

    summary = client.get("/api/dashboard/summary", headers=default_headers)
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["syncHealth"] == "active"
    assert (summary_payload["redCount"] + summary_payload["yellowCount"] + summary_payload["greenCount"]) >= 1


def test_feedback_and_alert_resolution_permissions(client, default_headers):
    connector = _create_connector(client, default_headers)
    _run_sync(client, default_headers, connector["id"])

    alerts = client.get("/api/alerts", headers=default_headers)
    assert alerts.status_code == 200
    items = alerts.json()["items"]
    assert len(items) >= 1
    alert_id = items[0]["id"]

    invalid_feedback = client.post(
        f"/api/alerts/{alert_id}/feedback",
        headers=default_headers,
        json={"disposition": "bad-value", "notes": "test"},
    )
    assert invalid_feedback.status_code == 422

    valid_feedback = client.post(
        f"/api/alerts/{alert_id}/feedback",
        headers=default_headers,
        json={"disposition": "accurate", "notes": "This warning helped us resequence framing."},
    )
    assert valid_feedback.status_code == 201
    assert valid_feedback.json()["disposition"] == "accurate"

    coordinator_headers = {**default_headers, "x-user-role": "coordinator"}
    forbidden = client.post(f"/api/alerts/{alert_id}/resolve", headers=coordinator_headers)
    assert forbidden.status_code == 403

    resolved = client.post(f"/api/alerts/{alert_id}/resolve", headers=default_headers)
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
