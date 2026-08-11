# Final Retail Features Implementation Plan

> **For agentic workers:** Execute inline, task by task, with red-green-refactor. Do not use subagents in this workspace.

**Goal:** Implement secure, event-driven retail features that close Task 4 gaps without deploying or redesigning SmartRetailX.

**Architecture:** Product Service owns promotions and Product writes. Order Service builds immutable Decimal price snapshots from its restricted read model, and owns fulfilment/cancellation. Inventory owns reservations/releases in Aurora. The existing outbox, EventBridge and WebSocket pieces carry new events.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, boto3, DynamoDB, Aurora PostgreSQL/Alembic, React/Vite/TypeScript/Vitest, Terraform.

## Global Constraints

- Do not run Terraform apply/destroy/import, mutate AWS, deploy, commit, push, delete screenshots, or change backend state.
- Preserve existing user-owned dirty changes and patch only approved feature surfaces.
- New public APIs are `/v1/*`, JWT-protected and backend-authorized.
- Money uses `Decimal.quantize(Decimal("0.01"), ROUND_HALF_UP)`; browser values are never authoritative.
- Commands go to SQS, durable Order-domain events go to EventBridge through the existing outbox, and fan-out remains SNS.
- Each test below is written and observed failing before its production implementation.

### Task 1: Strict order request and pricing snapshots

**Files:** `services/order-service/app/models.py`, `services/order-service/app/main.py`, `services/order-service/app/services.py`, `services/order-service/tests/test_orders.py`.

**Produces:** `OrderLineRequest(productId, quantity)`, immutable `OrderItem` price snapshot fields, `Order.subtotal`, `Order.discountTotal`, and a 422 for supplied client price fields.

- [ ] Write failing API tests: a request containing `unitPrice` returns 422; a valid ID/quantity request returns decimal snapshots; a legacy stored row remains readable.
- [ ] Run `pytest services/order-service/tests/test_orders.py -q` and verify the new tests fail because the schema still accepts `unitPrice`.
- [ ] Add `ConfigDict(extra="forbid")` request models and backward-compatible snapshot mapping using `unitPrice` only when reading an existing persisted row.
- [ ] Re-run the focused tests and then the full Order Service test suite.

### Task 2: Product/promotion read model and price calculation

**Files:** create `services/common/srx_common/pricing.py`; modify `services/order-service/app/pricing.py`, `services/order-service/app/config.py`, Order tests; modify `services/product-service/app/models.py`, `services/product-service/app/services.py`, Product tests.

**Produces:** `calculate_effective_price(base_price, promotions, now)`, `PricingCatalog.quote(lines, now)`, and product responses containing `basePrice`, `effectivePrice`, and promotion metadata.

- [ ] Write failing unit tests for percentage discount, inclusive start/exclusive end boundary, disabled promotion, tie-breaking, and `19.995 -> 20.00` rounding.
- [ ] Run the pricing tests and verify imports/functions are absent.
- [ ] Implement the shared pure Decimal calculator, narrow DDB pricing repository and Pydantic quote models; reject unknown/inactive products.
- [ ] Run focused pricing/Product/Order tests, then relevant existing tests.

### Task 3: Promotion CRUD, schedule reconciliation and safe price events

**Files:** Product Service main/config/repository/tests; `infra/data.tf`, `infra/security.tf`, `infra/compute.tf`, `infra/pipes.tf`, `services/ws-push-lambda/handler.py` and tests; `localstack-init/01-setup.sh`.

**Produces:** Admin promotion create/edit/enable-disable, native-stream `promotion.price-refresh`, scheduled state reconciliation, and the public `catalogue.price-refresh` WebSocket refetch signal.

- [ ] Write failing tests for admin-only CRUD, scheduled activation/expiry, non-sensitive event payload, public delivery to catalogue connections, and private-order isolation.
- [ ] Run the focused tests and verify failures represent missing routes/event branches.
- [ ] Implement promotion storage and route authorization, a 15-second deterministic reconciliation hook, and the dual public/private WebSocket event parser. Add only necessary Terraform table, roles, rules, targets, and LocalStack table.
- [ ] Run focused tests, EventEnvelope tests, WebSocket Lambda tests, Product tests and Terraform static formatting/validation.

### Task 4: Fulfilment state machine and durable delivery events

**Files:** Order models/events/services/main/tests; Order-outbox-publisher handler/tests; EventBridge Terraform; frontend types/hooks/pages/tests.

**Produces:** `PATCH /v1/orders/{id}/fulfilment`, valid transition enforcement, atomic order/outbox write with `fulfilment-status-changed`, and private live customer timeline updates.

- [ ] Write failing tests for each valid next transition, invalid reverse transition, customer 403, rejected/pending rejection, and concurrent cancellation guard condition.
- [ ] Run the tests to verify transitions/endpoints do not exist.
- [ ] Implement conditional DynamoDB transition/outbox transaction and destination-aware outbox publisher. Extend the WebSocket private branch and frontend order timeline.
- [ ] Run focused Order/outbox/WebSocket/frontend tests and existing saga tests.

### Task 5: Secure User Service deletion

**Files:** User Service main/services/tests; `frontend/src/pages/AdminUsersPage.tsx`; `infra/security.tf`.

**Produces:** `DELETE /v1/users/{username}`, admin JWT enforcement, Cognito error propagation, self-delete rejection, frontend removal only after 2xx.

- [ ] Write failing backend success/403/self-delete/Cognito-error tests and frontend failure-retention test.
- [ ] Run focused tests and observe the absent backend route/direct browser implementation.
- [ ] Implement the server endpoint and repository call; remove the browser Cognito call; add only `cognito-idp:AdminDeleteUser` to User task role.
- [ ] Run User Service and frontend focused tests.

### Task 6: Cart and stock-aware customer flow

**Files:** create `frontend/src/context/CartContext.tsx`; modify App/types/Products/PlaceOrder; create Cart page/tests; Inventory main/models/tests; route Terraform and LocalStack fixtures.

**Produces:** localStorage cart, multi-line checkout request without prices, `/v1/availability`, out-of-stock UI disabled state, server-returned totals.

- [ ] Write failing component tests for add/remove/quantity/persistence and API tests for IN_STOCK/LOW_STOCK/OUT_OF_STOCK plus customer mutation denial.
- [ ] Run focused tests and verify missing context/endpoint failures.
- [ ] Implement read-only availability and cart; call availability again before submission but leave Saga reservation authoritative.
- [ ] Run frontend/Inventory/Order focused tests and update k6/Postman request schema.

### Task 7: Admin promotions, fulfilment and operations dashboard

**Files:** create `AdminPromotionsPage.tsx`, `AdminFulfilmentPage.tsx`, `OperationsPage.tsx`; modify App/types/styles; Order/Product/Inventory read endpoints/tests; Postman collection.

**Produces:** admin business operations views composed from existing bounded-context APIs, with no CloudWatch replacement or analytics service.

- [ ] Write failing component/API tests for restricted routes, dashboard counts and safe fulfilment controls.
- [ ] Run focused tests to verify missing pages/endpoints.
- [ ] Implement the pages, route guards and small bounded-context read endpoints; include only customer-safe identifiers in admin listings.
- [ ] Run frontend build/typecheck/tests and API tests.

### Task 8: Cancellation compensation and reservation ledger

**Files:** Order models/events/services/compensation/tests; Inventory consumer/services/database/models/tests; create Alembic `0002_reservation_ledger.py`; messaging/route Terraform; local setup.

**Produces:** `POST /v1/orders/{id}/cancel`, `CANCEL_PENDING -> CANCELLED`, stored successful reservation lines, and exactly-once stock release.

- [ ] Write failing tests for eligible cancellation, post-dispatch denial, duplicate API/event, release-once, publisher retry and concurrent dispatch cancellation.
- [ ] Run focused tests and confirm the reservation ledger/cancel event is missing.
- [ ] Implement conditional Order/outbox cancellation, Aurora ledger migration and Inventory inbox/outbox release handling. Extend SNS filters and Order event consumer for `order-cancelled`.
- [ ] Run migration rendering, cancellation, saga and Inventory integration tests.

### Task 9: Contracts, documentation and non-deployment verification

**Files:** Postman collection, k6 scripts, LocalStack init, architecture contracts, `docs/final-retail-feature-implementation.md`, `docs/architecture-and-pipeline.md`.

**Produces:** current API examples without client prices, event/schema documentation, deployment-impact plan and assignment traceability.

- [ ] Write/adjust failing route/event contracts for every new public path and no client `unitPrice` in executable callers.
- [ ] Run contracts to confirm callers/routes are stale.
- [ ] Update caller fixtures/docs and write final implementation evidence with source of truth, consistency and deployment order.
- [ ] Run Python quality/tests, frontend lint/typecheck/tests/build, Terraform fmt/validate, architecture tests, Postman syntax checks and `docker compose config`; report unavailable optional tools without weakening gates.
