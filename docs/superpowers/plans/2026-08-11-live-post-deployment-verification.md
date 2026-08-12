# Live Post-Deployment Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce evidence-backed verification of the deployed SmartRetailX distributed application and classify every area as PASS, PASS WITH WARNINGS, FAIL, or BLOCKED without fabricating results.

**Architecture:** Use read-only AWS APIs for infrastructure, configuration, logs, metrics, and data-flow evidence; use bounded application requests only for the explicitly authorized functional and performance checks. Store conclusions in two assignment-facing documents, distinguish configuration evidence from live behavior, redact credentials, and never alter infrastructure merely to make a check pass.

**Tech Stack:** AWS CLI v2, CloudWatch Logs/Metrics, ECS Fargate, API Gateway HTTP/WebSocket APIs, Cognito, DynamoDB, Aurora PostgreSQL, Lambda, EventBridge Pipes, SQS/SNS, CloudFront/WAF, browser-controlled PKCE verification, k6, GitHub Actions, Markdown.

## Global Constraints

- AWS account `322551984077`, region `eu-west-1`.
- Terraform context remains `environment_name=baseline`, `live=true`, `enable_grafana=false`.
- Do not run Terraform apply/destroy/import/state mutation/backend migration.
- Do not change AWS infrastructure or deploy stale repository artifacts.
- Use read-only AWS commands except the explicitly requested controlled application requests and safe k6 HTTP traffic.
- Never print, save, document, or screenshot JWTs, passwords, AWS key material, or secret values.
- Do not run the ECS task-stop, poison-message, Aurora failover, extreme stress, or DR scripts against baseline.
- Mark credential-dependent or externally configured checks BLOCKED when evidence is unavailable.

---

### Task 1: Capture live infrastructure health

**Files:**
- Create: `docs/final-live-verification.md`

**Interfaces:**
- Consumes: Read-only ECS, ELBv2, EC2, RDS, DynamoDB, Pipes, Lambda, API Gateway, CloudFront, WAF, CloudWatch, and IAM APIs.
- Produces: Timestamped health evidence for every runtime resource and Grafana-disabled proof.

- [ ] Query all four ECS services for desired/running/pending counts, deployment rollout state, task definition, circuit breaker, and recent events.
- [ ] Resolve each service target group and query target health.
- [ ] Query ALB, NAT, Aurora, DynamoDB/outbox, Pipe, Lambda aliases/event mapping, WebSocket stage, CloudFront, WAF logging, dashboard, and Grafana runtime absence.
- [ ] Record exact observed statuses and classify deviations without mutation.

### Task 2: Inspect recent application logs

**Files:**
- Modify: `docs/final-live-verification.md`

**Interfaces:**
- Consumes: The eleven ECS/Lambda CloudWatch log groups and recent log events.
- Produces: Error-pattern counts and examples classified as startup warning, resolved transient, active defect, or no evidence.

- [ ] Enumerate log streams and query a bounded recent window for `ERROR`, `Exception`, `Traceback`, access/resource errors, database/migration/timeout failures, OTel failures, serialization failures, and Pydantic failures.
- [ ] Inspect surrounding events for every match before classifying it.
- [ ] Redact tokens, credentials, and sensitive request data from recorded evidence.

### Task 3: Verify SPA and Cognito PKCE

**Files:**
- Modify: `docs/final-live-verification.md`

**Interfaces:**
- Consumes: `https://dh46kn0l8se6n.cloudfront.net`, deployed static assets/config, Cognito client `270ec376iist6pggvkukqdtjsc`, and the Hosted UI.
- Produces: Asset/config comparison, OAuth client proof, group proof, and browser-flow result.

- [ ] Fetch the deployed HTML, asset references, and `/config.json`; compare safe runtime values with repository output and identify stale deployment separately.
- [ ] Query the Cognito client, domain, and groups for code grant, public-client, callback/logout, scope, and PKCE compatibility evidence.
- [ ] Use the browser to follow SPA to Hosted UI and complete login only if an existing legitimate signed-in session or user-entered credentials are available.
- [ ] Record navigation/authentication outcome without capturing tokens or browser storage.

### Task 4: Verify REST, RBAC, outbox, inventory saga, and idempotency

**Files:**
- Modify: `docs/final-live-verification.md`

**Interfaces:**
- Consumes: Canonical `/v1` API, legitimate customer/admin access tokens when available, DynamoDB records, CloudWatch logs/metrics, SQS attributes, and read-only Aurora evidence where connectivity permits.
- Produces: Status/latency/request-ID evidence and a timestamped causal trace for one controlled order.

- [ ] Verify public/no-token endpoint behavior and explicitly confirm unauthenticated protected endpoints return 401.
- [ ] With legitimate tokens, verify customer/admin reads and customer-to-admin 403/admin-allowed behavior.
- [ ] Create exactly one controlled order with a unique idempotency key and record non-secret identifiers/timestamps.
- [ ] Trace order, idempotency, outbox, publisher, SQS, inventory, event outcome, and final order state through read-only data/log queries.
- [ ] Repeat the same request with the same key and prove no duplicate logical order, event, or stock decrement; use a second key only when safe evidence and credentials permit.

### Task 5: Verify WebSocket routing

**Files:**
- Modify: `docs/final-live-verification.md`

**Interfaces:**
- Consumes: WebSocket `prod` stage, custom authorizer, Lambda aliases, connections table/index, EventBridge/Pipe/rule target, and legitimate user token(s).
- Produces: Connect/write/push/disconnect evidence and user-isolation result or a precise BLOCKED reason.

- [ ] Verify route/integration/authorizer/alias topology and the `userId-index` configuration.
- [ ] Connect with a legitimate token, confirm the connection row, observe an order-status push, and confirm disconnect cleanup.
- [ ] Perform two-user isolation only when two valid users are available; otherwise mark isolation live proof BLOCKED while recording scoped implementation evidence.

### Task 6: Verify observability, performance, and resilience

**Files:**
- Create generated evidence under: `evidence/live-verification/2026-08-11/`
- Modify: `docs/final-live-verification.md`

**Interfaces:**
- Consumes: Dashboard body/metrics, alarms, log groups, X-Ray traces, k6 scripts, CloudWatch ECS/API metrics, and resilience configuration.
- Produces: Widget/alarm/trace evidence, safe machine-readable k6 summaries, and configured-vs-live-tested resilience classification.

- [ ] Validate every dashboard widget definition and query the backing metric availability; classify all alarms.
- [ ] Query X-Ray/ADOT evidence and claim tracing only if a real trace exists.
- [ ] Inspect k6 scripts and run bounded smoke/normal/concurrency profiles only with a current token and safe catalogue-dominant workload.
- [ ] Capture k6 summary JSON plus before/during ECS CPU/memory and API metrics.
- [ ] Verify circuit breaker, target alarms, redrive/retry/DLQ, autoscaling, Multi-AZ, backups, and PITR configuration.
- [ ] Do not run baseline task-stop, poison-message, Aurora failover, extreme stress, or DR mutations; mark those live experiments not executed.

### Task 7: Verify CI/CD readiness

**Files:**
- Modify: `docs/final-live-verification.md`

**Interfaces:**
- Consumes: All workflow YAML, Terraform OIDC roles/trust, release/deploy scripts, and any available GitHub run evidence.
- Produces: Structural pipeline matrix and external GitHub environment prerequisites.

- [ ] Map PR CI, release, Terraform plan, promotion environments, production approval, exact-digest deployment, rollback, and saved-plan controls.
- [ ] Verify OIDC role existence/trust without printing credentials and confirm workflows do not require long-lived AWS keys.
- [ ] Distinguish repository structure from actual workflow-run proof and list required environment reviewers/secrets/variables.

### Task 8: Produce assignment evidence and classification

**Files:**
- Complete: `docs/final-live-verification.md`
- Create: `docs/assignment-evidence-checklist.md`

**Interfaces:**
- Consumes: Every result and evidence location from Tasks 1-7.
- Produces: Assignment-quality verification report, screenshot/report/viva checklist, complete issue list, and one final classification.

- [ ] Build the required `AREA | RESULT | EVIDENCE | ISSUE` table for all fifteen areas.
- [ ] For every assignment requirement, provide implementation, live status, evidence, screenshot, report section, and viva talking point.
- [ ] For each failure, state root cause evidence, smallest proposed fix, whether AWS mutation/redeployment is required, and wait for approval.
- [ ] Run a final source/evidence audit, verify no secrets were written, and classify exactly `PASS`, `PASS WITH WARNINGS`, or `FAIL`.
