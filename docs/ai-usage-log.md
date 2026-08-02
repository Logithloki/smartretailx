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
