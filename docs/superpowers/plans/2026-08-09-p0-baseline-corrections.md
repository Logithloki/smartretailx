# SmartRetailX P0 Baseline Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the existing routing, authentication, consistency, WebSocket isolation and release pipeline before creating additional AWS environments.

**Architecture:** Preserve the flat Terraform stack as the current baseline. Replace its unsafe dual writes with DynamoDB and Aurora outbox patterns, use Cognito authorization-code/PKCE in the browser, expose only `/v1`, and deploy exact OCI digests through blocking workflows.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, boto3, SQLAlchemy, Alembic, PostgreSQL 16, React 18, TypeScript, react-oidc-context, Vitest, Playwright, Terraform AWS provider 5.x, GitHub Actions, ECS Fargate, Lambda, DynamoDB, Aurora, SQS, SNS, EventBridge.

## Global Constraints

- Never apply or destroy Terraform or mutate AWS without explicit user approval.
- Preserve existing persistent resource identity and the current dirty working tree.
- Canonical public API path is `/v1`.
- Browser authentication is Cognito authorization code + PKCE; backend RBAC is authoritative.
- OCI digests, not mutable tags, are deployment identity.
- New behavior follows red-green-refactor.
- `live=false` remains the default.
- Do not overwrite or delete assignment screenshots.

---

### Task 1: Canonical `/v1` Routing

**Files:**
- Modify: `infra/frontend.tf`
- Modify: `k6-tests/*.js`
- Modify: `scripts/*.sh`
- Create: `tests/architecture/test_route_contract.py`

**Interfaces:**
- Consumes: HTTP API route keys from `infra/compute.tf`.
- Produces: one public `/v1` contract used by SPA, tests and scripts.

- [ ] Write a route-contract test that extracts configured CloudFront behaviors,
  HTTP API route prefixes, SPA client paths, k6 paths and shell-script URLs and
  fails when `/api/v1` or a CloudFront `/api/*` behavior remains.
- [ ] Run the test and verify it fails on the current `/api/*` behavior and k6 URLs.
- [ ] Remove the `/api/*` CloudFront behavior and update all callers to `/v1`.
- [ ] Run the route-contract test and existing Terraform validation.
- [ ] Commit only the routing/test files with `fix: standardise public API routing`.

### Task 2: Frontend Hosted UI, Runtime Configuration and RBAC

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`
- Replace: `frontend/src/auth-config.ts`
- Replace: `frontend/src/context/AuthContext.tsx`
- Modify: `frontend/src/main.tsx`, `frontend/src/App.tsx`
- Modify: `frontend/src/hooks/useIsAdmin.ts`, `frontend/src/api/client.ts`
- Create: `frontend/public/config.json`
- Create: `frontend/src/config/runtime-config.ts`
- Create: `frontend/src/config/runtime-config.test.ts`
- Create: `frontend/src/hooks/useIsAdmin.test.tsx`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/eslint.config.js`, `frontend/vitest.config.ts`

**Interfaces:**
- `loadRuntimeConfig(): Promise<RuntimeConfig>` validates `/config.json`.
- `RuntimeConfig` contains `apiBaseUrl`, `websocketUrl`, `cognitoAuthority`,
  `cognitoClientId`, `redirectUri`, `logoutUri`, `environment`, `releaseId`.
- `isAdminClaims(profile): boolean` trusts only `cognito:groups`.

- [ ] Add failing tests for missing runtime keys, invalid URLs, relative `/v1`, and
  group-only admin detection.
- [ ] Run Vitest and verify failures represent absent behavior.
- [ ] Implement runtime config validation and group-only role evaluation.
- [ ] Replace the custom password flow with `react-oidc-context` using session
  storage and automatic silent renew/expiry handlers.
- [ ] Make application bootstrap await config before rendering.
- [ ] Remove direct SignUp/ConfirmSignUp/InitiateAuth production calls.
- [ ] Configure ESLint and the frontend test harness.
- [ ] Run lint, typecheck, unit tests and production build.
- [ ] Commit with `fix: use Cognito PKCE and runtime frontend config`.

### Task 3: WebSocket User Isolation

**Files:**
- Modify: `infra/data.tf`, `infra/security.tf`, `infra/websocket.tf`
- Modify: `services/ws-push-lambda/handler.py`
- Modify: `services/ws-push-lambda/tests/test_handler.py`
- Modify: `services/order-service/app/compensation.py`
- Modify: `services/order-service/app/events.py`

**Interfaces:**
- Connection lookup: `query_connections(user_id: str) -> list[str]` via
  `userId-index`.
- Push event requires authoritative `userId` in the payload.

- [ ] Add a failing test with connections for two users and assert only the owning
  user's connection receives the order event.
- [ ] Verify the existing scan/broadcast behavior fails the test.
- [ ] Add the DynamoDB GSI, Query IAM action/resource, and query implementation.
- [ ] Remove scan permission and scan behavior.
- [ ] Ensure WebSocket access logs do not record query tokens.
- [ ] Run Lambda tests and Terraform validation.
- [ ] Commit with `fix: isolate WebSocket updates by customer`.

### Task 4: Atomic Order/Outbox Write and Command Publisher

**Files:**
- Modify: `services/order-service/app/services.py`, `events.py`, `main.py`
- Modify: `services/order-service/tests/test_orders.py`, `test_idempotency.py`
- Create: `services/order-command-publisher-lambda/handler.py`
- Create: `services/order-command-publisher-lambda/tests/test_handler.py`
- Modify: `infra/data.tf`, `infra/lambdas.tf`, `infra/security.tf`, `infra/observability.tf`

**Interfaces:**
- `OrderRepository.create_with_outbox(order, event) -> Order` uses one
  `TransactWriteItems` request.
- Publisher accepts DynamoDB Stream INSERT records and sends the versioned event to
  the existing orders queue.

- [ ] Add failing repository tests proving neither order nor outbox is committed
  independently and duplicate order IDs are rejected.
- [ ] Add failing publisher tests for send success, retry, duplicate delivery and
  partial batch response.
- [ ] Implement the atomic transaction and remove direct SQS send from the request.
- [ ] Implement the publisher Lambda with Powertools, partial-batch failure and
  delivered-state update.
- [ ] Add outbox table/stream, event-source mapping, failure queue, alarms and
  least-privilege roles.
- [ ] Run focused tests, all order/Lambda tests and Terraform validation.
- [ ] Commit with `fix: publish order commands through DynamoDB outbox`.

### Task 5: Aurora Inbox/Outbox and Controlled Migrations

**Files:**
- Create: `services/inventory-service/alembic.ini`
- Create: `services/inventory-service/migrations/env.py`
- Create: `services/inventory-service/migrations/versions/0001_inventory_inbox_outbox.py`
- Modify: inventory models, services, consumer, events, main, Dockerfile and tests.

**Interfaces:**
- `process_order(command) -> PersistedOutcome` commits stock, inbox and outbox once.
- `publish_pending(limit: int) -> int` publishes stored outcomes and marks success.

- [ ] Add failing tests for first processing, duplicate redelivery, publish failure
  after commit, later republish, and conflicting duplicate payload.
- [ ] Verify current code reserves twice under the reproduced failure boundary.
- [ ] Add inbox/outbox SQLAlchemy models and Alembic migration.
- [ ] Implement transactionally idempotent processing.
- [ ] Implement bounded outbox publication with retry/backoff/jitter and explicit
  logging states.
- [ ] Remove production startup schema creation and wire controlled migration
  commands for local/CI/deployment use.
- [ ] Run inventory tests, migration upgrade/downgrade validation and container build.
- [ ] Commit with `fix: make inventory saga redelivery safe`.

### Task 6: Event Contracts and Correlation

**Files:**
- Create: `services/common/srx_common/events.py`, `middleware.py`
- Modify: all FastAPI apps, event publishers/consumers and relevant Lambdas.
- Create: `tests/contracts/test_event_contracts.py`

**Interfaces:**
- `DomainEvent[T]` includes version, ID, timestamp, correlation ID, aggregate ID and
  typed payload.
- `X-Correlation-ID` is accepted/generated, logged, returned and propagated.

- [ ] Add failing contract and middleware tests.
- [ ] Implement typed event envelopes and correlation middleware.
- [ ] Migrate order, inventory, notification and WebSocket paths.
- [ ] Add compatibility validation for unsupported event versions.
- [ ] Run all backend/Lambda/contract tests.
- [ ] Commit with `feat: standardise event contracts and correlation`.

### Task 7: Blocking Quality and Digest-Based Release Workflows

**Files:**
- Replace: `.github/workflows/deploy.yml`
- Create: `.github/workflows/pr-ci.yml`, `release.yml`, `infrastructure.yml`, `performance.yml`
- Create reusable workflows under `.github/workflows/reusable/`
- Create: `scripts/release/render-task-definition.py`, `verify-ecs-deployment.py`,
  `generate-manifest.py`, `deploy-frontend-release.py` and tests.

**Interfaces:**
- Release manifest records Git SHA, image digests, Lambda checksums, SPA checksum and
  workflow identity.
- ECS deploy accepts environment, service and exact image digest.

- [ ] Add failing script tests for ECR name derivation, digest substitution,
  rerun digest verification, rollback detection and release-manifest schema.
- [ ] Implement deterministic release helper scripts.
- [ ] Add blocking Python/frontend/Terraform/security/integration reusable workflows.
- [ ] Build each image once, reuse an existing immutable SHA tag only when its
  digest matches, and record repository digests.
- [ ] Register exact digest task definitions, update services, wait stable, inspect
  failures/target health and smoke test.
- [ ] Package Lambda artifacts and SPA once and upload the release manifest.
- [ ] Add development/test/staging/production environments and concurrency groups.
- [ ] Ensure production applies only an approved saved Terraform plan.
- [ ] Validate workflow YAML and run helper tests.
- [ ] Commit with `ci: add immutable release promotion pipeline`.

### Task 8: Verification and Documentation

**Files:**
- Create: `docs/architecture-and-pipeline.md`
- Modify: inaccurate runbooks/evidence index.
- Create: `docs/diagram-change-list.md`

- [ ] Run Terraform fmt/validate/TFLint/Checkov where installed.
- [ ] Run every Python test and coverage threshold.
- [ ] Run frontend lint/typecheck/test/build and Playwright tests where locally
  possible.
- [ ] Run container builds, LocalStack integration, Postman/Newman contracts and k6
  syntax/smoke validation where locally possible.
- [ ] Classify every result PASS, FAIL or BLOCKED with exact evidence.
- [ ] Update architecture/pipeline documentation and diagram change list to match
  the implemented baseline.
- [ ] Commit with `docs: document production-ready baseline and pipeline`.
