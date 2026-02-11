# Build Sight Feature Specifications

## 1. FEATURE OVERVIEW

**Feature Name**: Material Delay Early Warning & Recovery Hub (MVP)  
**Feature Category**: Core + Integration  
**Priority Level**: Must-Have  
**Target Release**: v0.1 Beta (2-4 week MVP), Sprint 1-3

**Problem Statement**  
Small construction firms rely on supplier promises, emails, and spreadsheets to track material availability and ETAs. They discover delays too late, after crews are already blocked on-site. This causes schedule slips, idle labor cost, client dissatisfaction, and margin erosion.

**Success Criteria**  
- 80%+ of pilot users connect at least 3 supplier accounts within first 7 days.  
- Delay risks are detected at least 72 hours before supplier-confirmed delay in 60%+ of impacted orders by week 6.  
- Reduce material-related idle crew hours by 20% across pilot accounts within 60 days.  
- Achieve weekly active usage by 70%+ of pilot users (10 target builders).

**User Impact**  
- **Small builders/GCs** get early warnings and can re-sequence work or source alternates before crews stall.  
- **Project managers** gain a single source of truth for open orders, status confidence, and next-best actions.  
- **Owners/operations leads** reduce avoidable delay costs and improve on-time project delivery.

---

## 2. USER PERSONAS & USE CASES

### Primary Persona: Small Builder Owner-Operator (Decision Maker)
- **Demographics**: 30-55, owner or lead PM at 3-25 employee firm, moderate tech-savviness, mobile-first in field.
- **Goals**:
  - Keep jobs moving without unplanned downtime.
  - Know which materials are likely late before crews are impacted.
  - Communicate confidently with clients about schedule risks.
- **Pain Points**:
  - Supplier ETA promises change without proactive notice.
  - Tracking data spread across texts, calls, and spreadsheets.
  - Idle labor and scheduling chaos when one key material slips.
- **Context**:
  - Checks status early morning before dispatching crews.
  - Reviews risk dashboard during weekly job progress planning.
  - Uses phone on job sites, desktop in evenings.

### Secondary Persona: Procurement/Operations Coordinator (Execution User)
- **Demographics**: 24-45, admin/ops role, detail-oriented, desktop-heavy workflow.
- **Goals**:
  - Track dozens of POs and delivery windows efficiently.
  - Trigger backup suppliers quickly when risk increases.
  - Keep PMs and owners updated without manual data wrangling.
- **Use Case**:
  - Performs deeper review of flagged orders.
  - Executes mitigation actions (alternate sourcing, supplier follow-up).
  - Maintains data quality and order status updates.

### Edge Cases
- Supplier API unavailable for >24 hours.
- Supplier inventory endpoint returns stale data timestamp.
- Builder has partial order delivery (split shipment).
- Item substitutions occur (different SKU but compatible product).
- Orders modified after placement (quantity/date changes).
- Same material sourced from multiple distributors simultaneously.
- Timezone mismatch between supplier systems and local jobsite.

---

## 3. DETAILED USER STORIES

**Epic**: Proactively prevent project delays by predicting material delivery risk and enabling fast recovery actions.

### Story 1: Core Functionality (Risk Detection)
- **As a** small builder owner  
- **I want** automatic risk scoring for each open material order  
- **So that** I can act before delays impact my crew schedule

**Acceptance Criteria**  
1)  
- **Given** a connected supplier account with open orders  
- **When** daily inventory and delivery history sync completes  
- **Then** each open order receives a risk status (Green/Yellow/Red) with confidence score and reason codes

2)  
- **Given** an order where available inventory is below ordered quantity and delivery history indicates slips  
- **When** the scoring engine runs  
- **Then** the order is marked Red and an alert is generated

3)  
- **Given** risk status changes from Green/Yellow to Red  
- **When** the change is detected  
- **Then** users receive in-app notification and optional SMS/email within 5 minutes

### Story 2: Error Handling & Recovery
- **As a** operations coordinator  
- **I want** clear sync error messaging and retry controls  
- **So that** I can restore tracking quickly without losing context

**Acceptance Criteria**  
- Error messages include supplier, timestamp, impacted orders, and next step.  
- Failed sync jobs auto-retry up to 3 times with exponential backoff.  
- Users can manually retry failed connectors.  
- System preserves last known status and labels it "stale" with last updated time.  
- No order data is deleted during transient integration failures.

### Story 3: User Experience & Actionability
- **As a** project manager  
- **I want** an intuitive dashboard with suggested mitigation actions  
- **So that** I can resolve risks quickly and keep project timelines intact

**Acceptance Criteria**  
- Dashboard default view prioritizes Red then Yellow items by project impact date.  
- Every Red order includes at least one suggested action (e.g., backup distributor, reorder split, schedule resequence).  
- Loading and empty states are explicit and informative.  
- Critical actions (e.g., mark resolved, trigger notification) require confirmation and show success feedback.  
- UI follows existing design system patterns and accessibility requirements.

### Story 4: Learning Loop (Prediction Improvement)
- **As a** product team/data model owner  
- **I want** users to confirm whether alerts were accurate  
- **So that** prediction quality improves over time

**Acceptance Criteria**  
- Users can label alert outcome: "Accurate", "False Positive", "Too Late".  
- Feedback is stored with order context and model version.  
- Weekly model quality report includes precision, recall, and lead-time delta.

---

## 4. FUNCTIONAL REQUIREMENTS

### Core Functionality

#### Function 1: Supplier Data Ingestion
- **Input**:
  - Supplier API credentials or secure file feed configuration.
  - Scheduled polling job (daily minimum; configurable up to every 2 hours).
- **Processing**:
  - Pull inventory snapshots, open order lines, shipment events, and ETA updates.
  - Normalize supplier-specific schemas to canonical internal model.
  - Deduplicate by external order line ID + timestamp + source hash.
- **Output**:
  - Normalized records stored with provenance metadata.
  - Sync run status (success/partial/failure) and ingestion metrics.
- **Validation**:
  - Required fields: supplier_id, sku, order_id, qty_ordered, qty_available OR eta, source_timestamp.
  - Reject malformed records with structured error logging.
  - Enforce timestamp sanity (not >24h in future, not null).

#### Function 2: Order-to-Inventory Matching & Risk Scoring
- **Input**:
  - Open customer orders and normalized supplier inventory/history data.
- **Processing**:
  - Match order lines by SKU (with substitution mapping table support).
  - Compute risk score using:
    - inventory coverage ratio,
    - historical late-delivery rate by supplier/SKU,
    - recent ETA volatility,
    - lead-time trend.
  - Convert score to status bands:
    - Green (<0.35),
    - Yellow (0.35-0.69),
    - Red (>=0.70).
- **Output**:
  - Risk status, score, confidence, reason codes, expected delay window.
- **Edge Cases**:
  - No historical data: fallback heuristic + low confidence label.
  - Partial deliveries: score remaining balance only.
  - Multiple suppliers for same SKU: present comparative risk options.

#### Function 3: Alerts & Recommended Mitigation
- **Input**:
  - Risk status transition events, user notification preferences.
- **Processing**:
  - Trigger alert rules on Yellow/Red transitions and confidence thresholds.
  - Generate action recommendations from alternatives database and prior outcomes.
- **Output**:
  - In-app alerts, email/SMS notifications, and dashboard action cards.
- **Validation**:
  - Avoid duplicate alerts within configurable cooldown window (default 12h).
  - Require actionable message format: risk reason + recommended next step + due date impact.

#### Function 4: User Feedback Capture
- **Input**:
  - User feedback on alert quality and final delivery outcomes.
- **Processing**:
  - Attach labels to prediction events.
  - Feed labeled examples into analytics/model training pipeline.
- **Output**:
  - Quality dashboards and retraining dataset.
- **Validation**:
  - Feedback entries must include disposition and timestamp.

### Business Rules
- **Rule 1**: Any order line with estimated impact within 7 days and Red status must trigger a high-priority alert.
- **Rule 2**: Supplier source data older than 48 hours is considered stale and cannot be used for "Green" final status without explicit warning.
- **Rule 3**: Only users with Owner/PM roles can mark a Red alert as resolved; coordinators can add notes and proposed actions.
- **Rule 4**: Risk scores must be explainable with at least one human-readable reason code.
- **Rule 5**: Manual user override of status expires in 24 hours unless reconfirmed.

### Integration Requirements
- **External APIs**:
  - Distributor inventory/order APIs (initially 5 metro distributors).
  - Optional SMS provider for urgent alerts.
  - Optional geocoding/routing for supplier proximity ranking.
- **Internal Systems**:
  - User/account management service.
  - Project/job scheduling module (if present) for impact-date context.
  - Notification preference center.
- **Data Synchronization**:
  - Incremental sync using supplier "updated_at" or cursor pagination.
  - Idempotent ingestion to prevent duplicate records.
  - Event bus publish on risk changes for downstream analytics and notifications.

---

## 5. NON-FUNCTIONAL REQUIREMENTS

### Performance Requirements
- **Response Time**:
  - Dashboard initial load: <=2.0s p95 for accounts with <=5,000 open lines.
  - Alert feed query: <=500ms p95.
- **Throughput**:
  - API tier supports 50 req/s sustained, 150 req/s burst.
- **Scalability**:
  - MVP targets 10-100 companies; architecture must scale to 1,000 companies without replatforming.
- **Resource Usage**:
  - Background risk scoring job should complete daily full run within 30 minutes for 100 companies.
  - Keep compute usage below budgeted cloud spend thresholds set by finance.

### Security Requirements
- **Authentication**:
  - Secure login via email/password + optional MFA.
  - API access via scoped tokens.
- **Authorization**:
  - RBAC roles: Owner, PM, Coordinator, Read-Only.
  - Enforce tenant-level data isolation (no cross-company data access).
- **Data Protection**:
  - Encrypt data at rest and in transit (TLS 1.2+).
  - Encrypt supplier credentials in secret manager; never store plaintext.
- **Audit Trail**:
  - Log critical actions: connector changes, alert acknowledgment/resolution, manual overrides, role changes.
  - Retain audit logs minimum 12 months.

### Usability Requirements
- **Accessibility**: WCAG 2.1 AA target (color contrast, keyboard support, ARIA labels).
- **Browser Support**: Last 2 versions of Chrome, Edge, Firefox; Safari 16+.
- **Mobile Responsiveness**: Fully usable on 390px+ width devices for monitoring and acknowledgments.
- **User Training**:
  - 10-minute onboarding checklist.
  - In-app tooltips for risk color logic and reason codes.
  - Help center article: "How risk scores are calculated."

---

## 6. TECHNICAL SPECIFICATIONS

### Frontend Requirements
- **Components**:
  - Risk Summary Cards (Green/Yellow/Red counts, trend).
  - Open Orders Risk Table (sortable/filterable by project, supplier, status).
  - Order Detail Drawer (timeline, reason codes, recommendations).
  - Alert Center (acknowledge/snooze/resolve).
  - Connector Health Panel (sync status, retry actions).
- **State Management**:
  - Server state via query cache library (stale-while-revalidate).
  - UI state for filters/sorting persisted per user.
  - Optimistic UI for acknowledgments with rollback on failure.
- **Routing**:
  - `/dashboard`
  - `/orders/:orderId`
  - `/alerts`
  - `/integrations`
  - `/settings/notifications`
- **Styling**:
  - Use design system tokens for status colors and spacing.
  - Status indicators must include both color and icon/text label.

### Backend Requirements

#### API Endpoints (MVP)

- **POST /api/integrations/suppliers**
  - **Purpose**: Create supplier connector.
  - **Request body**:
    ```json
    {
      "supplierName": "MetroLumber",
      "authType": "api_key",
      "credentials": { "apiKey": "string" },
      "pollIntervalMinutes": 1440
    }
    ```
  - **Response**:
    - `201 Created`: connector object with status `pending_validation`.
    - `400 Bad Request`: validation error details.
    - `409 Conflict`: connector already exists for tenant + supplier.
  - **Validation**:
    - `supplierName` required and must be supported.
    - `pollIntervalMinutes` min 120, max 1440 for MVP.

- **POST /api/sync/run**
  - **Purpose**: Trigger on-demand sync for specific connector.
  - **Request body**:
    ```json
    { "connectorId": "uuid", "mode": "incremental" }
    ```
  - **Response**:
    - `202 Accepted`: sync job queued.
    - `404 Not Found`: connector not found.
    - `429 Too Many Requests`: rate-limited manual sync.

- **GET /api/orders/risk**
  - **Purpose**: Retrieve risk-scored open orders.
  - **Parameters**:
    - Required: none.
    - Optional: `status`, `projectId`, `supplierId`, `impactBefore`, `page`, `pageSize`.
  - **Response**:
    ```json
    {
      "items": [
        {
          "orderLineId": "uuid",
          "status": "red",
          "riskScore": 0.84,
          "confidence": 0.77,
          "reasonCodes": ["LOW_STOCK", "ETA_VOLATILITY"],
          "estimatedDelayDays": 6
        }
      ],
      "total": 1
    }
    ```
  - **Error handling**:
    - `400`: invalid query filters.
    - `401/403`: auth/authz errors.
    - `500`: unexpected server failure with trace ID.

- **GET /api/orders/{id}**
  - **Purpose**: Retrieve order risk detail and timeline.
  - **Parameters**:
    - `id` (required path param UUID).
  - **Response**:
    - Order metadata, risk history, event timeline, and recommendations.
  - **Error handling**:
    - `404` for missing order.
    - `403` for cross-tenant access attempt.

- **POST /api/alerts/{id}/feedback**
  - **Purpose**: Capture user quality feedback.
  - **Request body**:
    ```json
    {
      "disposition": "accurate",
      "notes": "Shipment actually arrived 4 days late"
    }
    ```
  - **Validation**:
    - `disposition` in `accurate | false_positive | too_late`.
    - `notes` max 500 chars.

### Database Changes

#### New Tables
- `supplier_connectors`
  - `id`, `tenant_id`, `supplier_name`, `auth_type`, `secret_ref`, `status`, `last_sync_at`, `created_at`.
- `supplier_inventory_snapshots`
  - `id`, `connector_id`, `supplier_sku`, `qty_available`, `captured_at`, `raw_payload_ref`.
- `order_lines`
  - `id`, `tenant_id`, `project_id`, `supplier_order_id`, `supplier_sku`, `qty_ordered`, `qty_delivered`, `eta_date`, `status`.
- `risk_assessments`
  - `id`, `order_line_id`, `model_version`, `risk_score`, `risk_status`, `confidence`, `reason_codes_json`, `estimated_delay_days`, `assessed_at`.
- `alerts`
  - `id`, `tenant_id`, `order_line_id`, `severity`, `status`, `message`, `created_at`, `acknowledged_at`, `resolved_at`.
- `alert_feedback`
  - `id`, `alert_id`, `user_id`, `disposition`, `notes`, `created_at`.

#### Schema Updates
- Add `role` and `notification_preferences` fields to existing `users` table (if absent).
- Add `project_target_dates` to `projects` table for impact calculations.

#### Indexes
- Composite: `risk_assessments(order_line_id, assessed_at desc)`.
- Composite: `order_lines(tenant_id, status, eta_date)`.
- Composite: `alerts(tenant_id, severity, status, created_at desc)`.
- Unique: `supplier_connectors(tenant_id, supplier_name)`.

#### Migrations
- Use forward-only SQL migrations with rollback scripts for critical tables.
- Backfill strategy:
  - Seed `order_lines` from existing imported orders.
  - Generate initial baseline `risk_assessments` with model version `heuristic_v1`.
- Validate row counts and null constraints post-migration before enabling live scoring.

---

## 7. USER INTERFACE SPECIFICATIONS

**Wireframes/Mockups**  
- Figma file: `Build Sight - Delay Intelligence MVP` (to be created).
- Required screens:
  - Dashboard
  - Alerts list
  - Order detail
  - Integrations setup
  - Notification settings

### Layout Requirements
- **Page/Screen Structure**:
  - Top summary ribbon (risk counts + sync health).
  - Main content area with filters + risk table.
  - Right-side detail panel on row selection.
- **Navigation**:
  - Left nav: Dashboard, Orders, Alerts, Integrations, Settings.
  - Persistent breadcrumb in detail views.
- **Information Hierarchy**:
  - Priority: impacted date + risk status + recommended action.
  - Secondary: supplier details, confidence, historical trend.

### Interactive Elements
- **Buttons**:
  - Primary: "Review Alert", "Run Sync", "Resolve Risk".
  - Secondary: "Snooze", "View Timeline", "Retry Connector".
- **Forms**:
  - Supplier connector setup with inline validation and test connection.
  - Notification preferences with channel toggles and quiet hours.
- **Feedback**:
  - Success toast for action completion.
  - Error banners with retry CTA and trace ID.
- **Loading States**:
  - Skeleton rows for risk table.
  - Spinner + status text for on-demand sync.
  - Last-updated timestamp always visible.

### Responsive Design
- **Desktop**:
  - 3-column dashboard layout with side detail panel.
- **Tablet**:
  - Collapse detail panel into slide-over drawer.
- **Mobile**:
  - Single-column cards; filters in bottom sheet.
  - Focus on alert triage and acknowledgments over deep analytics.

---

## 8. TESTING REQUIREMENTS

### Unit Tests
- Risk scoring function correctness across threshold boundaries.
- Order/inventory matching logic including substitutions and partial deliveries.
- API input validation schema tests.
- Frontend component states (loading, empty, error, success).
- Notification deduplication and cooldown logic.

### Integration Tests
- End-to-end connector sync flow with mocked supplier APIs.
- Data normalization and idempotent ingestion verification.
- Risk event generation -> alert creation pipeline.
- RBAC enforcement on alert resolution and connector management.
- Cross-browser UI smoke tests for dashboard and alert workflows.

### User Acceptance Tests
- **Scenario 1: Early Warning Success Path**
  1. Connect supplier.
  2. Import open orders.
  3. System marks key line Red.
  4. User receives alert and views recommendation.
  5. User logs mitigation action.
  6. Project schedule adjusts before crew downtime.

- **Scenario 2: Integration Failure Recovery**
  1. Supplier API times out.
  2. Connector status becomes degraded.
  3. User sees clear error and retries.
  4. Sync recovers; stale status clears.

- **Scenario 3: Edge Case Validation (Partial Delivery + Substitution)**
  1. Order partially delivered.
  2. Remaining quantity mapped to substitute SKU.
  3. Risk recalculates only on remaining balance.
  4. Alert severity updates correctly.

### Performance Tests
- Load test: 10k open lines across 100 tenants with p95 query thresholds.
- Stress test: burst manual sync requests and queue durability.
- Security tests:
  - Tenant isolation penetration checks.
  - Injection and auth bypass attempts.
  - Secrets exposure scanning.

### Quality Gates (Release Exit Criteria)
- 95%+ pass rate on critical automated tests.
- 0 unresolved P1/P2 defects.
- No high-severity security findings.
- Pilot readiness review sign-off by Product + Engineering + Customer Success.

---

## 9. IMPLEMENTATION PLAN

### Development Phases

#### Phase 1: Core Data & Scoring (6-8 days)
- Build supplier connector framework and ingestion pipelines.
- Implement canonical data model and storage.
- Deliver initial heuristic risk scoring engine.
- Ship internal-only API endpoints for risk retrieval.

#### Phase 2: MVP UI & Alerts (5-7 days)
- Build dashboard, orders table, and alert center.
- Implement notification delivery (in-app + email; SMS optional toggle).
- Add connector health panel and retry workflows.
- Add basic recommendation engine (rule-based alternates).

#### Phase 3: Hardening, Testing, Pilot Prep (4-6 days)
- End-to-end integration and performance testing.
- Improve error handling and user feedback states.
- Add analytics instrumentation and model feedback capture.
- Prepare onboarding docs and pilot runbook.

### Dependencies
- **Blocking Dependencies**:
  - Supplier API credentials/access agreements for first 5 distributors.
  - Finalized data mapping for each distributor.
  - Decision on authentication provider.
- **Parallel Work**:
  - UI design and backend API can proceed concurrently after schema lock.
  - Test automation can begin once endpoint contracts are stable.
- **External Dependencies**:
  - SMS/email provider setup.
  - Hosting/monitoring stack provisioning.

### Risk Assessment
- **Technical Risks**:
  - Inconsistent supplier data formats and missing fields.
  - False positives reducing user trust.
  - Rate limits or instability in distributor APIs.
- **Timeline Risks**:
  - Delays in supplier credential approvals.
  - Scope creep from advanced model features too early.
- **Mitigation Strategies**:
  - Start with robust heuristic baseline and explainable reason codes.
  - Build per-supplier adapter abstraction to isolate schema variance.
  - Feature-flag advanced prediction logic.
  - Keep manual override and feedback loop to preserve user control.

### Implementation Guidelines
- Prioritize explainability over model complexity in MVP.
- Keep architecture modular: connectors, scoring, alerts, and UI should evolve independently.
- Use feature flags for risky capabilities (SMS alerts, auto-recommendations).
- Instrument everything early (sync latency, scoring drift, alert action rates).
- Preserve human-in-the-loop controls to support trust and adoption.

---

## 10. SUCCESS METRICS & MONITORING

### Feature Adoption Metrics
- Number of connected suppliers per account (target: >=3 in first week).
- Weekly active users per account (target: >=70% of invited users).
- Alert acknowledgment rate (target: >=85% within 24 hours).
- Time to complete risk triage workflow (target: median <5 minutes).

### Technical Metrics
- Risk scoring batch completion time.
- API p95 response by endpoint.
- Sync success/failure rate by supplier.
- Alert delivery latency and failure rate.
- Data freshness distribution (age of last successful sync).

### Business Impact Metrics
- Reduction in material-related schedule slips per project.
- Reduction in idle crew hours attributable to delayed materials.
- Pilot retention/churn at 30/60/90 days.
- NPS or CSAT among pilot builders.
- Support ticket volume related to delivery surprises.

### Monitoring Setup
- **Analytics Tracking**:
  - Instrument events: connector_created, sync_failed, risk_status_changed, alert_acknowledged, alert_resolved, feedback_submitted.
- **Error Logging & Alerting**:
  - Centralized logs with trace IDs.
  - Pager alerts for repeated sync failures, queue backlog, API error spikes.
- **Performance Monitoring**:
  - APM dashboards for endpoint latency and background jobs.
  - Database query performance alerts for risk and alerts queries.
- **User Feedback Collection**:
  - In-product feedback prompt after alert resolution.
  - Bi-weekly pilot interviews with structured rubric.

### KPI Targets for First 90 Days (Pilot)
- >=20% reduction in material-related idle time across participating builders.
- >=60% precision on Red alerts with continuous improvement trend.
- >=50% of Red alerts acted on within 12 hours.
- >=40% of pilot accounts convert to paid plans.

---

## Product Strategy Alignment

This specification is aligned to Build Sight's go-to-market strategy:
- Starts with a narrow, high-pain workflow (material delay visibility) for small builders.
- Leverages available distributor inventory data rather than requiring full ERP integrations on day one.
- Delivers immediate operational ROI (fewer crew delays), supporting price points from $200-$1,000/month.
- Creates defensibility through accumulated order-outcome data and feedback-driven prediction quality improvements.
