# CLAUDE.md — SmartRetailX (COMP60010 Enterprise Cloud & Distributed Web Applications)

## What this project is
Final-year university assignment worth 50% of the module mark. Deadline: **30 September 2026**.
Target: **95+ marks**. Marking: Implementation 40% · Architecture 20% · Testing 20% · Viva 20%.
The lecturer's stated differentiators: **cost-effectiveness** and **innovative AWS service choices**.
Everything must be demonstrable live on AWS (eu-west-1) at the viva, built entirely with Terraform.

This file is the source of truth for architecture decisions and working rules.
It was distilled from an extensive design-review conversation. **Do not re-litigate
settled decisions (ADRs below) unless the user explicitly asks.**

## Repo layout
- `infra/` — Terraform (currently one main.tf; to be split into network.tf / data.tf / messaging.tf / compute.tf / security.tf / observability.tf)
- `services/{order,inventory,user,product}-service/` — Python 3.12 + FastAPI microservices
- `localstack-init/` — LocalStack seed scripts
- `docker-compose.yml`, `Makefile` — local dev (LocalStack + Postgres 16)
- `assignment-screenshots/` — evidence for the report (never delete)

## Settled architecture decisions (ADRs) — final
- **ADR-01** ECS Fargate over EKS ($0 idle vs $73/mo control plane)
- **ADR-02** API Gateway HTTP API v2 over REST (−71% cost). Consequences accepted:
  no request validators → **Pydantic is the validation layer**; WAF cannot attach to
  HTTP API → **WAF lives on CloudFront** (dual origin: S3 static + /api/* → API GW)
- **ADR-03** Polyglot persistence: DynamoDB (orders, products, idempotency, ws-connections)
  + Aurora Serverless v2 PostgreSQL 16 (inventory). Per-task in-memory TTL cache in dev;
  ElastiCache Serverless named as prod path only
- **ADR-04** Single NAT Gateway (~$35/mo), free **gateway** VPC endpoints for DynamoDB+S3.
  Interface endpoints REJECTED (8 × ~$8 ≈ $64/mo > NAT). Single NAT = documented conscious SPOF
- **ADR-05** Grafana OSS on Fargate (~$3/mo) over Managed Grafana ($29/user/mo).
  Access via ALB Cognito OIDC listener + SSM port-forward. **Never public**
- **ADR-06** Saga = choreography (not Step Functions): insufficient stock →
  `order-rejected` event → Order Service compensates (status=REJECTED). Idempotent retries
- **ADR-07** Multi-region: DR = **eu-central-1** (GDPR: personal data stays in EU;
  pilot-light via terraform apply + hourly AWS Backup cross-region snapshot copy).
  **ap-south-1 Mumbai = future APAC expansion cell**: DynamoDB **Global Table for
  PRODUCTS ONLY** (no personal data → lawful multi-region). Mumbai is NOT a DR copy
- **ADR-08** ARM64 Graviton Fargate (−20% compute). All images built with
  `docker buildx --platform linux/arm64`; task defs set `runtime_platform { cpu_architecture = "ARM64" }`

Event routing rule (viva answer): **commands → SQS · domain events → EventBridge · fan-out → SNS**.
DynamoDB Streams → **EventBridge Pipes** (zero glue Lambda) is the headline differentiator.

Tiered resilience targets (never say "synchronous replication RPO 5 min" — it is a contradiction):
AZ failure: RTO <1 min / RPO ≈ 0 (ALB health checks + Aurora storage replication) ·
Corruption: PITR, RPO ≈ 5 min · Region loss: RTO 30–45 min / RPO ≤ 1 h (terraform + snapshot copy).

## Critical fix backlog (in priority order)
1. **ALB must be internal** (`internal = true`, private subnets, SG scoped to VPC Link ENIs).
   The public ALB bypasses the Cognito JWT authoriser entirely
2. **Cognito exclusively in Terraform** — a console-created pool exists from Week 1; delete it,
   keep only the Terraform pool (pool + client + customer/admin groups + seed-user script)
3. **Aurora**: engine PG **16.x** (match local postgres:16), `min_capacity = 0` (auto-pause),
   `max_capacity = 2` (cost circuit breaker), `manage_master_user_password = true`
   (remove plaintext password variable and the manual Secrets Manager secret)
4. **Per-service IAM task roles** (least privilege matrix), separate from the execution role;
   DB creds injected via ECS `secrets` valueFrom — never plaintext env
5. **`live` toggle**: `variable "live" { type = bool, default = false }` gating `count` on
   NAT Gateway, ALB, CloudFront+WAF, and every ECS service `desired_count`.
   live=false ≈ $0/mo (parked); live=true rebuilds in ~10–12 min
6. **Data subnets isolated**: own route table, NO default route (currently they route via NAT)
7. **DynamoDB**: GSIs (orders: userId-index; products: category-index), PITR on orders,
   **remove TTL from orders table** (financial retention) — TTL stays only on idempotency
   and websocket-connections
8. **SQS**: `receive_wait_time_seconds = 20`; CloudWatch alarm on **DLQ depth ≥ 1**
9. **ECR**: `IMMUTABLE` tags + lifecycle policy keep-5
10. **CI/CD → GitHub OIDC** (`role-to-assume`), delete stored AWS access keys;
    pipeline stages: pytest+coverage → checkov+tflint → buildx ARM64 → Trivy → ECR → ecs update
    (rolling, deployment circuit breaker + auto-rollback)
11. Rename `MakeFile` → `Makefile` (breaks on Linux CI); remove `-auto-approve` from `make destroy`
12. **/v1** prefix on all FastAPI routers (API versioning is an explicitly marked requirement)
13. Circuit breakers: pybreaker/tenacity around Aurora + payment calls; ECS
    `deployment_circuit_breaker { enable = true, rollback = true }`
14. **Product Service must actually be built** (DDB reads + TTL cache + Global Table) —
    the old plan never scheduled it
15. EventBridge **Scheduler**: 00:00 park (ECS desired=0; Aurora auto-pauses itself),
    08:00 restore, daily stock-reconciliation cron

## Cost guardrails — standing orders for Claude Code
- **NEVER run `terraform apply`, `terraform destroy`, or any mutating `aws` CLI command
  without explicitly asking the user first.** `terraform plan`, `validate`, `fmt` are always fine
- Default posture is **live=false (parked)**. Remind the user to park at the end of any live session
- Budget: $50 alarm exists (may be raised to $75 in final month). Aurora stop via CLI
  auto-restarts after 7 days — rely on min-0 auto-pause instead
- Local-first: features are developed against Docker Compose + LocalStack.
  LocalStack Community CANNOT emulate: EventBridge Pipes, API GW v2 (HTTP+WebSocket),
  Cognito, ALB, X-Ray, IAM enforcement — those are validated on real AWS in weekly windows

## Credential hygiene — standing orders
- NEVER read, cat, print, or copy ~/.aws/credentials, ~/.aws/config, or any
  AWS_SECRET/SESSION env var value. Auth happens implicitly via my configured
  AWS CLI profile — you never need the key values themselves.
- NEVER write access keys, secrets, tokens, or JWT values into CLAUDE.md,
  memory files, code, comments, commits, or logs. Account ID and resource
  IDs/ARNs are fine; key material never is.
- If any command output contains a secret value, redact it before quoting.

## Weekly plan (from late July → 30 Sep)
1. **Infra corrections week**: fix backlog items 1–9 + 11, apply once, validate, park
2. Order Service + Product Service (local); weekly AWS window: deploy + wire JWT authoriser
3. Inventory Service: SQS consumer, retry+breaker, Aurora txn, SNS, **compensating order-rejected path**
4. Notification Lambda + SES (verify sender email early — sandbox!) + Powertools + Scheduler
5. AWS-seams week: Pipes, WebSocket API + minimal S3/CloudFront frontend page (viva centrepiece),
   OIDC CI/CD, Grafana, ADOT/X-Ray
6. **Testing week (20% of grade)**: k6 load/stress/spike **against real AWS** with autoscaling
   graphs, chaos task-kill under load, DLQ poison-message demo, Aurora failover screenshot,
   ZAP baseline, bandit, pip-audit, coverage report, LocalStack integration job in CI;
   add products Global Table
7. **Report week**: 4,000–5,000 words, ADRs, requirement→evidence traceability matrix,
   cost chapter with real Cost Explorer screenshots
8. Slides (10–15) + README + ZIP + recorded backup demo video
9. Buffer + two timed rehearsals; submit ~2 days early. Viva day: apply live=true in the
   morning, pre-warm Aurora 15 min before demo, park after

## Guide corrections (defects found in IMPLEMENTATION-GUIDE.md while executing it)
Recorded in `docs/guide-corrections.md` and fixed in the guide text itself. These are
corrections, not workarounds — following the original wording would have broken the system.
- **GC-1** order-events SNS filter must be `["order-confirmed","order-rejected"]`, not
  rejected-only: that queue is the only route out of PENDING, so a rejected-only filter
  strands every successful order (and contradicts the guide's own W3 D5 gate)
- **GC-2** ECS `desired_count = var.live ? var.service_desired_count : 0` (default 0), not
  `? 1 : 0`: at CW-1 the image tags do not exist yet, so 1 trips the deployment circuit breaker
- **IC-1** test users on `@example.com`, not `@smartretailx.test` — `.test` is RFC 2606
  special-use and `email-validator` rejects it (self-inflicted, not a guide defect)
Cite the correction ID in the report's methodology section; expect a viva question on why
the code and the plan differ.

## Conventions
- Python 3.12, FastAPI, pytest + moto for unit tests, httpx for API tests
- Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`)
- Every AWS-visible milestone gets a screenshot into `assignment-screenshots/` with a numbered name
- Harvard referencing in the report; log AI-tool usage for the academic-integrity declaration

## Amendments from adversarial self-review (2026-07-25) — treat as part of the backlog
- Count-gate the API GW integration + routes together with the ALB listener (refs error when live=false otherwise)
- Do NOT count-gate CloudFront (free idle, 15-20 min create/delete); WAF stays once added (~£5/mo, ledgered)
- After autoscaling attaches: `ignore_changes = [desired_count]` on services; park via appautoscaling target `min_capacity = var.live ? 1 : 0`
- Aurora cluster: `storage_encrypted = true` (diagram claims KMS at rest)
- Products Global Table requires Streams (NEW_AND_OLD_IMAGES) on the products table first
- WebSocket `$connect` Lambda MUST validate the Cognito JWT (WS APIs have no JWT authorizer) and reject otherwise
- Grafana access = CloudFront VPC origin -> internal ALB (Cognito OIDC listener rule); SSM port-forward is fallback only
- Cognito Hosted UI needs `aws_cognito_user_pool_domain`
- ECR `force_delete = true` + S3 `force_destroy = true` so the DR destroy/apply drill actually completes
- Remote state: S3 backend + lockfile in Week 1 Day 1 (laptop-loss insurance)
- Auth fail-closed: unset ENV behaves as production, never as local

## Final-review additions to the fix backlog (from adversarial pass)
16. CloudFront /api/* behavior: origin request policy AllViewerExceptHostHeader +
    CachingDisabled — otherwise Authorization header is stripped → blanket 401s
17. WebSocket $connect Lambda authorizer (WS APIs have NO JWT authorizer); token via query string
18. CORS configuration on the HTTP API for the CloudFront origin
19. aws_cognito_user_pool_domain + client callback URLs + auth-code flow (Hosted UI prerequisite)
20. Enable Streams (NEW_AND_OLD_IMAGES) on products table BEFORE adding the Global Table replica
21. k6 must not spam SES: target /v1/products primarily; loadTest message-attribute filter on SNS sub
22. aws_ecs_service depends_on the gated private egress route (unpark race)
23. Verify newest Aurora PG 16.x in eu-west-1 before pinning engine_version
24. Scheduler: schedule_expression_timezone = "Asia/Colombo"
25. Route 53 is design-intent only (no custom domain purchased); demo uses default AWS URLs
26. Regenerate/fix the swimlane + DR diagrams to match the corrected architecture (old errors persist there)

## Lecturer rulings (in writing — cite in report and viva)
- "Production level" = production PRACTICES with demo-scale sizing, each recorded as an ADR
  with a costed path to scale. Confirmed "good enough and perfect". Do NOT expand sizing.
- Frontend: a FULL UI with CRUD features IS REQUIRED (not a minimal demo page).
  UI is mandatory scope — REMOVED from the descope list. UI polish (styling depth) is the
  new flex point; feature completeness is not negotiable.
- OPEN: multi-region depth was not explicitly re-confirmed (his reply addressed the UI).
  Proceeding with Global Table + documented/timed DR unless he objects — confirm with a
  one-line follow-up at next contact.

## Frontend scope (mandatory)
React SPA (Vite + react-router) on existing S3 + CloudFront + WAF. Auth: Cognito Hosted UI,
authorization-code + PKCE via react-oidc-context; roles from cognito:groups claim
(UI hides admin pages; backend enforces regardless).
Pages: Products list/detail · Admin product CRUD · Place order · My Orders with live
WebSocket status · Admin stock view/adjust · Login/Callback.
Schedule: W5 D4 scaffold + auth end-to-end; W6 D1–3 feature build-out
(Grafana/ADOT shift to W6 D4–5; chaos prep merges into testing week).

## Backlog additions (frontend ruling)
27. React SPA build as scoped above (4 days total)
28. Product service: POST/PUT/DELETE /v1/products, admin-group RBAC middleware
29. Order service: GET /v1/orders (userId GSI) + GET /v1/orders/{id}
30. Inventory service: GET/PATCH stock endpoints (admin only)
31. Diagram label updated to "React SPA (CRUD UI)" — keep artifacts consistent
32. CI: build SPA (npm build) + sync to S3 + CloudFront invalidation stage
