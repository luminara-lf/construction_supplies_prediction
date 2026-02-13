# construction_supplies_prediction

Build Sight MVP implementation for:

> Material Delay Early Warning & Recovery Hub

This repository now contains a working MVP product with:

- FastAPI backend for supplier connectors, sync, risk scoring, alerts, and feedback.
- SQLite persistence with canonical tables matching the product specification.
- Heuristic risk engine with explainable reason codes and stale-data guardrails.
- Alert generation with dedup cooldown and role-aware alert resolution.
- Minimal web UI routes:
  - `/dashboard`
  - `/orders/{orderId}`
  - `/alerts`
  - `/integrations`
  - `/settings/notifications`
- Automated tests for scoring boundaries, API validation, sync flow, and feedback/RBAC.

## Quickstart

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Run application

```bash
uvicorn app.main:app --reload --port 8000
```

Open:

- UI: `http://localhost:8000/dashboard`
- API docs: `http://localhost:8000/docs`

## Key API endpoints (MVP)

- `POST /api/integrations/suppliers`
- `POST /api/sync/run`
- `GET /api/orders/risk`
- `GET /api/orders/{id}`
- `POST /api/alerts/{id}/feedback`

Additional helper endpoints:

- `GET /api/integrations/suppliers`
- `GET /api/alerts`
- `POST /api/alerts/{id}/resolve`
- `POST /api/integrations/{connector_id}/retry`

## Running tests

```bash
pytest
```

## Notes

- Data ingestion currently uses deterministic mocked supplier payloads (`MetroLumber`, `BuildPro`) for repeatable MVP behavior.
- Sync retries are implemented with exponential backoff (up to 3 attempts).
- Risk scoring follows Green/Yellow/Red thresholds and enforces stale-data warnings for source data older than 48 hours.