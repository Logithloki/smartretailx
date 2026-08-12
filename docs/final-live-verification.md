# SmartRetailX final live verification

Date: 11 August 2026  
Environment: `baseline` (`live=true`, `enable_grafana=false`)  
AWS account/region: `322551984077` / `eu-west-1`  
Branch: `codex/production-readiness`

## Final classification

**PASS WITH WARNINGS**

The AWS runtime and persistence layers are healthy, the security controls fail closed, and the repository passes its architecture, service, frontend, and Terraform validation. The approved P0 frontend redeployment on 11 August 2026 fixed the missing runtime configuration and stale bundle: the SPA renders with no fatal console error and its login action reaches Cognito using Authorization Code + PKCE. Full customer/admin authentication and the downstream application-data tests remain blocked only because no legitimate test credentials/token were available.

The P0 operation changed only versioned/live S3 frontend objects and created one scoped CloudFront invalidation. No Terraform apply/destroy/state/import/backend operation, ECS/Lambda/Cognito/API Gateway/data/network/GitHub mutation, load test, order creation, or chaos experiment was performed.

## Area summary

| Area | Result | Evidence | Issue |
|---|---|---|---|
| Infrastructure | PASS | Four ECS services are 1 desired / 1 running / 0 pending, deployments `COMPLETED`, targets healthy; ALB, NAT, Aurora, DynamoDB, Pipe, Lambda aliases, CloudFront and WAF logging are healthy | None observed in the live control plane |
| Frontend | PASS | `/`, JSON pointer files and current assets return 200 with correct types/cache metadata; React sign-in shell renders without console errors | No frontend bootstrap defect remains |
| PKCE authentication | PARTIAL | Login reaches Hosted UI; request uses `response_type=code`, a 43-character challenge, `S256`, correct client and callback | Full login/code exchange is blocked by unavailable test credentials |
| RBAC | BLOCKED | JWT authorizer protects all `/v1` routes; groups `admin` and `customer` exist; local tests pass | Customer 403/admin success were not re-exercised against this deployment |
| REST API | PARTIAL | Direct and CloudFront no-token requests return 401; request `B7BeejRODoEEJsg=` took 0.816508 s | Authenticated GET/admin/customer operations blocked |
| Order outbox | BLOCKED | Table/stream, development alias, enabled event-source mapping, retry/DLQ and empty queues verified | Publisher has no post-reconciliation invocation; no controlled live order could be created |
| Inventory | BLOCKED | ECS/target/Aurora healthy; code and 49 inventory tests pass; SQS queues empty | Current inbox/stock/outbox transaction not observed live |
| Saga | PARTIAL | Historical table evidence: 11 `CONFIRMED`, 4 `REJECTED`; SNS filter accepts both; no queued backlog | Historical outcomes predate the final application verification; no new order traced end to end |
| Idempotency | BLOCKED | DynamoDB table/PITR/TTL contract and 58 order-service tests pass | Same-key/different-key live sequence not run |
| WebSocket | PARTIAL | `$connect` custom authorizer present; no token -> 401, invalid token -> 403; Pipe/rule/push alias active | Valid connect, connection row, scoped push and two-user isolation blocked |
| Observability | PASS WITH WARNINGS | 17/17 alarms `OK`; nine-widget dashboard; current logs healthy; two real X-Ray traces with no faults/errors/throttles | Quiet alarms often rely on `notBreaching`; no authenticated trace was generated during this audit |
| Performance | BLOCKED | Passive ECS and safe probe metrics saved in `evidence/live-verification/performance-blocked.json` | k6 requires a legitimate token; no application request reached the ALB |
| Resilience | PASS WITH WARNINGS | ECS circuit breakers/rollback, autoscaling 1-5, SQS redrive/DLQs, Lambda retry/DLQ, DynamoDB PITR, Aurora encrypted multi-AZ storage | No baseline chaos run by design; no SmartRetailX AWS Backup plan/vault found; Aurora has one writer and one-day retention |
| CI/CD | BLOCKED | OIDC provider/roles and immutable ECR digest deployment verified; local workflow contracts pass | New workflows are untracked locally; private GitHub run/environment evidence unavailable |
| Terraform | PASS | User-provided final zero-change result; `terraform fmt -check -recursive` and `terraform validate` pass; 36 architecture safety contracts pass | No plan/apply was run in this application-verification task |

## 1. Runtime health

| Service | Desired/running/pending | Task definition | Deployment | Target |
|---|---:|---|---|---|
| order | 1 / 1 / 0 | `smartretailx-order:12` | `COMPLETED` | healthy |
| inventory | 1 / 1 / 0 | `smartretailx-inventory:11` | `COMPLETED` | healthy |
| product | 1 / 1 / 0 | `smartretailx-product:10` | `COMPLETED` | healthy |
| user | 1 / 1 / 0 | `smartretailx-user:10` | `COMPLETED` | healthy |

Every service has rolling deployment configuration, circuit breaker enabled, and automatic rollback enabled. The internal ALB is active in two AZs; the NAT Gateway is available. Aurora PostgreSQL 16.14 and its writer are available, encrypted, configured at 0-2 ACUs with five-minute auto-pause, and backed by Aurora storage across `eu-west-1a`, `1b`, and `1c`.

The orders, products, idempotency, WebSocket-connections and order-outbox DynamoDB tables are `ACTIVE`; PITR is enabled on all five. `smartretailx-order-status` is `RUNNING`. The outbox event-source mapping is enabled and points to the `development` alias with batch size 10, bisect-on-error, three retries, and an SQS failure destination. The notification, reconciliation, outbox and WebSocket Lambda `development` aliases resolve to version 1.

The WebSocket `prod` stage is deployed with auto-deploy. CloudFront is enabled/`Deployed`. WAF logging targets `aws-waf-logs-smartretailx-cloudfront` in `us-east-1` with authorization/cookie redaction. `smartretailx-operations` exists. No Grafana ECS service or target group exists, as required by `enable_grafana=false`.

## 2. Log health

The four ECS log groups have recent activity. A 24-hour Logs Insights scan across 11 ECS/Lambda groups scanned 1,137 events and found no current application `ERROR`, exception, access denial, missing resource/queue, database/migration failure, timeout, serialization failure, or Pydantic failure.

The only matches were:

- graceful Uvicorn shutdown/startup messages whose logger is named `uvicorn.error`;
- an ADOT sidecar receiving the expected termination signal during the previous task rollout;
- ADOT startup warnings about binding OTLP to `0.0.0.0`, a future dimension-rollup default, and an absent optional extra-config file.

These are expected startup/deployment messages, not active application defects. Notification/reconciliation/WebSocket logs last show activity on 8-10 August. The outbox publisher has no log stream because it has not been invoked since deployment; that is a verification gap, not evidence of success.

## 3. Frontend diagnosis and P0 resolution

Original root cause: S3 lacked `config.json` and `release.json`; CloudFront converted the missing-object response to the HTML shell, so `loadRuntimeConfig()` failed at `response.json()` before React rendered. The live index also referenced stale assets `index-DJ5VqSqb.js` and `index-BsOVpHfB.css`.

The approved repair used the reviewed reusable frontend workflow semantics. Release `3c3f37731af8-p0-20260811T052611Z` was stored under `releases/`, the root `assets/` prefix was synchronised with `--delete`, and only the three live pointer files were replaced. Hashed assets use `public,max-age=31536000,immutable`; `index.html`, `config.json` and `release.json` use `no-cache,no-store,must-revalidate`. Invalidation `IF1BTAA4JTOZ0ZCJCEBVGZGY0X` covered `/index.html`, `/config.json`, and `/release.json` and completed.

Post-deployment results:

- `/`: 200 `text/html`, 766 bytes;
- `/config.json`: 200 `application/json`, valid baseline configuration, 569 bytes;
- `/release.json`: 200 `application/json`, matching release ID, 108 bytes;
- `index-PdMpsUz6.js`: 200 `application/javascript`, 302,162 bytes;
- `index-DeQLCTJE.css`: 200 `text/css`, 15,079 bytes.

All five S3 ETags match the corresponding local MD5 checksums. The live index references only the new hashes; the two stale root assets are absent. Browser verification rendered the SmartRetailX sign-in shell and reported no console errors. Full evidence is in `docs/frontend-redeployment-verification.md`.

## 4. Cognito and PKCE

The `smartretailx-spa` client has:

- authorization-code flow only;
- no implicit flow;
- no client secret (`GenerateSecret` is false/null);
- scopes `openid`, `email`, `profile`;
- CloudFront `/` and `/callback` callback URLs;
- CloudFront `/` logout URL;
- Cognito as the identity provider;
- token revocation enabled.

The `admin` and `customer` groups exist. After the P0 redeployment, clicking the live SPA login button reached the Cognito `/login` page. The request used `response_type=code`, a present 43-character challenge, `code_challenge_method=S256`, the correct public client and the CloudFront callback. The complete login -> code -> token exchange remains **BLOCKED BY TEST CREDENTIALS**. No browser storage, token, cookie, password or code verifier was inspected or recorded.

## 5. REST API and CORS

All eight `/v1` API Gateway routes use the Cognito JWT authorizer with the correct issuer and client audience. No-token GETs to products, orders and inventory returned 401 both through CloudFront and directly through API Gateway. The final products probe returned:

- status: 401;
- latency: 0.816508 s;
- API Gateway request ID: `B7BeejRODoEEJsg=`;
- body: `{"message":"Unauthorized"}`.

No JWT, password or secret was logged.

The API has CORS configured for `http://localhost:5173`, including the authorization/content-type/idempotency headers, but an `OPTIONS /v1/products` request still returns 401 even while emitting CORS headers. Production uses same-origin CloudFront `/v1`, so this does not block the deployed topology; it does block direct Vite browser preflight. Smallest fix: add an unauthorised explicit OPTIONS route covering `/v1/{proxy+}` (or otherwise prevent the JWT route from authorising preflight), then verify a 2xx preflight. This is a Terraform/API Gateway configuration change and apply, so it was not made.

## 6. Outbox, inventory, saga and idempotency

Verified wiring:

```text
Order transaction -> order-outbox DynamoDB stream
  -> order-outbox-publisher:development
  -> smartretailx-orders-queue
  -> inventory consumer / Aurora inbox-stock-outbox transaction
  -> smartretailx-order-confirmed SNS
  -> smartretailx-order-events SQS
  -> Order compensation consumer
  -> orders DynamoDB terminal status
```

Both command/event queues use 20-second long polling, redrive after three receives, and currently have zero visible/in-flight/delayed messages. Both DLQs are empty. The SNS SQS subscription is confirmed and filters `order-confirmed` plus `order-rejected` (GC-1). The orders table contains 15 historical terminal orders: 11 `CONFIRMED` and 4 `REJECTED`; transitions generally completed within about 0.2-0.4 seconds in those records.

This proves previous choreography outcomes and current wiring, but not the reconciled deployment's complete transaction path. Because authenticated order creation was blocked, the audit did not create an order, capture a new outbox/idempotency row, inspect the corresponding Aurora inbox/outbox transaction, or repeat same/different idempotency keys. Those requirements remain `BLOCKED`.

## 7. WebSocket

`$connect` uses the `smartretailx-ws-cognito` request authorizer with `route.request.querystring.token` and the `development` Lambda alias. `$default` and `$disconnect` integrations exist. A missing token was rejected with 401; an invalid token was rejected with 403. The connections table and `userId-index` are active and empty after the probes.

The orders Stream -> Pipe -> `smartretailx-events` -> `smartretailx-order-status-changed` -> `ws-push:development` chain is enabled. A valid connection row, status push, disconnect cleanup and two-user isolation test were not possible without a valid token. Do not use the wiring result as a substitute for that evidence.

## 8. Observability and passive performance

All 17 SmartRetailX alarms are `OK`; none is `ALARM` or `INSUFFICIENT_DATA`. Alarm actions point to `smartretailx-alerts`. Several quiet resources are `OK` because missing data is explicitly treated as non-breaching, which is appropriate for sparse error/DLQ metrics but should not be described as observed zero traffic.

The dashboard contains nine metric widgets covering API requests/4xx/5xx, p50/p90/p95/p99 latency, DynamoDB, ECS CPU/memory, queue depth/DLQs, Lambda errors/throttles and Aurora. It does not contain alarm-status widgets.

Two real X-Ray traces exist in the 24-hour window (HTTP 200 and 202), with no fault, error or throttle; durations were 0.555 s and 1.725 s. This proves trace ingestion, but no new authenticated distributed trace was generated in this audit.

Authenticated k6 smoke/load/concurrency tests were deliberately not run. The scripts require `AUTH_TOKEN`, and no token was present. Generating one would have required the blocked login path or an unapproved credential/AWS mutation. Passive results and the exact blocker are machine-readable in `evidence/live-verification/performance-blocked.json`.

## 9. Resilience

Configured and read-only verified:

- ECS deployment circuit breaker and automatic rollback on all four services;
- application autoscaling min 1/max 5 with 70% CPU target, 60-second scale-out and 300-second scale-in cooldown;
- healthy targets and unhealthy-target alarms;
- SQS retry/redrive/DLQ and long polling;
- Lambda event-source bisect/retry/failure destination;
- Aurora encrypted three-AZ storage, automated backup retention of one day, 0-2 ACUs and auto-pause;
- DynamoDB PITR on all five live tables;
- disabled park/restore schedules at 00:00/08:00 Asia/Colombo while `live=true`, and enabled daily stock reconciliation.

The chaos and poison-message scripts hard-stop unless the environment is `test` or `staging` and require explicit confirmation. They were therefore not run against `baseline`. No SmartRetailX AWS Backup plan/vault was returned in `eu-west-1`, so cross-region backup/DR remains unverified. Aurora has one writer and no reader; storage is multi-AZ, but compute failover capacity is demo-scale rather than a continuously hot reader.

## 10. CI/CD readiness

Structurally verified in the local workflows:

- PR CI and equivalent main-branch release gate;
- OIDC `id-token: write` only where AWS access is needed;
- ARM64 builds, scan stages, immutable digest outputs and release manifest;
- development/test/staging promotion;
- production reviewed saved-plan boundary and environment approval;
- ECS/Lambda/frontend rollback pointers;
- authenticated smoke, browser E2E and API contract jobs;
- performance workflow restricted to test/staging.

AWS has the GitHub OIDC provider with audience `sts.amazonaws.com`. `smartretailx-gha-release` trusts only `main`; `smartretailx-gha-deploy` trusts exactly `repo:Logithloki/smartretailx:environment:development`, preserving the baseline -> development compatibility mapping. Running ECS tasks resolve to the four tagged `v0.2.0` ECR digests; repositories use immutable tags and scan-on-push.

The enterprise workflow files are untracked on the local `codex/production-readiness` branch. The repository is private, the GitHub CLI/connector is unavailable, and unauthenticated GitHub API requests return 404. Therefore workflow runs, environment reviewers, secrets and variables are external `BLOCKED` evidence. They must be verified in GitHub after the workflow changes are committed/pushed; no run success is claimed here.

## 11. Validation performed

- 36 architecture/safety contract tests: pass;
- all service/Lambda tests: pass (237 tests; 273 including architecture contracts);
- frontend lint: pass;
- frontend unit tests: 8/8 pass;
- frontend typecheck: pass;
- frontend production build: pass;
- `terraform fmt -check -recursive -diff`: pass;
- `terraform validate -no-color`: pass.

`tflint`, `checkov`, authenticated GitHub tooling and k6 were not installed/available in this local shell; the local architecture contracts still verify the expected workflow structure. Do not interpret tool absence as a successful external scan/run.

## Remaining issues and smallest safe fixes

| Priority | Failure/root cause | Smallest proposed fix | Mutation required? |
|---|---|---|---|
| RESOLVED | P0 missing runtime config and stale frontend bundle | Release `3c3f37731af8-p0-20260811T052611Z` deployed and verified | Completed: S3 frontend objects + scoped CloudFront invalidation only |
| P1 | Authenticated API/RBAC/outbox/saga/idempotency/WebSocket/performance evidence is blocked by unavailable test credentials | In a separately approved task, use existing short-lived customer/admin credentials and begin with login/API verification; do not create users | Normal authentication traffic; application-data mutations still require separate approval |
| P1 | Configured Vite-origin OPTIONS preflight returns 401 | Add an unauthorised OPTIONS catch-all for `/v1`, plan/review/apply, then retest 2xx CORS preflight | Yes: Terraform/API Gateway change and apply |
| P1 | Enterprise workflows are local/untracked and no GitHub run evidence is accessible | Review, commit and push the workflow suite; configure environments/variables/secrets/reviewers; run PR/release/promotion gates | Yes: Git/GitHub configuration and workflow runs; no AWS keys |
| P2 | No SmartRetailX AWS Backup plan/vault found | If cross-region DR is in final scope, add a costed backup plan/copy rule through reviewed Terraform and capture restore evidence | Yes: Terraform/AWS resources and ongoing cost |
| P2 | Baseline live chaos/performance was not run | Keep destructive chaos restricted to test/staging; run safe k6 profiles only after a token is available | Test traffic/state; no baseline infrastructure destruction |

Stop point: the approved P0 frontend-only repair is complete. No order, k6, authenticated API mutation or unrelated AWS/Terraform change was attempted.
