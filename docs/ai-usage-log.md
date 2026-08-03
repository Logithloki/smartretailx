# AI Usage Log — SmartRetailX

One line per session describing AI assistance (guide §0 rule 5 — academic-integrity declaration).
Harvard-referenced acknowledgement of AI tooling goes in the report's declaration section.

| Date | Tool | Assistance provided |
|------|------|---------------------|
| 2026-07 (design phase) | Claude (chat) | Architecture design review producing the ADR set (ADR-01..08), fix backlog 1–32, and the master implementation guide; adversarial self-review passes on the design and diagram |
| 2026-08-02 | Claude Code | Full read-only repository audit against CLAUDE.md/guide (gap table, contradictions, live-billing discovery); then, with approval, Week-0 hygiene fixes and Week-1 Terraform corrections (live toggle, internal ALB, data-subnet isolation, DynamoDB/SQS/ECR fixes, Aurora PG16 min-0, per-service IAM) |
| 2026-08-02 | Claude Code | W2 D1: shared srx_common auth module - fail-closed ENV handling, Cognito JWKS validation, cognito:groups RBAC dependency; 29 tests |
| 2026-08-02 | Claude Code | W2 D2: User Service - /v1/users/me, admin directory listing, self-vs-admin read rules, in-memory vs Cognito repositories; 14 tests |
| 2026-08-02 | Claude Code | W2 D3: Order Service - Pydantic validation, server-side totals, Decimal money, DynamoDB write, SQS command publish, userId-index reads; 27 tests |
| 2026-08-02 | Claude Code | W2 D4: idempotency - per-user scoped keys, payload fingerprinting, conditional-write claim, release on failure; 16 further tests |
| 2026-08-02 | Claude Code | W2 D5: saga compensation receiver, order-events queue + SNS filter policy in messaging.tf and localstack-init; found and fixed missing GSIs in the local seed script |
| 2026-08-02 | Claude Code | W3 D1: inventory stock model, atomic conditional-UPDATE reservation, CHECK constraint; 16 tests |
| 2026-08-02 | Claude Code | W3 D2: tenacity retry inside pybreaker circuit breaker; business refusals excluded from both; 9 tests |
| 2026-08-02 | Claude Code | W3 D3: saga outcome publisher (order-confirmed/order-rejected), SQS consumer, admin stock endpoints; 21 tests |
| 2026-08-02 | Claude Code | W3 D4: Product Service - TTL cache with X-Cache header, category GSI reads, admin CRUD; 29 tests |
| 2026-08-02 | Claude Code | W3 D5: full local saga demo against LocalStack + Postgres, both directions verified; scripts/saga-demo.sh |
| 2026-08-03 | Claude Code | W4 D1: notification Lambda with Powertools Logger/Tracer/Idempotency, SES identity in Terraform, event-carried userEmail through the saga; 14 tests |
| 2026-08-03 | Claude Code | W4 D2: Lambda Terraform (ARM64 + Powertools layer), SNS filter incl. loadTest exclusion, stock-reconciliation Lambda + enabled Asia/Colombo schedule, least-privilege Lambda IAM; 12 tests |
| 2026-08-03 | Claude Code | W4 D3: Powertools formatter adopted across all four Fargate services so services and Lambdas emit one log shape; correlation id injected via logging filter |
| 2026-08-03 | Cursor Agent | W5 chunk 1 commit 1: EventBridge Pipes — DDB Streams → orders event bus, native filter on MODIFY + terminal status, dedicated pipes IAM role; pipes.tf + outputs |
| 2026-08-03 | Cursor Agent | W5 chunk 1 commit 2: WebSocket API v2 + REQUEST Lambda authorizer validating Cognito JWT off ?token=; authorizer Lambda (8 tests) with offline JWKS stub |
| 2026-08-03 | Cursor Agent | W5 chunk 1 commit 3: connect / disconnect / push Lambdas — connect writes (connectionId, userId, ttl); disconnect idempotent delete; push scans by userId, prunes 410 GoneException inline, re-raises 5xx for EventBridge retries (15 tests) |
| 2026-08-03 | Cursor Agent | W5 chunk 1 commit 4: backlog 33 IAM — PutItem / DeleteItem / Scan-Query-Delete on websocket-connections split per Lambda; execute-api:ManageConnections scoped to this WSS API's stage ARN |
| 2026-08-03 | Cursor Agent | W5 chunk 1 commit 5: EventBridge rule + target + invoke permission — routes order.status-changed events off the bus into the push Lambda; terraform validate green |
| 2026-08-03 | Cursor Agent | Lambda cross-platform packaging fix: `pyjwt[crypto]` needs a Linux ARM64 wheel bundled into the authorizer zip (dev host is Windows) — added `scripts/build-lambda-packages.ps1` that runs `pip install --platform manylinux2014_aarch64 --only-binary=:all: --target infra/build/ws-authorizer-src`, switched the archive_file to `source_dir` |
| 2026-08-03 | Cursor Agent | Terraform correctness pass discovered by real API: (a) WS authorizer rejects `authorizer_result_ttl_in_seconds` and `authorizer_payload_format_version` (removed with comment); (b) WS stage `access_log_settings` requires account-level API GW CloudWatch role (added `aws_api_gateway_account` + `AmazonAPIGatewayPushToCloudWatchLogs` role) — one apply retry each |
| 2026-08-03 | Cursor Agent | **CW-4 + CW-5 live evidence window on real AWS.** Applied `live=true`, seeded Cognito test users (`logithsivakumar07@gmail.com` customer, `admin@example.com` admin) with `admin-set-user-password` from a shell env var, placed real orders, captured raw evidence: SES delivered email (MessageId `0102019fc88697ec-…`), idempotency wrapper returned cached MessageId on replay, reconciliation Lambda returned `stuck:0`, WebSocket authorizer allowed a valid Cognito ID token, live push arrived at the client (`{"type":"order.status-changed","orderId":"ord-f6c9745b753a","status":"CONFIRMED"}`), invalid token → HTTP 403 at handshake. Runbooks `docs/cw-4-runbook.md` and `docs/cw-5-runbook.md` + raw log `docs/cw-4-5-session-evidence.md` |
