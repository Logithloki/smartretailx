# SmartRetailX assignment evidence coverage

This document summarizes the atomic requirement matrix in `docs/final-assignment-completion-audit.md`. Counts cover the **81 technical requirements in Tasks 1–8 only**. Submission deliverables are listed separately because a missing PDF or slide deck is not a missing AWS feature.

## Counting method

- **Complete** = either `✅ COMPLETE — IMPLEMENTED + EVIDENCED` or `✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement`.
- **Needs evidence/report only** = either `🟢 IMPLEMENTED — NEW SCREENSHOT OPTIONAL` or `🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED`.
- **Actually missing** = `🔴 ACTUALLY MISSING` and requires new application functionality.
- Historical screenshots and raw AWS session records count when they visibly/exactly prove a requirement and the current implementation retains that behavior.

## Coverage by task

| Task | Atomic requirements | Complete | Needs evidence/report only | Actually missing |
|---|---:|---:|---:|---:|
| Task 1 — cloud architecture | 12 | 11 | 1 | 0 |
| Task 2 — microservices/APIs | 9 | 9 | 0 | 0 |
| Task 3 — security | 11 | 8 | 3 | 0 |
| Task 4 — real-time/distributed data | 12 | 8 | 2 | 2 |
| Task 5 — resilience | 10 | 9 | 1 | 0 |
| Task 6 — performance | 11 | 9 | 2 | 0 |
| Task 7 — observability | 7 | 5 | 2 | 0 |
| Task 8 — testing | 9 | 7 | 2 | 0 |
| **Total** | **81** | **66** | **13** | **2** |

No completion percentage is used as a mark prediction. The atomic count is a traceability device, not a claim that every item carries equal marks.

## Task 1 — cloud architecture

### Complete requirements

- T1.1–T1.11: cloud-native design, Docker, ECS Fargate, Lambda, managed databases, event-driven design, HA, multi-region consideration, scalability, resilience and maintainability.
- Current AWS still contains the primary deployment and the products-only `ap-south-1` Global Table replica.

### Partial/evidence requirements

- T1.12 combines cost evidence and professional architecture/data-flow diagrams. Cost-saving mechanisms are implemented, but the final report needs real Cost Explorer analysis and the diagram must be corrected/exported.
- The diagram currently overclaims some designed features as live. Fixing labels is a documentation action, not a reason to build a second region.

### Actually missing requirements

- None.

## Task 2 — microservices and APIs

### Complete requirements

- T2.1–T2.9 are complete: four loosely coupled services, REST, `/v1`, API Gateway, secure private integration, event communication, OpenAPI and IaC deployment/configuration.
- `21-route-matrix-200.png`, `43-api-gateway-routes.png` and the current read-only route/authorizer inventory are especially strong.

### Partial/evidence requirements

- None.

### Actually missing requirements

- None. A payment service or fifth core microservice is not mandated; the brief requires at least three.

## Task 3 — security

### Complete requirements

- T3.1, T3.3–T3.8 and T3.11: Cognito authentication, JWT, RBAC, secured APIs, encryption, secrets/least privilege, and real API-security evidence.
- `22-rbac-403.png` genuinely shows an authenticated customer receiving 403.
- `52-rbac-403.png` visibly shows unauthenticated 401 and is evidence-labelling debt, not an RBAC implementation gap.

### Partial/evidence requirements

- T3.2: current OAuth code + PKCE is implemented/deployed and the P0 record proves the redirect; a current visual callback sequence is worth capturing.
- T3.9: final GDPR/PCI scope discussion is incomplete. Do not claim implemented payment processing, a live erasure cascade or customer-managed KMS everywhere.
- T3.10: add an explicit distributed-security/Zero-Trust/API/federation risk analysis to the report.

### Actually missing requirements

- None at application-infrastructure level.

## Task 4 — real-time and distributed data

### Complete requirements

- T4.1, T4.2, T4.5–T4.9 and T4.11: stock/order synchronization, SQS/SNS/EventBridge/Pipes/WebSocket, asynchronous pub/sub, consistency controls and the choreographed Saga.
- The `23`–`26` sequence proves confirmed/rejected outcomes and diagnosis; CW-5 raw evidence proves the authenticated live WebSocket path.
- Transactional outboxes are a newer safety improvement verified through current code/Terraform/AWS; they do not invalidate the earlier functional proof.

### Partial/evidence requirements

- T4.10: expand the eventual-consistency analysis in the final report.
- T4.12: explain CQRS applicability and distributed-transaction trade-offs. Full CQRS implementation is not required by the wording; the brief asks for discussion.

### Actually missing requirements

- T4.3 delivery tracking updates.
- T4.4 real-time pricing/promotions.

These are the only two clear new application-feature gaps found by the audit.

## Task 5 — resilience

### Complete requirements

- T5.1–T5.6 and T5.8–T5.10: retries, application/deployment circuit breakers, load balancing, autoscaling, two-AZ architecture, DR planning, failure/HA explanation, RTO/RPO targets and supporting evidence.
- The current baseline is deliberately demo-sized with one Aurora writer. Do not describe it as two database instances.

### Partial/evidence requirements

- T5.7: DynamoDB PITR and Aurora backup/encryption exist, but a clear restore procedure—and optionally a non-production restore drill—would strengthen the evidence.

### Actually missing requirements

- None. A live active-active region, Aurora Global Database and cross-region AWS Backup are not automatically required by the brief.

## Task 6 — performance

### Complete requirements

- T6.1–T6.9: load, stress, API, concurrency, k6, latency, throughput, CPU and error-rate evidence.
- Historical screenshot `70` visibly records 96,055 requests/checks, 100% successful checks, 0% request failures, 228.613642 requests/second, average 326.91 ms, median 282.98 ms, p90 494.9 ms, p95 623.76 ms, maximum 4.87 s and a 200-VU ceiling over 7m00.2s.
- p99 is not visible and is not claimed.

### Partial/evidence requirements

- T6.10: write the bottleneck/scalability analysis.
- T6.11: turn existing screenshot metrics into a clear report table/graph and interpretation.

### Actually missing requirements

- None. A fresh post-reconciliation k6 run is optional supporting evidence, not proof that performance testing first needs to be implemented.

## Task 7 — observability

### Complete requirements

- T7.1, T7.2, T7.4, T7.6 and T7.7: centralized logs, metrics, alarms, diagnosis and configuration evidence.
- Current AWS has a dashboard, 17/17 alarms in OK, and two recent X-Ray traces.

### Partial/evidence requirements

- T7.3: X-Ray/ADOT is deployed and ingesting; a current trace/service-map screenshot is optional high-value evidence.
- T7.5: the nine-widget CloudWatch dashboard is deployed but lacks a screenshot.

### Actually missing requirements

- None. Grafana is optional because CloudWatch meets the monitoring-dashboard requirement.

## Task 8 — testing

### Complete requirements

- T8.1–T8.4 and T8.6–T8.8: unit, integration, API, historical/manual E2E, suitable frameworks, Postman/OpenAPI and test-output evidence.
- Recorded validation reports 237 Python tests, 8 frontend unit tests and a successful frontend build.
- The latest persisted Playwright JUnit file contains three credential-skipped cases. It must not be described as a passing automated E2E run; the historical SPA/Saga/WebSocket evidence supplies the executed E2E proof.

### Partial/evidence requirements

- T8.5: security gates exist and Checkov has a recorded 497-pass result; preserve outputs from Bandit/pip-audit/Trivy or an optional ZAP run.
- T8.9: the CI coverage threshold exists, but save the actual coverage summary/XML and discuss limitations.

### Actually missing requirements

- None.

## Evidence strength

### Strongest evidence already available

1. `21-route-matrix-200.png` — compact authenticated/unauthenticated API contract matrix.
2. `22-rbac-403.png` — genuine authenticated customer 403.
3. `23`–`26` — coherent confirmed/rejected Saga plus stock and CloudWatch logs.
4. `50`–`56` — real Postman 200/201/401/CRUD/inventory/idempotency results.
5. `61`–`65` — authenticated customer/admin SPA, full CRUD, stock and Live Sync.
6. `66`/`67` plus CW-5 raw evidence — Pipes/WebSocket configuration and executed client push.
7. `70-k6-load-summary.png` — high-volume historical real-AWS performance result.
8. `49`, `41`, `43`, `44`, `66`, `69`, `72`, `73` — strong architecture, security and operations configuration.

### Mislabeled or superseded evidence

- `52-rbac-403.png`: definite mislabel; it is 401 authentication-wall evidence.
- `70-k6-load-summary.png`: valid result, but its seven-minute/200-VU shape is stress-like, so “load” is generic rather than precise.
- `60-cognito-sign-in.png`: genuine historical authentication UI, but the current application uses Hosted UI code + PKCE.
- `34-s3-spa-bucket.png`: genuine pre-P0 bucket state, not proof of the current complete SPA artifact.
- `40`, `47`, `68`, `73`: valid historical states whose resource counts/health have since improved or changed.

## Exact remaining work classification

### A. Must do before submission

- Implement and demonstrate delivery tracking and real-time pricing/promotions.
- Write/export the final 4,000–5,000-word report with required sections, Harvard references, diagrams, analysis, limitations and evidence traceability.
- Correct/export the architecture/data-flow diagram; label designed versus deployed features accurately.
- Create the 10–15 slides, clean source ZIP and final README/demo instructions.
- Make redacted report copies of token/PII-bearing screenshots without touching originals.
- Capture the current Hosted UI PKCE and authenticated callback/SPA sequence because the login mechanism fundamentally changed after screenshot `60`.

### B. Should do if time

- Capture the current dashboard, X-Ray map/trace and products Global Table replica view.
- Save coverage and security-tool outputs.
- Run a bounded current k6 smoke/load, Playwright and Newman suite when credentials and a safe environment are available.
- Capture one successful GitHub Actions pipeline after commit/push and, optionally, actual ECS scale-out/recovery or a non-production restore drill.

### C. Optional / outside assignment scope

- Full second-region deployment, active-active DR, Aurora Global Database, Route 53 failover/custom domain.
- AWS Backup cross-region vault/copy unless retained as a claimed live feature.
- Grafana runtime, EKS, Kafka/MSK, Step Functions, ElastiCache, or a payment microservice.
- Destructive baseline chaos testing, another huge k6 run, or a Terraform state/module migration solely for production perfection.

## Deliverable readiness

| Deliverable area | State |
|---|---|
| Technical source/IaC/tests | Substantially complete; two Task 4 features remain |
| Evidence library | Extensive and genuine; needs curation/redaction, not wholesale recreation |
| Final report/PDF | Not yet present |
| Slides | Not yet present |
| Submission ZIP | Not yet assembled |
| Harvard references | Not yet assembled into final report |
| AI-use log | Present |

## Recommendation

Do not reopen the whole AWS architecture. Finish the two narrow Task 4 features, then shift decisively to the corrected diagram, report, evidence appendix and slides. Fresh AWS captures should be targeted and low-risk; most existing functional evidence remains academically valid.
