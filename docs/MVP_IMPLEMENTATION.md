# Build Sight MVP Implementation Notes

This repository now includes an end-to-end MVP aligned with the provided feature specification for:

- Supplier connector setup
- Daily/on-demand sync workflow
- Risk scoring for open orders (Green/Yellow/Red)
- Alert generation and feedback capture
- Dashboard and alert visibility

## Implemented modules

- `app/main.py`: FastAPI routes + dashboard page
- `app/models.py`: SQLite data model for connectors, orders, inventory, risk, alerts, feedback
- `app/services/suppliers.py`: supplier adapter simulation for five initial distributors
- `app/services/risk.py`: explainable heuristic scoring engine
- `app/services/sync.py`: sync ingestion + risk assessment + alert generation
- `app/static/*` and `app/templates/index.html`: lightweight UI
- `tests/*`: API and scoring tests

## Current MVP tradeoffs

- Supplier integrations are deterministic mocks for development and pilot simulation.
- Authentication uses request headers for role/tenant simulation.
- Alert channels are currently in-app/API (email/SMS can be plugged in next).
- Scoring uses heuristics (`heuristic_v1`) instead of trained ML.

## Next recommended increments

1. Replace simulated supplier adapters with production API connectors.
2. Add background job queue for async sync and scoring.
3. Add full auth + tenant provisioning flow.
4. Add migration framework and model version management.
5. Add analytics dashboards and proactive notification channels.
