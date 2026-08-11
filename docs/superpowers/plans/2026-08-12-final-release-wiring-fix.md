# Final Release Wiring Fix Implementation Plan

> **For agentic workers:** Execute inline in the current `codex/production-readiness` checkout. The approved release candidate is uncommitted, so do not create a clean worktree that would omit it.

**Goal:** Remove the three release blockers and complete the approved real-time pricing, live cancellation, promotion administration, and event-contract wiring without planning or deploying AWS infrastructure.

**Architecture:** Preserve the existing command/event boundaries. Extend the existing SNS filter, DynamoDB Streams/EventBridge Pipes/WebSocket path, and React WebSocket hook. Add a manual baseline workflow that initializes the repository's default backend and refuses to plan unless known existing-state sentinels are present.

**Tech Stack:** Terraform 1.9, GitHub Actions, Python 3.12, pytest, FastAPI, DynamoDB Streams, EventBridge Pipes, SNS/SQS, React 18, TypeScript, Vitest, Testing Library.

## Global Constraints

- Do not run Terraform plan/apply/destroy/import or any state command that mutates, migrates, copies, or removes state.
- Do not deploy or mutate AWS/application data/Cognito.
- Do not commit or push.
- Preserve the existing baseline state key `smartretailx/terraform.tfstate` and baseline project identity `smartretailx`.
- Keep `smartretailx/production/terraform.tfstate` as future isolated-production design only.
- Use test-first red/green cycles for every behavior change.
- Preserve authoritative server pricing and private WebSocket user isolation.

---

### Task 1: P0 routing and executable-caller contracts

**Files:**
- Create: `tests/architecture/test_release_wiring_contract.py`
- Create: `scripts/check_order_callers.py`
- Modify: `infra/messaging.tf`
- Modify: `.github/workflows/reusable/integration-tests.yml`
- Modify: `.github/workflows/reusable/smoke-tests.yml`

**Produces:** A narrow three-event SNS subscription and a reusable repository scanner that rejects monetary fields in executable order-creation payloads.

- [ ] Add failing architecture tests for the exact SNS allow-list and unsafe/safe order payload fixtures.
- [ ] Run the focused tests and confirm failures identify `order-cancelled` and the two stale CI payloads.
- [ ] Add `order-cancelled` to the SNS filter without broadening it.
- [ ] Remove `unitPrice` and the unused price extraction from both CI workflows.
- [ ] Implement the scanner and run it against CI, Postman, k6, frontend and scripts.
- [ ] Re-run the focused tests green.

### Task 2: Same-state baseline release workflow

**Files:**
- Create: `.github/workflows/baseline-release.yml`
- Modify: `scripts/check_baseline_plan.py`
- Modify: `tests/architecture/test_baseline_plan_policy.py`
- Modify: `infra/oidc.tf`

**Produces:** A manual, protected workflow using the default backend and a state-sentinel policy callable before plan creation.

- [ ] Add failing policy tests for missing/partial/complete baseline state address sets.
- [ ] Add failing architecture tests that reject a baseline workflow containing the isolated-production backend or project identity.
- [ ] Extend the policy script with the actual VPC, ECS, Cognito, Aurora, orders/products, SPA and CloudFront sentinels.
- [ ] Add exact baseline state and lock-object ARNs to the plan-role policy.
- [ ] Implement a `workflow_dispatch`-only baseline workflow: download immutable release, default-backend init, read-only state list, sentinel gate, plan, deletion policy, artifact/checksum, protected exact-plan apply, application rollout, smoke and rollback.
- [ ] Confirm the workflow never passes `environments/production/backend.hcl` or `smartretailx-prod`.
- [ ] Run source-only workflow/policy tests green; do not execute the workflow.

### Task 3: Base-price invalidation through the native product stream

**Files:**
- Modify: `services/product-service/tests/test_products.py`
- Modify: `services/product-service/app/services.py`
- Modify: `services/ws-push-lambda/tests/test_handler.py`
- Modify: `services/ws-push-lambda/handler.py`
- Modify: `infra/pipes.tf`

**Produces:** Price-only product mutations marked in DynamoDB, filtered by a native Pipe, and converted into the existing public `catalogue.price-refresh` message without prices.

- [ ] Add a failing Product repository test proving a price update emits a marker/version stream state while a description-only update does not.
- [ ] Add failing WebSocket tests for a valid product refresh, PII rejection and price omission.
- [ ] Add failing architecture assertions for products-stream source, marker filter and EventBridge detail type.
- [ ] Implement conditional product marker/version writes and marker clearing.
- [ ] Add least-privilege product-stream read access and `aws_pipes_pipe.product_price_refresh`.
- [ ] Extend the existing EventBridge rule and WebSocket extractor for `smartretailx.products` / `product.price-refresh`.
- [ ] Run Product, WebSocket and architecture tests green.

### Task 4: SPA authoritative catalogue refetch

**Files:**
- Modify: `frontend/src/hooks/useOrderStatusStream.ts`
- Modify: `frontend/src/pages/ProductsPage.tsx`
- Create: `frontend/src/hooks/useOrderStatusStream.test.ts`
- Create: `frontend/src/pages/ProductsPage.test.tsx`

**Produces:** Runtime-validated catalogue invalidations that refetch affected products or the full catalogue and never consume a WebSocket price.

- [ ] Add failing parser tests for valid catalogue, private-order, malformed JSON and malformed catalogue messages.
- [ ] Add failing ProductsPage tests for affected-product refetch/update, private-event non-refresh and malformed-event fail-safe behavior.
- [ ] Introduce a `CataloguePriceRefresh` union member with strict runtime parsing.
- [ ] Reuse the existing WebSocket hook from ProductsPage and refetch `/v1/products/{id}` for supplied IDs or `/v1/products` when the affected set is empty.
- [ ] Re-run focused frontend tests green.

### Task 5: Live cancellation status

**Files:**
- Modify: `infra/pipes.tf`
- Modify: `services/ws-push-lambda/tests/test_handler.py`
- Modify: `frontend/src/hooks/useOrderStatusStream.ts`
- Modify: `frontend/src/pages/MyOrdersPage.tsx`

**Produces:** Private, owning-user-only `CANCEL_PENDING` and `CANCELLED` updates.

- [ ] Add failing tests proving `CANCELLED` reaches only the owning connection and is accepted by the frontend parser.
- [ ] Extend the order Pipe status allow-list to `CANCEL_PENDING` and `CANCELLED`.
- [ ] Extend frontend order status types/parser without altering the private query branch.
- [ ] Run focused Lambda/frontend/architecture tests green.

### Task 6: Admin promotion management and IAM cleanup

**Files:**
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/pages/AdminPromotionsPage.tsx`
- Create: `frontend/src/pages/AdminPromotionsPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css` only if existing component classes cannot express the page
- Modify: `infra/security.tf`

**Produces:** Admin list/create/edit/enable-disable UI using existing RBAC APIs; no hard delete and no promotion DeleteItem permission.

- [ ] Add failing page tests for list rendering, create, edit and enable/disable calls.
- [ ] Add Promotion/PromotionCreate/PromotionUpdate frontend contracts.
- [ ] Implement the page using existing table/form/badge styling and accessible controls.
- [ ] Add the protected route/navigation entry.
- [ ] Remove `dynamodb:DeleteItem` from promotion permissions only.
- [ ] Run focused tests, lint and typecheck green.

### Task 7: Normalize event and environment documentation

**Files:**
- Modify: `docs/architecture-and-pipeline.md`
- Modify: `docs/final-retail-feature-implementation.md`

**Produces:** One compact runtime contract table and an explicit current-baseline versus future-isolated-production distinction.

- [ ] Document the exact producer, transport, consumer, privacy and purpose for every new runtime event/detail type.
- [ ] Remove claims that `price-updated` or `inventory-released` are runtime events.
- [ ] Document public native Pipe semantics versus application `EventEnvelope` semantics.
- [ ] Correct promotion administration wording to create/edit/enable-disable with retained history.
- [ ] State that `baseline-release.yml` is the current same-state path and `production.yml` is future isolated-production only.

### Task 8: Full non-deployment verification

**Files:** No production changes.

- [ ] Run Ruff and Bandit across production Python.
- [ ] Run every service pytest suite and source-only architecture/static tests.
- [ ] Run frontend lint, typecheck, unit tests and a production build into a temporary directory.
- [ ] Run Terraform fmt-check, validate and Checkov without a state-backed plan.
- [ ] Generate all four FastAPI OpenAPI schemas.
- [ ] Run the executable-caller scanner.
- [ ] Render Alembic migrations offline.
- [ ] Run `docker compose config` only.
- [ ] Inspect `git diff` and verify only scoped files changed.
- [ ] Report explicitly that no plan, deployment, AWS mutation, state migration/import/copy, commit or push occurred.
