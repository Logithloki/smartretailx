# SmartRetailX architecture and delivery pipeline

Status legend: **Implemented** means present in source/Terraform/workflows; **configured, not deployed** means locally validated but not applied to an AWS environment in this change; **future** is deliberately not claimed as working.

## 1. Actual architecture

The public entry point is CloudFront with WAF. It serves the versioned React SPA from private S3 and forwards only `/v1/*` to API Gateway HTTP API. API Gateway validates Cognito JWTs and reaches an internal ALB through VPC Link. Four ARM64 FastAPI services run on ECS Fargate. Orders/products use DynamoDB; inventory uses Aurora Serverless v2 PostgreSQL 16. This is implemented in Terraform and locally validated, but the new environment profiles have not been applied.

## 2. Request lifecycle

The SPA loads immutable JavaScript plus environment-specific `/config.json`, completes Cognito authorization-code + PKCE, and sends the access token to `/v1`. The HTTP service accepts or creates `X-Correlation-ID`, returns it, and logs it. Order creation atomically writes an order and outbox row. The outbox stream Lambda sends the reservation command to SQS. Inventory commits its inbox record, stock mutation, and outcome outbox in one Aurora transaction. The relay publishes the outcome to SNS; Order compensates a rejection. Order DynamoDB Streams flow through EventBridge Pipes for WebSocket/UI events.

## 3. Microservices

- Order: create/read orders, per-user GSI reads, idempotency and transactional outbox.
- Inventory: admin stock API, SQS consumer, SQL inbox/outbox, retry and application circuit breaker.
- Product: authenticated catalogue and admin CRUD, DynamoDB GSI, per-task TTL cache.
- User: own-profile and admin Cognito directory reads.

## 4. Authentication

Browser authentication uses Cognito Hosted UI, OAuth 2.0 authorization code and PKCE through `react-oidc-context`. Tokens use session storage; the library owns state, nonce, PKCE, refresh and expiry handling. Admin state comes only from exact `cognito:groups` membership. HTTP authorization remains backend-authoritative. WebSocket `$connect` uses its dedicated JWT authorizer because API Gateway WebSocket APIs lack the HTTP JWT authorizer. Query tokens are never intentionally logged and WAF logging redacts authorization/cookie fields.

## 5. Event-driven flow

Commands use SQS, domain outcomes use SNS, stream changes use EventBridge Pipes and EventBridge. Important messages use the shared versioned envelope: `eventType`, `eventVersion`, `eventId`, `occurredAt`, `correlationId`, `aggregateId`, optional causation/trace IDs, and payload. Pydantic contract tests reject missing/extra fields. DLQs and alarms exist for the inventory command consumer and order-outbox stream relay.

## 6. Saga

The choreography is `PENDING -> CONFIRMED` or `PENDING -> REJECTED`. Insufficient stock produces `order-rejected`; Order applies the compensating status change idempotently. GC-1 is retained: both confirmed and rejected outcomes reach the Order event queue so successful orders cannot remain pending.

## 7. Consistency strategy

Order uses DynamoDB `TransactWriteItems` for the aggregate and command outbox. Inventory uses an order-ID-unique inbox plus outcome outbox inside the stock transaction. Redelivery returns the recorded outcome and does not reserve twice. Relay failure leaves recoverable pending outbox state. Alembic owns schema changes; `create_all()` is absent from startup. The ECS delivery workflow runs `alembic upgrade head` using the exact new task revision before an inventory rollout.

## 8. Environments

The currently deployed assignment stack is the `baseline` identity in the root backend key `smartretailx/terraform.tfstate`; it is released only through the manual, protected `baseline-release.yml` same-state workflow and retains the baseline-to-`development` GitHub Environment compatibility mapping. The `sandbox`, `development`, `test`, `staging`, and `production` profiles are isolated future stacks with their own state keys and project prefixes. In particular, `smartretailx/production/terraform.tfstate` is not a release path for the deployed baseline. All profiles default to `live=false`; staging/production reject localhost Cognito callbacks and cannot enable auto-confirm.

## 9. Terraform structure

The corrected architecture remains in the existing root, split by concern (`network`, `data`, `messaging`, `compute`, `security`, `observability`, and related files). Environment backend/tfvars profiles are implemented. Moving existing resources under a module is intentionally **not implemented**: without a state-backed plan and `moved` blocks, that change could replace persistent resources. This is a safety decision, not an assertion that the requested module migration is complete.

## 10. CI pipeline

PR CI runs per-component pytest/coverage, focused Ruff/Bandit/pip-audit, frontend lint/typecheck/unit/build, Terraform fmt/validate/TFLint/Checkov, Gitleaks, deterministic Compose/LocalStack integration, route/environment/release architecture contracts, and event contracts. Mandatory gates contain no `continue-on-error`. Security and build tools use stable version pins; Trivy uses an immutable remediated action commit and scans exact image digests.

## 11. CD pipeline

Main creates one release. `promote.yml` deploys that release to future development, test, or staging stacks without rebuilding. `production.yml` remains the future isolated-production path using `smartretailx/production/terraform.tfstate`. For the existing deployed assignment baseline, `baseline-release.yml` is manual-only, verifies sentinel addresses in `smartretailx/terraform.tfstate`, creates and policy-checks a binary plan, waits for protected approval, and applies only that reviewed artifact. No deployment workflow was executed during this implementation.

## 12. Artifact promotion

Four ARM64 OCI images use immutable Git-SHA tags and resolved `repository@sha256` authority. A rerun reuses the existing digest. Lambda ZIPs vendor Linux ARM64 Python dependencies and have deterministic timestamps/checksums. The SPA archive contains no environment values. The release manifest records Git SHA, four digests, Lambda checksums, SPA checksum, source run, and Terraform version. Environments consume the original run's artifacts.

## 13. Rollback

ECS uses circuit breaker rollback and CloudWatch unhealthy-target deployment alarms. The workflow waits for stability and rejects a rolled-back/non-primary revision. Production snapshots all active ECS task definitions, Lambda alias versions and the current SPA release before apply. Failed service, Lambda, frontend, smoke, or browser validation restores those pointers and waits for ECS stability. Versioned S3 releases remain available; invalidations are limited to entry/runtime metadata.

## 14. Security gates

OIDC is split: main-only ECR build role, main-only read/state-lock plan role, and per-environment deploy role whose subject exactly matches its GitHub Environment. Production depends on an externally bootstrapped Terraform apply role. WAF managed rules plus per-IP rate limiting are enabled; WAF logs redact credentials. S3 is private/OAC-only and versioned. Task roles are per service and DB credentials come from the RDS-managed secret. Production data resources disable force-delete and enable deletion protection where supported.

## 15. Testing strategy

Unit/component tests cover service APIs, RBAC, idempotency, transactional boundaries, event validation, retry/breaker behavior, WebSocket isolation, and notification behavior. OpenAPI tests assert canonical routes. Compose integration exercises LocalStack/PostgreSQL, migrations, an order, replay and terminal Saga outcome. Newman adds live API/RBAC/CRUD/validation coverage. Playwright adds the critical customer/admin browser journeys.

## 16. Performance testing

Separate k6 smoke, load, concurrent-user, stress and spike profiles use canonical schemas/routes and strict HTTPS/token configuration. Outputs include machine-readable summaries with latency percentiles and errors. PR CI does not run load. TEST uses smoke; STAGING/manual runs load/stress/spike. `loadTest` is propagated as an SNS message attribute so performance runs cannot spam SES.

## 17. Observability

CloudWatch is primary. The Terraform dashboard includes API volume/4xx/5xx/p50/p90/p95/p99, ECS CPU/memory, queue/DLQ depth and message age, Lambda errors/throttles, DynamoDB consumption/throttles/errors, and Aurora capacity/connections/latency. Alarms cover API 5xx/p95, unhealthy targets, Lambda errors, queue depth/age, DLQs, and Aurora connections. FastAPI correlation middleware and OpenTelemetry SDK export through the ADOT sidecar to X-Ray. Actual end-to-end traces still require AWS evidence.

## 18. High availability

Two AZs, ALB health checks, Fargate replacement, Aurora distributed storage, deployment rollback, and autoscaling are configured. Production has two tasks per service and a second Aurora Serverless instance; lower environments retain one task when live. The task-kill script is explicitly gated to TEST/STAGING and records recovery evidence.

## 19. Disaster recovery

ADR-07 remains the truthful design: eu-central-1 pilot-light recovery using Terraform plus hourly cross-region backup copy; products alone use the ap-south-1 Global Table. The current repository does **not** contain a complete secondary-region Terraform root or deployed backup-copy plan, so regional DR is **designed, not Terraform-ready or live**. No Route 53 domain/failover is claimed. This is a P2 remaining item.

## 20. RTO/RPO

Targets remain: AZ failure RTO under one minute/RPO approximately zero; corruption recovery through PITR RPO approximately five minutes; regional loss RTO 30–45 minutes/RPO at most one hour. None was newly measured in this change. Scripts and evidence fields distinguish target from measured result.

## 21. Cost strategy

Fargate, HTTP API, Graviton, DynamoDB on-demand, Aurora min-0/max-2, gateway endpoints, one NAT, and CloudWatch-first observability preserve the settled ADRs. Profiles park billable compute/egress with `live=false`; CloudFront/WAF/storage and other retained resources mean parked is low-cost, not zero-cost. `scripts/set-live.ps1` always shows a plan and requires an exact typed confirmation.

## 22. Limitations

The new environment stacks, OIDC roles, aliases, WAF logging, traces, alarms and delivery workflows are configured but not deployed or AWS-verified. GitHub Environment reviewers/branch rules and secret/variable values require repository settings. Terraform module/state migration, a dedicated DR root, CloudTrail/VPC Flow Logs, budget anomaly automation, and Grafana production hardening remain incomplete. Cognito live Playwright and Newman need short-lived test credentials/tokens.

## 23. Future improvements

After P0/P1 AWS evidence: perform the state-aware module migration with `moved` blocks; implement/test eu-central-1 backup restore; add CloudTrail and selectively enabled Flow Logs with a cost ADR; evaluate one native ECS blue/green service only if provider/state safety is proven; and either harden Grafana fully or remove the prototype from production claims.

## 24. Retail authority and real-time contracts

Orders now snapshot Decimal base/effective unit prices, discounts, names and totals from Product and Promotions data at submission; client prices are rejected. Promotion lifecycle state is a multi-task-safe notification projection only: Product Service tasks race through conditional DynamoDB transitions and the promotions stream reaches the WebSocket Lambda through an EventBridge Pipe. Base-price writes use the existing Products stream and a second native Pipe. Both become the safe public `catalogue.price-refresh` identifier-only message; the SPA validates it and refetches authoritative Product Service data without reloading. Private order/fulfilment notifications continue to use only the `userId-index`, including `CANCEL_PENDING` and `CANCELLED`. Cancellation is a choreography extension: a conditional cancellation request emits `order-cancel-requested`, Aurora transitions durable reservation-ledger rows from `RESERVED` to `RELEASED`, and `order-cancelled` finalises the order. No notification event is pricing authority.

### Native promotion-pipe traceability boundary

The promotion refresh path intentionally remains DynamoDB Streams -> EventBridge
Pipe -> EventBridge rule -> WebSocket push, with no glue Lambda. The native
EventBridge record preserves the DynamoDB stream detail, including the
`promotionId`, affected `productIds`, lifecycle revision, event name and event
time metadata. It therefore preserves aggregate identity and ordering context,
but it does not manufacture the application envelope's `correlationId` or
`causationId`. Those identifiers remain guaranteed for transactional
application events; promotion refresh is a public, best-effort refetch signal
and never checkout authority. The WebSocket Lambda whitelists only product IDs
and revision before broadcast.
