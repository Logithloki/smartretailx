# SmartRetailX final assignment completion audit

Audit date: 11 August 2026  
Repository/branch: `smartretailx` / `codex/production-readiness`  
AWS scope: account `322551984077`, primary region `eu-west-1`  
Audit mode: evidence-first and read-only. No deployment, data mutation, Terraform apply/destroy/state action, user creation, order creation, product creation, or k6 execution was performed.

## Executive conclusion

The earlier conclusion that large parts of the assignment were “blocked” was too broad. It conflated “not re-exercised with credentials on 11 August” with “not implemented or never demonstrated.” The repository contains 53 visually inspected screenshots, raw real-AWS session records, current source/Terraform, test suites, and a live AWS deployment. Together they prove most of Tasks 1–8.

Using the 81 atomic technical requirements defined in this audit:

- 47 are complete with current implementation and evidence.
- 19 are complete using genuine historical real-AWS evidence that the current implementation still supports.
- 2 are implemented and would benefit only from an optional current screenshot.
- 11 are substantially implemented/addressed but need stronger evidence or final-report analysis.
- 2 application features are actually missing: delivery tracking and real-time pricing/promotions.

Therefore 66/81 requirements are already evidence-ready, 13/81 are implementation/design-complete or substantially addressed but need evidence/report work, and only 2/81 require new application implementation. Deliverables such as the final PDF, slides, and submission ZIP are tracked separately and are not misrepresented as AWS implementation gaps.

## Authority and classification rules

The authoritative brief is `D:\APIIT\ECADWP_2\COMP60010-ECDWA2_Assignment_v20260510.docx`. Tasks 1–8 and its deliverables were extracted directly from its OOXML structure. DOCX page rendering was unavailable because LibreOffice is not installed, so no invented page numbers are used.

Statuses mean exactly:

- ✅ COMPLETE — IMPLEMENTED + EVIDENCED
- ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement
- 🟢 IMPLEMENTED — NEW SCREENSHOT OPTIONAL
- 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED
- 🔴 ACTUALLY MISSING
- ⚪ OPTIONAL / OUTSIDE ASSIGNMENT SCOPE

Historical evidence remains valid unless the demonstrated mechanism fundamentally changed. A later safety improvement—such as adding transactional outboxes—does not erase earlier proof that the Saga completed on AWS.

## Evidence inventory

| Location | Audited inventory | Evidential value |
|---|---:|---|
| `assignment-screenshots/` | 53 PNG files, all opened and inspected at original resolution | AWS infrastructure, APIs, RBAC, Saga, SPA, real-time UI, observability and performance |
| `evidence/` | 1 JSON record | Correctly records that k6 was not rerun on 11 August; does not invalidate historical k6 evidence |
| `docs/` | 23 root Markdown files, Draw.io architecture source, guide/plans/audits | Raw session records, run outcomes, architecture, cost, recovery and validation evidence |
| `postman/` | Collection, secret-free environment template and README; 15 request/test entries | API, authentication, RBAC, CRUD, validation, idempotency and Saga contracts |
| `k6-tests/` | 6 executable profiles plus shared config and README | Smoke, load, concurrency, stress, spike and cache-busting stress tests |
| `tests/architecture/` | 7 files; parameterized safety and convergence contracts | Terraform safety, live/park, route, release, Cognito and dashboard contracts |
| `services/` | 4 FastAPI services, 8 Lambda components, common library; 228 visible Python test functions | Current implementation and automated component/integration evidence |
| `frontend/` | React/Vite SPA, 8 unit tests and 3 Playwright journeys | Full customer/admin UI, PKCE configuration and E2E specification |
| `.github/workflows/` | 17 workflow files | Structurally implemented CI/CD; no GitHub-run screenshot exists |
| `infra/` | Split Terraform root, five environment profiles, saved plans/text audits | Current IaC and reconciliation evidence; state/secret files were not read |

Persisted Playwright JUnit output contains three skipped tests because live credentials were absent; it is not a passing E2E run. Manual historical AWS/UI evidence independently proves the customer and administrator journeys.

## Current AWS read-only snapshot

Captured on 11 August 2026 without invocation or mutation:

| Area | Current observation |
|---|---|
| ECS | Cluster `smartretailx-cluster` ACTIVE; order, inventory, product and user services each desired/running `1/1`, zero pending; Container Insights enabled |
| Tasks | Four current task families are ARM64/Linux, each with application and ADOT containers and a distinct task role |
| Network | VPC `10.0.0.0/16`; six public/private/data subnets across `eu-west-1a` and `1b`; data route table has no default route; ALB is active and internal in two AZs |
| APIs | HTTP and WebSocket APIs exist; all eight `/v1` HTTP routes use the JWT authorizer; WebSocket `$connect` uses a custom request authorizer |
| Identity | Cognito pool, `admin`/`customer` groups, active Hosted UI domain and public SPA client exist; client uses OAuth code flow with registered CloudFront callbacks |
| Data | Five DynamoDB tables exist; orders PITR is enabled; products stream uses `NEW_AND_OLD_IMAGES` and its `ap-south-1` replica is ACTIVE |
| Aurora | `smartretailx-inventory` is available on Aurora PostgreSQL 16.14, encrypted, with one writer and an active RDS-managed master secret |
| Messaging | Four SmartRetailX SQS queues, two SNS topics and the `smartretailx-order-status` Pipe (RUNNING) exist |
| Lambda | Eight SmartRetailX functions exist; the seven application/event functions are Python 3.12 ARM64 with active tracing where configured |
| Edge | S3 SPA bucket exists; CloudFront `E1LFQ5YHORDZ6P` is enabled/deployed with S3 and API origins; WAF is attached |
| Operations | Four ECS scaling targets are min 1/max 5 at 70% CPU; `smartretailx-operations` dashboard exists; 17/17 alarms are OK; two X-Ray traces existed in the preceding 24 hours |
| Grafana | No Grafana ECS service is active. Task definition revision 4 and its Secrets Manager secret remain, matching the optional-runtime contract |

The baseline Aurora deployment has one writer. Aurora storage is multi-AZ, but this audit does not claim that a second database compute instance is currently deployed.

## Capability reconciliation

| Capability | Code | Terraform | AWS deployed | Screenshot/result | Finding |
|---|---|---|---|---|---|
| Docker / four microservices | Four Dockerfiles and Compose | Four ECS task definitions/services | Yes, four healthy services | `15`, `40`, `41` | Complete |
| ARM64 / ECR / Fargate | Container builds and workflow | ARM64 runtime, immutable ECR, ECS Fargate | Yes | `16`, `41`, `42` | Complete |
| API Gateway / VPC Link / internal ALB | `/v1` FastAPI routes | HTTP API, VPC Link, internal ALB | Yes | `10`, `21`, `43`, `49` | Complete |
| S3 / CloudFront / WAF SPA edge | React build/runtime config | Private S3, OAC, CloudFront, WAF | Yes | `34`, `37`, `38`, `61`–`65` | Complete; `34` predates P0 redeploy |
| Cognito Hosted UI / PKCE | `react-oidc-context`, code flow | Pool, domain, public client | Yes | P0 verification document; `60` is old direct-auth UI | Current mechanism implemented; fresh current flow screenshot recommended |
| JWT / groups / backend RBAC | Shared fail-closed verifier and role dependencies | JWT authorizer and Cognito groups | Yes | `21`, `22`, `44`, `46`, `54`, `64` | Complete historically/current configuration |
| Encryption / secrets / IAM | Secret injection and least-privilege clients | RDS-managed secret, encrypted stores, per-service roles | Yes | `12`, `16`, `32`, `36`, `38` | Complete; describe KMS claims precisely |
| GitHub OIDC | Workflow role assumptions | OIDC provider and scoped roles | Yes | No GitHub run screenshot | Implemented; live execution evidence absent |
| Order transactional outbox | Atomic order/outbox write | Outbox table/stream, publisher Lambda/ESM/DLQ | Yes | Current AWS audit plus service tests | New safety mechanism; code/Terraform/AWS evidence |
| Inventory inbox/outbox | SQL inbox, stock and outcome transaction | Aurora, queues/topic and task IAM | Yes | Tests plus historical Saga logs | Current implementation verified; internal SQL rows not screenshot-tested after reconciliation |
| Saga / idempotency / retry / breaker | Choreography, idempotency, tenacity/pybreaker | Queues, SNS filter, DLQs, alarms | Yes | `23`–`27`, `51`, `53`, `56`, raw CW-4/5 evidence | Complete historical function plus current hardening |
| Pipes / WebSocket status | User-indexed connections and push Lambda | Stream, Pipe, bus/rule, WS API | Yes | `63`, `66`, `67`, raw CW-5 live client record | Complete historical real-AWS path |
| Notification / reconciliation | Powertools idempotent handlers | Lambda, SNS and Scheduler | Yes | CW-4 raw SES/X-Ray results, `68` | Complete historical real-AWS execution |
| Autoscaling / rollback | Deployment-safe services | Scaling 1–5, ECS circuit breakers/alarms | Yes | `72`; current read-only state | Configured and evidenced; actual scale-out screenshot optional |
| Backup / persistence | Idempotent persistence logic | DynamoDB PITR, Aurora backups/encryption | Yes | `12`, `36`, current AWS | Core backup strategy exists; do not claim live cross-region AWS Backup |
| Logs / metrics / tracing / alerts | Structured logs and OTel hooks | ADOT, logs, dashboard, 17 alarms, X-Ray | Yes | `26`, `69`, `71`, `73`; current two traces | Complete; dashboard/service-map screenshot optional |
| Tests | Python, Vitest, Playwright, Postman, k6 | CI jobs | Local/historical AWS as applicable | 237-test validation record, screenshots, Postman and k6 | Broad coverage; latest Playwright artifact is skipped, not passed |
| Enterprise CI/CD | Release/promotion/production YAML | OIDC IAM and environment profiles | IAM exists; workflow runs not verified | No CI/CD screenshot | Structurally implemented, not live-executed |
| Multi-region / DR | DR timing script and design | Products Global Table replica | Product replica active | Current AWS; no Global Table screenshot | Brief’s “address multi-region” is met; full second-region stack is not required or claimed |
| Delivery tracking | No service/model/UI/event path | None | No | None | Actually missing |
| Real-time pricing/promotions | Product CRUD has static price only | None | No | None | Actually missing |

## Master Tasks 1–8 matrix

### Task 1 — cloud architecture

| Req ID | Assignment requirement | Implemented? | Current code/Terraform | Real AWS deployed? | Screenshot/evidence | Historical or current | Tested? | Status | Actual remaining action |
|---|---|---|---|---|---|---|---|---|---|
| T1.1 | Comprehensive cloud-native AWS architecture | Yes | Full Terraform root and architecture source | Yes | `30`–`49`, architecture Draw.io | Current + historical | Architecture contracts | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Use corrected diagram in report |
| T1.2 | Containerised application | Yes | Four Dockerfiles/Compose | Yes | `41`, `42` | Current | Python/Compose gates | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T1.3 | Managed container compute (ECS/Fargate or EKS) | Yes | ECS Fargate services | Yes | `15`, `40`, `41` | Current | Health/deployment checks | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T1.4 | Serverless/Lambda use | Yes | Eight Lambda components | Yes | `68`, CW-4/5 logs | Both | Handler tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T1.5 | Cloud-managed databases | Yes | DynamoDB + Aurora | Yes | `12`, `36`, current AWS | Current | Repository/integration tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T1.6 | Event-driven architecture | Yes | Outboxes, SQS/SNS/EventBridge/Pipes | Yes | `26`, `47`, `48`, `66` | Both | Event/Saga tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T1.7 | High availability | Yes, demo-sized | Two-AZ network/Fargate/ALB; Aurora storage HA | Yes | `10`, `31`, `36`, `49` | Current | Safety/config checks | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | State single-writer limitation accurately |
| T1.8 | Multi-region addressed | Yes | ADR/pilot-light design; product replica | Products replica only | Current AWS replica; diagram | Current | Terraform contract | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Do not claim a full second-region stack |
| T1.9 | Scalability | Yes | Autoscaling, on-demand DDB, Serverless Aurora | Yes | `70`–`72` | Both | k6 historical/config tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Optional scale-out recapture |
| T1.10 | Resilience | Yes | Retry, DLQ, circuit breaker, PITR | Yes | `12`, `26`, `72`, `73` | Both | Resilience tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T1.11 | Maintainability | Yes | Four bounded services, IaC, migrations, CI | Mostly | Code/docs/workflows | Current | Quality gates | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Explain boundaries in report |
| T1.12 | Cost efficiency and professional architecture/data-flow diagrams | Substantially | ADRs/live toggle/Draw.io | Cost controls deployed | `00`, cost ledger, Draw.io | Mixed | Contract tests | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Correct diagram overclaims, export it, and add real Cost Explorer analysis |

### Task 2 — microservices and APIs

| Req ID | Assignment requirement | Implemented? | Current code/Terraform | Real AWS deployed? | Screenshot/evidence | Historical or current | Tested? | Status | Actual remaining action |
|---|---|---|---|---|---|---|---|---|---|
| T2.1 | Loosely coupled microservices | Yes | Separate services/data/event contracts | Yes | Architecture + `40` | Current | Integration tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T2.2 | At least three working microservices | Yes, four | Order/inventory/product/user | Yes | `15`, `40` | Current | 228 visible Python tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T2.3 | REST APIs | Yes | FastAPI routers | Yes | `21`, `43`, `50`–`56` | Both | Postman/service tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T2.4 | API versioning | Yes | Canonical `/v1` routes | Yes | `21`, `43` | Current | OpenAPI/route contracts | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T2.5 | API Gateway | Yes | HTTP API v2 | Yes | `43`, `44` | Current | Route contracts | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T2.6 | Secure service-to-service connectivity | Yes | Private ALB/VPC Link/SG scoping | Yes | `10`, `32`, `49` | Current | Terraform tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T2.7 | Event queue/bus communication | Yes | SQS, SNS, EventBridge, Pipes | Yes | `47`, `48`, `66` | Both | Event/Saga tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T2.8 | Swagger/OpenAPI documentation | Yes | FastAPI-generated schemas | Runtime available behind auth | OpenAPI contract tests | Current | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Include schema excerpt/link in appendix |
| T2.9 | Deployment/configuration | Yes | Terraform, Docker, runtime config, workflows | Yes baseline | Audits and `41`–`49` | Current | Validation records | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |

### Task 3 — security

| Req ID | Assignment requirement | Implemented? | Current code/Terraform | Real AWS deployed? | Screenshot/evidence | Historical or current | Tested? | Status | Actual remaining action |
|---|---|---|---|---|---|---|---|---|---|
| T3.1 | Authentication | Yes | Cognito integration | Yes | `45`, `50`, `60`–`65` | Historical + current configuration | Auth tests | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Replace obsolete direct-auth login shot for final report |
| T3.2 | OAuth2 authorization code + PKCE | Yes | OIDC client/config | Yes | P0 live redirect record | Current | 2 auth-config tests | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Capture Hosted UI request and post-callback SPA because the old UI used a different mechanism |
| T3.3 | JWT validation | Yes | Fail-closed JWKS verifier | Yes | `21`, `44`, `50` | Both | Extensive negative tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Redact token fragment in report copy of `50` |
| T3.4 | Role-based access control | Yes | Exact Cognito-group dependencies | Yes | `22` true 403; `54`, `64` admin | Historical + current configuration | RBAC tests | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Relabel `52` as 401 auth-wall evidence |
| T3.5 | Secure APIs | Yes | Auth middleware, Pydantic, WAF | Yes | `21`, `38`, `44` | Current | Route/security tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T3.6 | Encryption in transit | Yes | HTTPS/WSS-only production config | Yes | CloudFront/API/WS evidence | Current | Config tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | State default-certificate limitations accurately |
| T3.7 | Encryption at rest | Yes | S3/DDB/Aurora/ECR encryption | Yes | `12`, `16`, `36`, `42` | Current | Terraform checks | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Say AWS-managed encryption where applicable, not blanket CMK |
| T3.8 | Secrets management and least privilege | Yes | RDS-managed secret, ECS secrets, scoped roles | Yes | Current AWS/task-role audit | Current | IaC/security tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T3.9 | GDPR/PCI considerations | Partly documented | Data-residency and no-card-data design | Design, not a payment system | Diagram/ADRs | Current design | N/A | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Write precise compliance discussion; remove unsupported erasure/rotation claims |
| T3.10 | Distributed security risks, Zero Trust, API best practice, federation | Substantially | Private ingress, fail-closed auth, OIDC federation | Yes | Architecture/workflow/IAM evidence | Current | Security tests | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Add explicit threat/risk analysis to report |
| T3.11 | Authentication-flow/JWT/API-security evidence | Yes | Current implementation supports it | Yes | `21`, `22`, `44`, `50`, `54`, `64` | Historical + current config | Yes | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Use redacted report copies; add current PKCE flow shot |

### Task 4 — real-time and distributed data

| Req ID | Assignment requirement | Implemented? | Current code/Terraform | Real AWS deployed? | Screenshot/evidence | Historical or current | Tested? | Status | Actual remaining action |
|---|---|---|---|---|---|---|---|---|---|
| T4.1 | Real-time stock synchronisation | Yes within order/inventory flow | SQS consumer and Aurora transaction | Yes | `25`, `26`, `55`, `65` | Historical + current wiring | Saga/stock tests | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Explain asynchronous stock consistency |
| T4.2 | Customer order-status updates | Yes | DDB stream/Pipe/WS hook | Yes | `23`, `24b`, `63`, CW-5 raw client | Historical + current wiring | WS/Saga tests | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | None |
| T4.3 | Delivery tracking updates | No | No delivery model/service/event/UI | No | None | None | No | 🔴 ACTUALLY MISSING | Implement a minimal event-driven delivery status path and evidence it |
| T4.4 | Real-time pricing/promotions | No | Static product price only | No | None | None | No | 🔴 ACTUALLY MISSING | Implement promotion/price-change propagation and evidence it |
| T4.5 | EventBridge/Kafka/SQS/SNS/WebSocket concepts | Yes | SQS/SNS/EventBridge/Pipes/WS | Yes | `47`, `48`, `66`, `67` | Both | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T4.6 | Real-time data between services | Yes | Order→inventory→order and stream push | Yes | `23`–`26`, CW-4/5 | Historical + current wiring | Yes | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | None |
| T4.7 | Asynchronous communication | Yes | Queues, streams and events | Yes | `26`, `47`, `66` | Both | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T4.8 | Publish/subscribe | Yes | SNS topic/subscriptions and EventBridge | Yes | `48`, raw session evidence | Both | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T4.9 | Consistency mechanisms | Yes | Idempotency, inbox/outbox, terminal-state guards | Yes | `56`, code/tests | Current + historical | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T4.10 | Eventual-consistency discussion | Substantially drafted | Architecture consistency section | N/A | Architecture document | Current | N/A | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Expand trade-offs/anomalies in final report |
| T4.11 | Saga pattern | Yes, choreography | Confirm/reject compensation | Yes | `23`–`26`, `53`, CW-4/5 | Historical + current hardening | Yes | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | None |
| T4.12 | CQRS and distributed-transaction challenges discussion | Distributed transaction addressed; CQRS not yet explicit | Outboxes/read queries provide material | N/A | Architecture docs/tests | Current | N/A | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Discuss CQRS applicability and why full CQRS was not selected |

### Task 5 — resilience

| Req ID | Assignment requirement | Implemented? | Current code/Terraform | Real AWS deployed? | Screenshot/evidence | Historical or current | Tested? | Status | Actual remaining action |
|---|---|---|---|---|---|---|---|---|---|
| T5.1 | Retries | Yes | Tenacity, SQS/Lambda retry | Yes | Code/tests/current config | Current | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T5.2 | Circuit breakers | Yes | Pybreaker plus ECS deployment breaker | Yes | `72`, tests | Both | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Distinguish application/deployment breakers |
| T5.3 | Load balancing | Yes | Internal ALB/target groups | Yes | `10`, `49` | Current | Health checks | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T5.4 | Autoscaling | Yes | ECS target tracking 1–5 | Yes | `72`, current AWS | Current | Config tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Actual scale-out graph optional |
| T5.5 | Multi-AZ architecture | Yes, demo-sized | Six subnets/two AZs, ALB/Fargate | Yes | `31`, `36`, `49` | Current | Terraform checks | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Be clear the DB compute layer is one writer |
| T5.6 | Disaster-recovery planning | Yes, design | ADR-07 and timing script | Product replica only | Diagram/docs/current replica | Current design | Script not executed here | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Label eu-central-1 as designed/not deployed |
| T5.7 | Backup/recovery strategy and procedure | Core strategy yes | DDB PITR, Aurora backups | Yes | `12`, `36`, current AWS | Current | Safety tests | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Document restore procedure; optional non-production restore drill |
| T5.8 | Failure handling, redundancy and HA explanation | Yes | Architecture/resilience docs | Controls deployed | Docs + `26`, `72`, `73` | Both | Resilience tests | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T5.9 | Clear RTO/RPO | Yes, target-based | ADR tiered targets | N/A | Architecture docs/diagram | Current design | Not measured in this audit | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Label targets versus measurements |
| T5.10 | Resilience diagrams/config/screens | Yes | Draw.io/Terraform | Yes | `12`, `31`, `36`, `49`, `72`, `73` | Both | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Correct unsupported diagram labels |

### Task 6 — performance testing

| Req ID | Assignment requirement | Implemented? | Current code/Terraform | Real AWS deployed? | Screenshot/evidence | Historical or current | Tested? | Status | Actual remaining action |
|---|---|---|---|---|---|---|---|---|---|
| T6.1 | Load testing | Yes | k6 profiles | Target was real AWS | `70` | Historical | Executed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Fresh run optional, not mandatory |
| T6.2 | Stress testing | Yes | 7-minute 50→150→200 VU profile exists | Target was real AWS | `70` aligns with the 7-minute 200-VU stress profile | Historical | Executed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Relabel as stress/load evidence |
| T6.3 | API response testing | Yes | k6/Postman | Yes | `21`, `50`–`56`, `70` | Historical | Executed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | None |
| T6.4 | Concurrent users | Yes | concurrent and stress profiles | Yes at test time | `70`: max 199, configured max 200 VUs | Historical | Executed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | None |
| T6.5 | Suitable tool | Yes | k6 | N/A | Scripts/workflow/`70` | Current + historical | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T6.6 | Latency | Yes | k6 trend metrics | N/A | `70`: avg 326.91 ms, median 282.98 ms, p90 494.9 ms, p95 623.76 ms, max 4.87 s | Historical | Executed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Do not invent p99; it is not visible |
| T6.7 | Throughput | Yes | k6 request rate | N/A | `70`: 96,055 requests, 228.613642 req/s | Historical | Executed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | None |
| T6.8 | CPU monitoring | Yes | CloudWatch/Container Insights | Yes | `71` | Historical | Observed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Correlate timestamps in report; no claim of scale-out |
| T6.9 | Error rate | Yes | k6 threshold | N/A | `70`: 0% failed; 96,055 checks passed, 0 failed | Historical | Executed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | None |
| T6.10 | Bottleneck and scalability analysis | Not yet report-ready | Metrics and architecture provide inputs | N/A | `70`–`72` | Historical/current | Partial | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Write analysis of latency tail, low CPU and likely edge/I/O bottlenecks |
| T6.11 | Graphs/reports/screens and analysis | Results exist; analysis incomplete | k6 summary formats | N/A | `70`, `71`, `72` | Historical | Yes | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Convert the visible results into report graphs/table and interpretation |

### Task 7 — observability

| Req ID | Assignment requirement | Implemented? | Current code/Terraform | Real AWS deployed? | Screenshot/evidence | Historical or current | Tested? | Status | Actual remaining action |
|---|---|---|---|---|---|---|---|---|---|
| T7.1 | Centralized logging | Yes | Structured JSON/correlation | Yes | `26`, `69` | Both | Live logs | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T7.2 | Metrics | Yes | Container Insights/dashboard metrics | Yes | `71`, current dashboard | Historical + current | Observed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | None |
| T7.3 | Distributed tracing | Yes | OTel/ADOT/X-Ray | Yes | CW-4 trace record; two current traces | Both | Trace ingestion verified | 🟢 IMPLEMENTED — NEW SCREENSHOT OPTIONAL | Capture X-Ray trace/service map if useful |
| T7.4 | Alerting | Yes | 17 CloudWatch alarms/SNS | Yes | `73`; current 17/17 OK | Both | State verified | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Prefer current all-OK screenshot |
| T7.5 | Monitoring dashboard | Yes | Nine-widget Terraform dashboard | Yes | Current AWS existence; no dashboard screenshot | Current | Contract tests | 🟢 IMPLEMENTED — NEW SCREENSHOT OPTIONAL | Capture dashboard for report |
| T7.6 | Fault diagnosis | Yes | Correlation/logging/alarms | Yes | `26` rejected Saga logs | Historical | Executed | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Use as diagnostic narrative |
| T7.7 | Dashboard/log/trace/alert configuration evidence | Yes | Observability Terraform | Yes | `69`, `71`, `73`, AWS audit | Both | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |

### Task 8 — testing

| Req ID | Assignment requirement | Implemented? | Current code/Terraform | Real AWS deployed? | Screenshot/evidence | Historical or current | Tested? | Status | Actual remaining action |
|---|---|---|---|---|---|---|---|---|---|
| T8.1 | Unit testing | Yes | Broad pytest/Vitest suites | N/A | Validation record: 237 Python and 8 frontend tests | Current record | Passed | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Preserve console/CI output for appendix |
| T8.2 | Integration testing | Yes | Moto/LocalStack/Postgres/Saga tests | N/A | Tests and workflow | Current | Passed in recorded validation | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T8.3 | API testing | Yes | Postman/Newman and service tests | Yes | `21`, `50`–`56`; 15 Postman requests | Historical | Executed manually; automation exists | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Newman run optional after push |
| T8.4 | End-to-end testing | Yes historically/manual; Playwright specified | Current E2E journeys | Yes | `61`–`65`, CW-4/5 sequence | Historical | Manual end-to-end demonstrated; latest Playwright artifact skipped | ✅ COMPLETE — HISTORICAL REAL-AWS EVIDENCE; current implementation still supports requirement | Run Playwright later only for stronger automation evidence |
| T8.5 | Security testing | Substantially | Auth negative tests, Bandit/pip-audit/Trivy/Checkov workflows | Mostly local/config | Checkov 497-pass record; RBAC/401/403 evidence | Mixed | Partial outputs | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Save Bandit/pip-audit/Trivy or ZAP output for appendix |
| T8.6 | Suitable frameworks | Yes | pytest, moto, Vitest, Playwright, Newman, k6 | N/A | Repository inventory | Current | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T8.7 | Postman/Swagger testing | Yes | Collection plus OpenAPI contracts | Yes | Postman screenshots and collection | Both | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | None |
| T8.8 | Test screenshots/outputs | Yes | Output-capable workflows | N/A | API/Saga/k6/CloudWatch screenshots and audits | Both | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Curate appendix |
| T8.9 | Coverage and limitations | Partly | Coverage gate is 60%; limitations recorded | N/A | Validation totals; no committed coverage report | Current | Partial | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Save coverage XML/summary and discuss gaps |

## Deliverables matrix (separate from the 81 technical requirements)

| ID | Brief deliverable | Present now? | Status | Remaining action |
|---|---|---|---|---|
| D1 | 4,000–5,000-word final PDF report | No final report found | 🔴 ACTUALLY MISSING | Write and export the report |
| D2 | Required report sections across Tasks 1–8 | Evidence exists; final synthesis absent | 🔴 ACTUALLY MISSING | Build sections from this matrix and evidence catalogue |
| D3 | Source ZIP containing services/APIs/Docker/IaC/tests/README | Source exists; final ZIP absent | 🔴 ACTUALLY MISSING | Produce clean submission ZIP after final validation |
| D4 | README/deployment instructions | Present but still evolving | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Finalize exact setup/demo/park steps |
| D5 | 10–15 presentation slides for ~15 minutes | Not found | 🔴 ACTUALLY MISSING | Create and rehearse slide deck |
| D6 | Harvard references | Not assembled as a final bibliography | 🔴 ACTUALLY MISSING | Add citations and bibliography to report |
| D7 | Appendices/evidence | Raw evidence is extensive; final appendix not assembled | 🟡 IMPLEMENTED — EVIDENCE WEAK / RECAPTURE RECOMMENDED | Curate redacted screenshots, test outputs and diagrams |
| D8 | AI-use academic-integrity record | Yes | ✅ COMPLETE — IMPLEMENTED + EVIDENCED | Adapt `docs/ai-usage-log.md` to declaration format |

## Historical end-to-end evidence chain

The following is one coherent, valid real-AWS body of evidence rather than unrelated screenshots:

1. `21` shows authenticated API success and unauthenticated/invalid-token denial.
2. `51` shows an authenticated order accepted as `PENDING`.
3. `23`/`53` show terminal `CONFIRMED`; `24a`→`24b` show `PENDING`→`REJECTED`.
4. `25` and `26` show unchanged stock on rejection plus correlated Order/Inventory event logs.
5. `56` shows same-key replay returning the same order, supporting idempotency.
6. CW-4 raw evidence records SNS→notification Lambda→SES and identical-message idempotency, plus an X-Ray trace.
7. CW-5 raw evidence records an authenticated WebSocket client receiving a terminal update and a fake token being rejected with HTTP 403.
8. `63` visibly shows authenticated My Orders with “Live Sync.”

The current implementation improves this path with transactional order and inventory outboxes. That safety improvement changes internals, not the business outcome already demonstrated.

## Performance evidence interpretation

`70-k6-load-summary.png` is genuine historical real-AWS performance evidence. Visible values are:

- Duration: 7m00.2s.
- Requests/checks: 96,055.
- Successful checks: 100%; failed checks: 0.
- HTTP request failures: 0.00%.
- Throughput: 228.613642 requests/second.
- Latency: average 326.91 ms; median 282.98 ms; p90 494.9 ms; p95 623.76 ms; maximum 4.87 s; minimum 178.63 ms.
- VUs: maximum shown as 200, with observed current range reaching 199.
- Data: approximately 130 MB received and 11 MB sent.
- p99 is not visible and must not be invented.

The seven-minute duration and 200-VU ceiling align closely with `cache-bust-stress-test.js`, so the filename “load summary” is generic/imprecise; it is at least load evidence and likely the cache-busting stress execution. Current scripts are structurally sound and now emit p99, but a fresh run is optional supporting evidence, not a prerequisite to admit that testing occurred.

## Corrections required in older documentation

Do not rewrite these files until separately requested, but correct their claims before report reuse:

- `docs/final-live-verification.md`: replace broad `BLOCKED` labels for RBAC, Saga, idempotency, WebSocket, performance and CI/CD with the evidence categories used here. “Not freshly retested” is not “missing.”
- `docs/assignment-evidence-checklist.md`: its mandatory recapture list is excessive. Historical real-AWS proof already covers authenticated APIs, RBAC, Saga, idempotency, WebSocket and k6.
- `docs/evidence-index.md` and `docs/screenshot-guide.md`: many unchecked/planned entries are stale and cannot be used as an absence ledger.
- `docs/architecture-and-pipeline.md`: sections saying alarms, aliases, WAF logging and traces are not deployed are now stale; current AWS proves they are deployed.
- Architecture Draw.io: remove or qualify unsupported claims for live AWS Backup cross-region copy, a tested 12-minute DR apply, EventBridge archive/replay, VPC Flow Logs, ALB access logs, universal KMS/rotation, implemented GDPR cascade erasure, and active Grafana. Mark eu-central-1 as designed/not deployed and the Mumbai products replica as APAC expansion.

## Actual remaining work

### A. Must do before submission

1. Implement and demonstrate the two explicit Task 4 gaps: delivery tracking and real-time pricing/promotions. Keep them minimal and event-driven; they do not require another full microservice each.
2. Produce the final report, required section structure, Harvard references, appendices and evidence traceability. Include eventual consistency, CQRS applicability, distributed-transaction challenges, security risks, GDPR/PCI scope, performance bottleneck analysis, RTO/RPO targets versus measurements, and limitations.
3. Correct and export the architecture/data-flow diagram so it describes deployed versus designed components honestly.
4. Create the 10–15 slide deck, clean source ZIP and final README/demo instructions.
5. Prepare report-safe evidence copies: redact the partial JWT in `50` and personal email addresses in SPA screenshots; preserve originals unchanged.
6. Capture a current Hosted UI authorization-code/PKCE flow and authenticated callback/SPA view because `60` demonstrates the superseded direct-auth mechanism. This is evidence refresh, not new AWS implementation.

### B. Should do if time

1. Capture the current CloudWatch operations dashboard, X-Ray service map/trace and the active two-region products Global Table.
2. Save a current coverage summary and one security-tool output bundle (Bandit/pip-audit/Trivy/Checkov; ZAP is optional).
3. Run one bounded current smoke/load profile and Playwright/Newman after credentials and a safe environment are available. The historical results already satisfy the existence of testing.
4. Capture a successful GitHub Actions PR/release run after workflows are committed/pushed; until then describe CI/CD as structurally implemented, not live-executed.
5. Optionally capture actual ECS scale-out/recovery or a non-production restore drill for stronger resilience marks.

### C. Optional / do not need to implement for this assignment

- A full second AWS region, Aurora Global Database, active-active routing or Route 53 custom-domain failover.
- AWS Backup cross-region vault/copy unless explicitly retained as an implemented claim.
- Runtime Grafana; CloudWatch already satisfies Task 7 and Grafana is correctly optional.
- EKS, MSK/Kafka, Step Functions, ElastiCache, a payment microservice, or a fifth core microservice.
- Destructive chaos testing in the baseline environment or another very large k6 run.
- Terraform module/state migration merely for stylistic production perfection.
- The optional Admin Users delete feature; if retained, it must not claim that a browser can call Cognito `AdminDeleteUser` directly without privileged backend mediation.

## Final assessment

SmartRetailX is not at the beginning of implementation. It is a deployed, tested, evidence-rich system with two explicit Task 4 feature gaps and substantial submission-writing/curation work left. After those two narrow features, the highest-value work is the report, corrected diagram, evidence appendix and slides—not a broader AWS rebuild.
