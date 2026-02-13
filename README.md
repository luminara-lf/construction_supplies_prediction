# Build Sight MVP — Construction Supplies Prediction

Build Sight is an MVP for proactive construction material delay detection.  
It ingests supplier order/inventory snapshots, scores open orders by delay risk, and generates actionable alerts.

## What is included

- FastAPI backend with SQLite persistence
- Explainable risk scoring engine (`green` / `yellow` / `red`)
- Supplier connector management
- On-demand sync pipeline (simulated for 5 distributors)
- Alert generation, acknowledgment/resolution, and quality feedback capture
- Lightweight dashboard UI
- Automated tests for risk logic and API workflows

## Quick start

### 1) Create environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run the app

```bash
uvicorn app.main:app --reload
```

Open: `http://127.0.0.1:8000`

### 3) Run tests

```bash
pytest -q
```

## API overview

- `POST /api/integrations/suppliers` — create supplier connector
- `GET /api/integrations/suppliers` — list connectors
- `POST /api/sync/run` — trigger sync + scoring + alert creation
- `GET /api/dashboard/summary` — risk and sync summary counts
- `GET /api/orders/risk` — list risk-scored open orders
- `GET /api/orders/{id}` — order-level risk history and alerts
- `GET /api/alerts` — list alerts
- `POST /api/alerts/{id}/acknowledge` — acknowledge alert
- `POST /api/alerts/{id}/resolve` — resolve alert (owner/pm)
- `POST /api/alerts/{id}/feedback` — submit alert quality feedback

### Simulated auth headers (MVP)

The MVP uses headers to simulate role + tenant isolation:

- `x-tenant-id` (default: `demo-tenant`)
- `x-user-id` (default: `demo-user`)
- `x-user-role` (`owner`, `pm`, `coordinator`, `readonly`)

## Notes

- Database file defaults to `/workspace/buildsight.db`.
- Override with `BUILD_SIGHT_DB_PATH` if needed.
- Implementation details and limitations are documented in `docs/MVP_IMPLEMENTATION.md`.