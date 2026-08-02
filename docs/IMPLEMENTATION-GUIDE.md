# SmartRetailX — Master Implementation Guide (v2, Corrected)
### COMP60010 · Deadline Wed 30 Sep 2026 · Target 95+ · Written for the 9 weeks starting Mon 27 Jul 2026

---

## 0. How to use this guide

This guide replaces the plan in your old `Week_1_-7_cloude_implementation_guide.txt`.
The old guide's **code** is mostly reusable; its **plan and infrastructure config** were not.
Throughout, you'll see two markers:

- **REUSE (old guide § X):** follow that section of the old guide, with the listed edits.
- **REPLACE:** the old guide is wrong here; do what this guide says instead.

Three cost states govern everything (this is your lecturer's plan, sharpened):

| State  | What it means                                                                 | Cost          |
|--------|-------------------------------------------------------------------------------|---------------|
| LOCAL  | Docker Compose + LocalStack + Postgres 16. Where all feature code is written. | £0            |
| PARKED | AWS stack exists; `live=false` removes NAT/ALB/CloudFront, ECS desired=0, Aurora auto-paused. | ~pennies/day  |
| LIVE   | `terraform apply -var="live=true"` — full stack in ~10–12 min.                | ~£0.20/hour   |

**Checkpoint Window (CW):** a 2–4 hour LIVE evening session held whenever an AWS-only
feature lands. Protocol in Appendix C. Five or six of these across the project ≈ £5 total.
They exist because LocalStack Community **cannot** run: EventBridge Pipes, API Gateway v2
(HTTP + WebSocket), Cognito, ALB/VPC Link, X-Ray, or real IAM. Those seams are validated
in CWs, never trusted blindly until a final week.

**Standing rules (non-negotiable):**
1. Never leave the stack LIVE overnight except the night before the viva (PARKED, verified).
2. Every CW ends with screenshots into `assignment-screenshots/` (numbered) **before** parking.
3. `terraform plan` before every apply. Read it.
4. Conventional commits; push daily. The repo history is itself evidence.
5. Keep `docs/ai-usage-log.md` — one line per session describing AI assistance (academic integrity).
6. Keep `docs/cost-ledger.md` — date, session length, purpose, estimated £. Screenshot Cost
   Explorer monthly. This ledger becomes a report exhibit.

---

## Week 0 (this weekend, 25–26 Jul) — Verify what you already have

You've done most of old-guide Weeks 1–2. Verify, don't redo:

- [ ] AWS account, MFA on root, IAM user, billing alarm at $50 — old guide § W1 D1. ✔ done per your notes.
- [ ] **Check your AWS credits now:** Billing console → Credits. Accounts created under the
      2025+ free-tier scheme get **$100 at signup + up to $100 via activities** (create a
      budget, etc.). If credits exist, your entire projected spend (~£10–20) is covered.
      Screenshot the credits page → `00-aws-credits.png`.
- [ ] Tools installed (Terraform ≥1.5, AWS CLI, Docker, Python 3.12, k6, git) — old guide § W1 D2.
- [ ] Repo structure exists; `docker-compose.yml`, `localstack-init/01-setup.sh`, Makefile present.
- [ ] **Delete the console-created Cognito pool** (old guide W1 D6 created one by hand;
      Week 1 below recreates it in Terraform — you cannot have both).
- [ ] If any Terraform stack is currently applied from earlier weeks: run `terraform destroy`
      **now** (nothing depends on it yet, and the old NAT/ALB are billing). Fresh, corrected
      infra goes up in Week 1.
- [ ] Rename `MakeFile` → `Makefile` (`git mv MakeFile Makefile`). Remove `-auto-approve`
      from the `destroy` target.
- [ ] `docker-compose.yml`: change `postgres:15-alpine` → `postgres:16-alpine` (must match
      Aurora PG16); delete the obsolete `version: "3.8"` line.

---

## Week 1 (Mon 27 Jul – Sun 2 Aug) — Corrected infrastructure + the live toggle
**Goal:** Terraform that matches the corrected architecture diagram exactly, applies cleanly,
parks to ~£0, and passes CW-1. No application code this week.

### Day 1 — Restructure and the `live` variable
Split `infra/main.tf` into `network.tf`, `data.tf`, `messaging.tf`, `compute.tf`,
`security.tf`, `observability.tf` (Terraform reads all `.tf` files — zero refactor risk;
move blocks, run `terraform validate` after each move).

Add the toggle (Appendix B.1 has the full pattern):

```hcl
variable "live" {
  description = "true = full billable stack; false = parked (~£0)"
  type        = bool
  default     = false
}
```

**Also today — remote state (do not skip):** create a small versioned S3 bucket and
switch the backend (`backend "s3"` with `use_lockfile = true`). If your laptop dies with
local state, the deployed stack becomes unmanageable orphaned billing. Ten minutes now
insures the whole project.

**Critical prerequisite:** your private route table currently defines its default route
*inline*. Inline routes can't be gated. Convert to a standalone `aws_route` resource,
then gate NAT + EIP + that route with `count = var.live ? 1 : 0`.

### Day 2 — Internal ALB (REPLACE old guide W2 D2 — its ALB was public: auth bypass)
```hcl
resource "aws_lb" "main" {
  count              = var.live ? 1 : 0
  name               = "${var.project_name}-alb"
  internal           = true                      # THE fix
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.private[*].id  # private, not public
}
```
ALB security group ingress: **only** from the VPC Link security group (created Day 4),
not 0.0.0.0/0. Four target groups (order/inventory/user/product, port 8000, health check
`/health`), listener with path rules `/v1/orders*`, `/v1/inventory*`, `/v1/users*`, `/v1/products*`.
Add a data-subnet route table with **no default route**; attach both gateway endpoints to it.

### Day 3 — Per-service IAM + Aurora (REPLACE old guide W2 D1/D3)
One execution role (shared, fine) + **four task roles** (least privilege — Appendix B.2).
Aurora, corrected:
```hcl
resource "aws_rds_cluster" "inventory" {
  cluster_identifier          = "${var.project_name}-inventory"
  engine                      = "aurora-postgresql"
  engine_version              = "16.6"            # PG16; min-0 needs a recent engine
  database_name               = "inventory"
  master_username             = "smartretailx_admin"
  manage_master_user_password = true              # no plaintext anywhere
  db_subnet_group_name        = aws_db_subnet_group.aurora.name
  vpc_security_group_ids      = [aws_security_group.aurora.id]
  skip_final_snapshot         = true
  storage_encrypted           = true   # the diagram claims KMS at rest — this line makes it true
  serverlessv2_scaling_configuration {
    min_capacity = 0      # auto-pause: idle DB → £0 compute
    max_capacity = 2      # cost circuit breaker vs runaway k6
  }
}
resource "aws_rds_cluster_instance" "writer" {
  cluster_identifier = aws_rds_cluster.inventory.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.inventory.engine
  engine_version     = aws_rds_cluster.inventory.engine_version
}
```
Delete the old `aws_secretsmanager_secret.aurora_credentials` + version resources and the
`aurora_master_password` variable — `manage_master_user_password` replaces all of it.

DynamoDB upgrades: GSI `userId-index` on orders, `category-index` on products (add the
attribute blocks + `global_secondary_index`), `point_in_time_recovery { enabled = true }`
on orders, **delete the `ttl` block from the orders table** (financial retention). TTL stays
on idempotency + websocket-connections. SQS: add `receive_wait_time_seconds = 20`.
ECR: `image_tag_mutability = "IMMUTABLE"` + lifecycle policy keep-5.

### Day 4 — Cognito in Terraform + API Gateway HTTP API + VPC Link
REUSE old guide W2 D4–D5 code as the base, with edits: pool + client + `customer`/`admin`
groups all in Terraform; HTTP API with JWT authorizer referencing the Terraform pool's
issuer/client; VPC Link into the private subnets with its own SG; integration →
internal ALB listener. Add `$default` stage throttling (e.g. rate 50, burst 100).

### Day 5 — ECS services (skeleton) + Scheduler + alarms
Four `aws_ecs_service` resources with `desired_count = var.live ? var.service_desired_count : 0`
(**[GC-1 sibling: GC-2]** — this originally read `var.live ? 1 : 0`, which makes CW-1 pull
image tags that do not exist yet and trips the deployment circuit breaker; the new variable
defaults to 0 and is raised to 1 in Week 2. See `docs/guide-corrections.md`) and
`deployment_circuit_breaker { enable = true, rollback = true }`. Task definitions with
`runtime_platform { operating_system_family = "LINUX", cpu_architecture = "ARM64" }`
(images arrive in Week 2 — services will show 0 running; that's fine).
EventBridge Scheduler pair (Appendix B.4): 00:00 park / 08:00 restore (disabled by default;
enabled only in final weeks). CloudWatch alarms: DLQ depth ≥ 1, SQS depth > 100.

### Day 6 — CW-1 (first checkpoint window, ~2 h, ~£0.50)
`terraform apply -var="live=true"` → verify in console: internal ALB in private subnets,
Aurora available then **watch it auto-pause** after ~10 idle minutes (screenshot — this is
gold), Cognito pool, HTTP API with authorizer, endpoints, GSIs, PITR. Create one test user
via CLI, get a JWT (old guide W2 D6 REUSE), call the API — expect 503 (no targets yet) but
**401 without a token**: proves the auth wall. Screenshots `10-…` to `19-…`.
Then `terraform apply -var="live=false"` → confirm NAT/ALB gone, £ ≈ 0.

### Day 7 — Buffer + commit
`checkov -d infra/` and `tflint` locally; fix findings (report material). Commit:
`feat: corrected infrastructure — internal ALB, live toggle, per-service IAM, Aurora PG16 min-0`.

**Done when:** apply/park cycle works both ways; auth wall proven; cost ledger started.
**Cost this week:** ≈ £0.50–1.

---

## Week 2 (3–9 Aug) — User Service + Order Service (LOCAL) · CW-2
**REUSE** old guide W3 D1–D2 (User Service code, Dockerfile, local test) and W4 D1–D3
(Order Service, idempotency, tests) with these edits:

- All routers under `/v1` (old guide already does this — keep it).
- `ENV=local` skips JWT validation (mock claims); `ENV=production` validates against
  Cognito JWKS **and enforces the `cognito:groups` claim in middleware** (the HTTP API
  authorizer checks signature/scopes, not groups — know this for the viva).
  Make auth **fail-closed**: if `ENV` is unset, behave as production — a missing
  environment variable must never silently disable security.
- Add `pybreaker` + `tenacity` as dependencies now (used properly in Week 3).
- Order Service: on create → write DynamoDB (status=PENDING) → publish to SQS.
  Also subscribe an **order-events SQS queue** to the SNS topic with a filter policy
  `{"eventType": ["order-confirmed", "order-rejected"]}` and add a small consumer
  thread/task that applies the outcome (CONFIRMED or REJECTED) — this is the saga
  outcome receiver, of which compensation is one half (publisher lands Week 3).
  Add the queue + subscription to `messaging.tf`.
  **[GC-1]** This originally read `["order-rejected"]` only. Nothing else in the
  design moves an order to CONFIRMED, so a rejected-only filter leaves every
  successful order PENDING forever and contradicts the Week 3 D5 gate below.
  See `docs/guide-corrections.md`.

Days 1–2 User Service; Days 3–5 Order Service + unit tests (moto) green in `make test`;
both services in Compose, Swagger at `localhost:8001/docs`, `8003/docs`.

### Day 6 — CW-2 (~3 h, ~£0.75)
Build + push ARM64 images (Appendix B.3 buildx commands — REPLACE old guide's plain
`docker build`). `live=true`; ECS pulls; hit through the full chain:
`curl -H "Authorization: Bearer $JWT" https://<api-id>.execute-api…/v1/orders` — 201.
No token → 401. Wrong group → 403. Screenshots `20-…`. Park.

**Done when:** two services pass tests locally AND respond through API GW→VPC Link→ALB on AWS.

---

## Week 3 (10–16 Aug) — Inventory + Product Services, the saga (LOCAL) · CW-3
**REUSE** old guide W5 D1–D3 (Inventory Service) with additions:

- SQLAlchemy → Postgres 16 locally / Aurora in prod (connection string via env; in prod
  the ECS task pulls creds from the RDS-managed secret via `secrets.valueFrom`).
- Consumer loop: `tenacity` retry (3 attempts, exponential) + `pybreaker` around DB calls.
- **The compensation publisher:** stock sufficient → decrement in a transaction → SNS
  `eventType=order-confirmed`; insufficient → SNS `eventType=order-rejected`. This closes
  the choreography saga (ADR-06) — a named Task 4 requirement the old guide skipped.
- **Product Service (NEW — the old guide never built it):** smallest service. FastAPI,
  `/v1/products` list/get from DynamoDB, in-memory TTL cache (`cachetools.TTLCache`,
  maxsize 500, ttl 30 s), `X-Cache: HIT|MISS` response header (nice demo), unit tests.
  One day of work; it's promised by your diagram, so it must exist.

Days 1–3 Inventory; Day 4 Product; Day 5 full local chain: create order → SQS → inventory
consumes → Postgres decrements → SNS → order flips CONFIRMED; break stock → REJECTED
(compensation proven locally). `make test` green across all four.

### Day 6 — CW-3 (~3 h, ~£0.75): the money demo on AWS
All four images pushed; full chain on real AWS both paths (confirmed AND rejected).
Aurora wakes from pause on first query (~15 s — note it; you'll pre-warm at the viva).
DLQ demo groundwork: REUSE old guide W5 D6 (poison message → 3 retries → DLQ → alarm
fires). Screenshots `30-…`: both order states, DLQ alarm, X-Ray not yet — fine.

**Done when:** saga works both directions locally and on AWS; DLQ + alarm proven.

---

## Week 4 (17–23 Aug) — Notification Lambda + SES + Powertools + Scheduler · CW-4
**REUSE** old guide W6 nearly wholesale — it was one of its good weeks — with edits:

- Day 1 **first**: verify your sender email in SES (sandbox: verified recipients only —
  do it now, not at demo time). Screenshot.
- Lambda subscribed to SNS (filter `order-confirmed`); Powertools Logger + Tracer +
  Idempotency (idempotency table already exists). Structured JSON logs with correlation IDs.
- EventBridge scheduled rule: daily 00:00 stock-reconciliation (REUSE old W6 D5) **and**
  enable the park/restore Scheduler pair from Week 1 (from now on the stack has a safety
  net if you forget to park).

Local first (LocalStack SNS + a local Lambda invoke harness), then CW-4 (~2 h): deploy
Lambda, place an order on AWS, **receive a real email**, screenshot CloudWatch structured
logs + the idempotency second-delivery suppression. `40-…` series.

---

## Week 5 (24–30 Aug) — The AWS-seams week: Pipes · WebSocket · frontend · OIDC
This week is AWS-heavy by nature (none of it runs on LocalStack Community). Budget three
short LIVE sessions (~£3 total) rather than one long one. REUSE old guide W7 as the base.

- Day 1 — **EventBridge Pipes** (Terraform, Appendix B.5): DDB Streams → filter
  (`MODIFY`, status changed) → EventBridge bus. Zero glue Lambda. Verify with a bus
  archive/CloudWatch target first.
- Day 2 — WebSocket API + connect/disconnect/push Lambdas + connections table (REUSE old
  W7 D2–D3 code). **WebSocket APIs do not support JWT authorizers — validate the Cognito
  JWT inside the `$connect` Lambda (token passed as a query-string parameter) and reject
  the connection otherwise. An open, unauthenticated WebSocket is an examiner magnet.**
- Day 3 — EventBridge rule: status-change event → push Lambda → `postToConnection`.
- Day 4 — **Minimal frontend** (REPLACE — old guide had none, and your WebSocket demo
  needs eyes): one static HTML/JS page — login via Cognito Hosted UI (needs an
  `aws_cognito_user_pool_domain` resource — one line, add it), place order button,
  live status line via WebSocket. Host on S3 + CloudFront (OAC) + WAF (WAF needs a
  `us-east-1` provider alias — classic gotcha). This page is your viva centrepiece.
- Day 5 — **CI/CD to OIDC** (REPLACE old guide's access keys, § W3 D6/W7 D6): Appendix
  B.6. Pipeline: pytest+coverage → checkov+tflint → buildx ARM64 → Trivy → ECR →
  `ecs update-service`. Delete `AWS_ACCESS_KEY_ID` from GitHub secrets afterwards —
  screenshot the empty secrets page (Zero Trust evidence).
- Days 6–7 — CW-5: end-to-end through the browser page: login → order → watch
  PENDING→CONFIRMED appear live. Record a 60-second screen capture (backup demo v1).
  Screenshots `50-…`. Park.

**Done when:** a browser shows a live order status change on real AWS, deployed by a
pipeline with zero stored credentials.

---

## Week 6 (31 Aug – 6 Sep) — Observability + Global Table + hardening
- Days 1–2 — **Grafana OSS on Fargate**: dashboards provisioned-as-code baked into the
  image; reached via **CloudFront VPC origin** fronting the internal ALB (CloudFront can
  originate from an internal ALB since late 2024 — browser-friendly for the viva,
  WAF-protected, and itself one more innovative-service talking point), with the ALB's
  Cognito OIDC listener rule doing authentication. SSM port-forward to the Fargate task
  is the fiddlier fallback. Never public, never open.
- Day 3 — **ADOT/X-Ray**: OTel SDK in all four services + ADOT collector sidecar (or
  daemon); Lambda tracing already on via Powertools. Screenshot the service map showing
  the full order flow — one of the strongest single images in your report.
- Day 4 — **DynamoDB Global Table**: Global Tables **require Streams**, and the products
  table has none — first add `stream_enabled = true` + `stream_view_type =
  "NEW_AND_OLD_IMAGES"` to it, then add `replica { region_name = "ap-south-1" }`. Screenshot both regions' consoles showing the same item.
  (GDPR-lawful multi-region — rehearse the two-sentence justification.)
- Day 5 — CloudWatch dashboard (p95, 5xx, SQS/DLQ depth, ECS CPU, billing), alarm review.
- Days 6–7 — CW-6 + slack for anything that slipped from Weeks 2–5.

---

## Week 7 (7–13 Sep) — TESTING WEEK (this is 20% of your grade — treat it as a feature)
Run against real AWS in 2–3 LIVE sessions (~£4 — your biggest spend, and worth it):

- Day 1 — k6: load (ramp to 50 VUs, 10 min), stress (to failure), spike profiles against
  `/v1/products` and order-creation. Capture latency/throughput/error graphs AND the
  CloudWatch autoscaling graph (CPU>70% → tasks 1→5). This graph is the Task 6 money shot.
- Day 2 — Chaos: kill a task mid-load → ALB reroutes, autoscaler recovers (screenshot
  timeline). Aurora failover test if PROD profile reader enabled; otherwise document
  PITR restore drill.
- Day 3 — Poison-message demo re-run, formally evidenced: message → 3 retries → DLQ →
  alarm → replay runbook executed.
- Day 4 — Security testing: OWASP ZAP baseline against the API (expect JWT 401s —
  that IS the finding), `bandit -r services/`, `pip-audit`, checkov/tflint reports from CI.
- Day 5 — Coverage report (target ≥ 80% on service code); LocalStack integration job
  running in GitHub Actions (services + LocalStack as workflow containers).
- Days 6–7 — Assemble the **evidence pack**: every screenshot indexed in
  `docs/evidence-index.md` against the Task 1–8 requirements (traceability matrix skeleton
  in Appendix F). Full `terraform destroy` → `apply` timed drill once (**your DR RTO
  evidence** — record the minutes). For the drill to succeed set `force_delete = true`
  on the ECR repos and `force_destroy = true` on S3 buckets first — destroy refuses
  non-empty ones otherwise. Park.

---

## Week 8 (14–20 Sep) — REPORT
4,000–5,000 words per the brief's structure (Intro / Design / Implementation / Testing /
Conclusion / References / Appendices). Daily targets: D1 Design+Architecture (embed the
corrected diagram + ADR summaries), D2 Implementation (saga, Pipes, idempotency, polyglot
justification with the access-pattern table), D3 Security+Compliance (OAuth flow, RBAC,
GDPR/PCI, Zero Trust/OIDC), D4 Testing+Results (graphs, analysis, limitations), D5 Cost
chapter (**real Cost Explorer screenshots + your cost ledger** — the parked-vs-live
billing graph is an exhibit nobody else will have), D6 references (Harvard) + appendices,
D7 full read-through. Critical analysis > description — every choice paired with its
rejected alternative (the ADR panel writes this chapter for you).

## Week 9 (21–27 Sep) — Slides, packaging, rehearsal, SUBMIT EARLY
- D1–2: 10–15 slides mirroring the report; the demo storyboard (≤3 min golden path:
  login → order → live WebSocket flip → Grafana → the cost slide).
- D3: README polish; ZIP per the brief (source, Dockerfiles, Terraform, tests, README).
- D4: record the full backup demo video (if AWS hiccups at the viva, you play this).
- D5: **Rehearsal 1** from cold: unpark → demo → park. Time everything.
- D6: **Rehearsal 2** + fix friction. **Submit by Sun 27 / Mon 28 Sep** — two days of buffer.
- D7: rest. Seriously.

## Viva Day Protocol (whenever it's scheduled)
- **Evening before:** `apply live=true`; run the golden path once; leave PARKED (not
  destroyed — parking preserves ECR images and Cognito IDs; cold-creating on the morning
  is 20–25 min of avoidable risk, not the mythical 8–10).
- **Morning (T-45 min):** `apply live=true` (~3–5 min from parked); T-15: hit one product
  read to wake Aurora; T-10: golden path once; open tabs: frontend, Grafana, X-Ray map,
  Cost Explorer.
- **After:** `terraform destroy`. Done. Total day cost ≈ £1.

---

## If you fall behind — descope in THIS order (and no other)
1. Grafana (CloudWatch dashboards alone still satisfy Task 7) → saves ~2 days
2. Global Table (keep it in the report as designed-and-costed) → saves ~½ day
3. ZAP/schemathesis depth (keep bandit + pip-audit minimum) → saves ~½ day
4. ARM64 (fall back to x86 if buildx fights you; delete the −20% claim everywhere) → ~½ day
**Never cut:** the saga compensation, Pipes, WebSocket demo, the testing week, or report time.
Those carry the marks.

---

# Appendices

## A. Old-guide reuse map
| Old guide section | Verdict | Notes |
|---|---|---|
| W1 D1–D3 (account, tools, repo) | REUSE | done — verify only |
| W1 D4–D5 (Terraform, apply) | REPLACE | Week 1 here (toggle, internal ALB, PG16, IAM) |
| W1 D6 (Cognito console) | DELETE | Terraform-only pool (Week 1 D4) |
| W1 D7 (local env) | REUSE | postgres:16 edit |
| W2 D1 (Aurora) | REPLACE | min 0 / max 2 / PG16 / managed password |
| W2 D2 (ALB) | REPLACE | internal = true, private subnets |
| W2 D3 (IAM) | REPLACE | per-service task roles |
| W2 D4–D6 (API GW, Cognito TF, test user) | REUSE with edits | Week 1 D4/D6 |
| W3 (User Service) | REUSE | + groups-claim middleware |
| W4 (Order Service) | REUSE | + order-events queue consumer (compensation) |
| W5 (Inventory) | REUSE | + pybreaker/tenacity + order-rejected publisher |
| W6 (Lambda/SES) | REUSE | largely as-is |
| W7 (Pipes/WS) | REUSE | + frontend page; CI/CD → OIDC |
| W8–10 stubs | REPLACE | Weeks 7–9 here |

## B. Key configuration patterns

### B.1 The live toggle (gate everything billable)
```hcl
resource "aws_eip" "nat"          { count = var.live ? 1 : 0  domain = "vpc" }
resource "aws_nat_gateway" "main" { count = var.live ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id }
resource "aws_route" "private_egress" { count = var.live ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main[0].id }
# ALB + listener: count = var.live ? 1 : 0 ; downstream refs use [0]
# IMPORTANT: the API GW integration + routes reference the listener ARN, so they must
#   carry the same count — otherwise terraform errors the moment live=false.
# ECS services: desired_count = var.live ? 1 : 0
# CloudFront: do NOT gate it — it is free when idle and takes 15-20 min to create or
#   delete (gating it would break the 10-12 min wake promise). Keep it up from Week 5.
#   WAF (~£5/mo) also stays once added — an accepted line in the cost ledger.
# Autoscaling conflict: once Application Auto Scaling attaches to the ECS services,
#   add lifecycle { ignore_changes = [desired_count] } to each service and park via the
#   appautoscaling target instead: min_capacity = var.live ? 1 : 0 (max 5).
#   `make park` keeps an `aws ecs update-service --desired-count 0` fallback.
```
Park: `terraform apply -var="live=false"` · Wake: `-var="live=true"`.
Add Makefile targets `make park` / `make unpark`.

### B.2 Per-service task role (pattern — repeat ×4)
```hcl
resource "aws_iam_role" "order_task" { name = "${var.project_name}-order-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json }
resource "aws_iam_role_policy" "order_task" {
  role = aws_iam_role.order_task.id
  policy = jsonencode({ Version="2012-10-17", Statement=[
    { Effect="Allow", Action=["dynamodb:PutItem","dynamodb:GetItem","dynamodb:UpdateItem","dynamodb:Query"],
      Resource=[aws_dynamodb_table.orders.arn, "${aws_dynamodb_table.orders.arn}/index/*",
                aws_dynamodb_table.idempotency.arn] },
    { Effect="Allow", Action=["sqs:SendMessage"], Resource=[aws_sqs_queue.orders.arn] },
    { Effect="Allow", Action=["sqs:ReceiveMessage","sqs:DeleteMessage","sqs:GetQueueAttributes"],
      Resource=[aws_sqs_queue.order_events.arn] } ]})}
```
Inventory: consume orders queue, SNS publish, its DB secret. User: cognito-idp admin
APIs on the pool. Product: DDB read-only + products GSI. Document the 4×N matrix in the report.

### B.3 ARM64 build + push (REPLACES plain docker build)
```bash
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin $ECR
docker buildx build --platform linux/arm64 -t $ECR/smartretailx/order-service:v0.3.0 --push .
```
Task def: `runtime_platform { operating_system_family = "LINUX", cpu_architecture = "ARM64" }`.
In GitHub Actions add `docker/setup-qemu-action` + `docker/setup-buildx-action` first.

### B.4 Scheduler park/restore (enable in final weeks)
```hcl
resource "aws_scheduler_schedule" "park" {
  name = "${var.project_name}-nightly-park"
  schedule_expression = "cron(0 0 * * ? *)"
  flexible_time_window { mode = "OFF" }
  state = "DISABLED"   # flip to ENABLED from Week 4
  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ecs:updateService"
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ Cluster="smartretailx-cluster",
               Service="smartretailx-order-service", DesiredCount=0 }) } }
# one schedule per service, or a tiny Lambda that loops them; Aurora needs nothing (auto-pauses)
```

### B.5 EventBridge Pipes (the differentiator, in Terraform)
```hcl
resource "aws_pipes_pipe" "order_status" {
  name     = "${var.project_name}-order-status"
  role_arn = aws_iam_role.pipes.arn
  source   = aws_dynamodb_table.orders.stream_arn
  target   = aws_cloudwatch_event_bus.main.arn
  source_parameters {
    dynamodb_stream_parameters { starting_position = "LATEST" batch_size = 1 }
    filter_criteria { filter { pattern = jsonencode({ eventName = ["MODIFY"] }) } } }
  target_parameters { }
}
```
Pipe role: stream Read* on the table stream + `events:PutEvents` on the bus.

### B.6 GitHub OIDC (REPLACES access keys)
```hcl
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"] }
resource "aws_iam_role" "gha" {
  name = "${var.project_name}-gha-deploy"
  assume_role_policy = jsonencode({ Version="2012-10-17", Statement=[{
    Effect="Allow",
    Principal={ Federated = aws_iam_openid_connect_provider.github.arn },
    Action="sts:AssumeRoleWithWebIdentity",
    Condition={ StringLike={ "token.actions.githubusercontent.com:sub" =
      "repo:YOUR_GH_USER/smartretailx:*" },
      StringEquals={ "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }}}]}) }
```
Workflow: `permissions: id-token: write, contents: read` and
`aws-actions/configure-aws-credentials@v4` with `role-to-assume`, no keys.

## C. Checkpoint Window protocol (repeat verbatim each CW)
1. `terraform plan -var="live=true"` — read it → apply (~10–12 min; make tea).
2. Smoke script: JWT issue → authed API call → order both paths → email → WS push
   (grow the script as features land; keep it as `scripts/smoke.sh`).
3. Screenshots for everything new, numbered, into `assignment-screenshots/`.
4. Update `docs/cost-ledger.md` (+ Cost Explorer screenshot if month-end).
5. `terraform apply -var="live=false"` → verify NAT + ALB gone in console.
6. Commit + push. Total: 2–4 h, ≈ £0.50–0.75.

## D. Cost forecast
| Item | Estimate |
|---|---|
| CW-1 … CW-6 | ≈ £4–5 |
| Week 7 testing sessions | ≈ £4 |
| Weeks 8–9 spot checks + rehearsals | ≈ £3 |
| Parked storage/logs (whole project) | ≈ £2–3 |
| Viva eve + day | ≈ £1.50 |
| **Total** | **≈ £15–17, likely £0 after credits** |

## E. Master evidence checklist (screenshot series)
00 credits/billing-alarm · 10s corrected infra + auth wall + Aurora auto-pause ·
20s services via API GW · 30s saga both paths + DLQ · 40s email + structured logs ·
50s Pipes + WebSocket in browser + empty GitHub secrets · 60s Grafana + X-Ray map +
Global Table both regions · 70s k6 graphs + autoscaling + chaos + ZAP/bandit ·
80s Cost Explorer monthly + destroy/apply RTO timing.

## F. Traceability matrix skeleton (fill as you go; appendix of the report)
| Brief requirement | Where implemented | Evidence |
|---|---|---|
| T1 microservices/ECS/Lambda/multi-region | compute.tf, Global Table | 10s, 62 |
| T2 ≥3 services, /v1, Swagger, inter-service comms | services/*, /docs | 20s, 30s |
| T3 OAuth2/JWT/RBAC/secrets/GDPR/PCI | Cognito TF, middleware, managed pwd | 10s, 21, report §3 |
| T4 real-time, events, eventual consistency, saga | Pipes, WS, SNS/SQS, compensation | 30s, 50s |
| T5 retries, breaker, LB, autoscaling, multi-AZ, DR | tenacity/pybreaker, ALB, RTO drill | 70s, 84 |
| T6 load/stress testing + analysis | k6 + CloudWatch | 70s |
| T7 logging, tracing, dashboards, alerting | Powertools, X-Ray, Grafana, alarms | 40s, 60s |
| T8 unit/integration/API/e2e/security tests | pytest+moto, LocalStack CI, ZAP/bandit | 74–77 |

---

# ADDENDUM — Final adversarial review (read before Week 1)

These are defects found in a last full-perspective pass, including defects in this guide
and the diagram themselves. Each is small; several would have cost you hours at the worst time.

## G.1 Technical landmines (would have broken the demo)
1. **CloudFront strips the Authorization header by default.** Your /api/* behavior MUST use
   origin request policy `AllViewerExceptHostHeader` + cache policy `CachingDisabled`,
   or the JWT never reaches the authoriser and every call 401s mysteriously. (Week 5 D4.)
2. **WebSocket APIs do not support JWT authorisers** (HTTP/REST only). Authenticate the
   `$connect` route with a small Lambda authorizer reading the token from the query string
   (`wss://…?token=<JWT>`). Say this in the report — examiners know this gap. (Week 5 D2.)
3. **CORS**: the browser page (CloudFront domain) calling the HTTP API needs
   `cors_configuration` on the API (allow the CloudFront origin, Authorization header).
   Without it the SPA fails in-browser while curl works — classic confusion. (Week 5 D4.)
4. **Cognito Hosted UI needs a pool domain**: add `aws_cognito_user_pool_domain` (prefix
   domain is fine) + client callback/logout URLs (your CloudFront URL) + authorization-code
   flow enabled, or the login page simply doesn't exist. (Week 1 D4 + Week 5 D4.)
5. **Products table has no stream** — a DynamoDB Global Table replica requires Streams
   (NEW_AND_OLD_IMAGES) on the source. Enable before adding the replica. (Week 6 D4.)
6. **k6 vs SES**: load-testing order creation fires the notification path — SES sandbox
   allows ~1 msg/sec and ~200/day, so a 50-VU test = throttling errors + inbox flood.
   Point load tests at /v1/products primarily; for order-path tests set a message
   attribute (`loadTest=true`) filtered OUT by the SNS→Lambda subscription. (Week 7 D1.)
7. **Unpark race**: on `live=true`, ECS tasks can start before the NAT route exists →
   image pulls fail once. Add `depends_on = [aws_route.private_egress]` to the four
   `aws_ecs_service` resources. Harmless otherwise (circuit breaker retries), but ugly.
8. **Aurora engine version**: don't blind-trust "16.6" — run
   `aws rds describe-db-engine-versions --engine aurora-postgresql --query "DBEngineVersions[].EngineVersion"`
   and pick the newest 16.x available in eu-west-1 (min-0 auto-pause needs ≥16.3).
9. **Scheduler timezone**: schedules default to UTC. Add
   `schedule_expression_timezone = "Asia/Colombo"` or your "00:00 park" runs at 05:30.
10. **ARM64 builds in CI**: QEMU emulation on default runners is 2–4× slower. If the repo
    is public, use GitHub's free `ubuntu-24.04-arm` runners natively; if private (recommended
    for academic integrity), accept QEMU or build/push locally for big images.

## G.2 Consistency fixes applied to the diagram (done — re-import the .drawio)
- Route 53 relabelled "design intent — demo uses default AWS URLs": you have no custom
  domain (a hosted zone + domain costs real money), and nothing in this guide creates one.
  A diagram box with no Terraform behind it is exactly the mismatch examiners probe.
  Optional upgrade: a ~$3–12 .click/.link domain via Route 53 makes it real — your call.
- "React SPA" → "Web SPA": Week 5 builds a static HTML/JS page, not a React app. Diagram
  and implementation must not disagree. (If you prefer React via Vite, build that instead
  and keep the old label — pick ONE.)
- Grafana access claim simplified to "never public — SSM port-forward": browser OIDC
  through an internal ALB is operationally awkward via port-forward; the honest, simple,
  demo-able mechanism is `aws ssm start-session --target … --document-name AWS-StartPortForwardingSession`.
- Products label now shows "Streams ✓" (required for the Global Table — see G.1.5).

## G.3 Account-level check (do in Week 0)
Under the 2025+ AWS signup flow you chose either a **Free plan** (credits but many services
BLOCKED — Aurora may be unavailable) or a **Paid plan** (card on file, credits still granted,
everything available). You entered a card, so you're almost certainly Paid — but verify in
Billing → Credits/Plan. If somehow on Free plan: upgrade before Week 1 CW-1, or Aurora and
CloudFront work will dead-end.

## G.4 Rubric coverage to handle IN THE REPORT (no code needed)
- The brief lists a "Payment Service" among suggested services: dedicate a paragraph to
  why payment is an external tokenised integration (PCI SAQ-A scope reduction), and show
  the mocked payment call in the Order Service flow. Framing beats building here.
- Task 4 names "delivery tracking" and "real-time pricing/promotions": map your WebSocket
  order-status push as the delivery-tracking mechanism and discuss pricing/promotions as
  a designed extension over the same Pipes→Bus→push spine (one paragraph).
- Task 4 asks you to *discuss* CQRS and distributed transactions: saga is implemented;
  CQRS gets a considered-and-rejected paragraph (WS push = lightweight read-side projection).
- Task 3 asks for identity-federation discussion: one paragraph on Cognito federated IdPs
  (Google/SAML) as the growth path.
- **Your other two diagrams (order-lifecycle swimlane, DR topology) still carry the OLD
  errors** (Mumbai DR, "synchronous replication RPO 5 min", Route 53 AZ failover). They now
  contradict the corrected main diagram. Fix or regenerate them before the report week —
  internal inconsistency between figures is a visible, avoidable mark-loser.

## G.5 What "90+" actually depends on (honest closing note)
The plan removes known mark-losers; it cannot add marks by itself. The grade now rides on:
(1) the demo working live — protect it with the checkpoint discipline and viva-eve warm-up;
(2) the testing week producing real graphs, not screenshots of green terminals;
(3) the report arguing decisions (ADRs, rejected options, measured costs) instead of
describing features; (4) you being able to answer "why" for every box on the diagram
without notes. Rehearse the viva questions from the earlier review — they are the exam.

---

# ADDENDUM H — Lecturer rulings and the mandatory CRUD UI (supersedes conflicting text above)

## H.1 Rulings received
1. **Production level = practices, not sizing — CONFIRMED.** Every scale-down ADR now has
   written cover. Quote the confirmation date in the report's scope section.
2. **Full UI with CRUD features is REQUIRED.** The "minimal static page" in Week 5 D4 is
   superseded by the scope below. The UI is struck from the descope list permanently.
3. **Multi-region: treat as tacitly approved, explicitly confirm later.** His reply
   addressed the UI, not region strategy. One follow-up line at next contact:
   "Global Table + documented DR for multi-region — fine, yes?"

## H.2 UI scope (confirm this list with him in one line before building)
Customer: Cognito login/registration (Hosted UI) · product list + detail · place order ·
My Orders with live WebSocket status updates. Admin (cognito:groups = admin): product
create/edit/delete · stock view/adjust. RBAC is VISIBLE (admin controls absent for
customers; backend returns 403 regardless — demo both in the viva).

## H.3 Stack and build plan
- Vite + React + react-router; `react-oidc-context` for Cognito code+PKCE flow;
  fetch with the access token; deployed to the existing S3/CloudFront (no new infra).
- **W5 D4 (revised):** scaffold, Hosted UI round-trip, one authenticated GET /v1/products
  rendering on screen. Auth working end-to-end is the milestone — not looks.
- **W6 D1–3 (revised):** products page, admin CRUD forms, order placement, My Orders with
  WS live status, admin stock page. Plain styling; completeness first.
- **W6 D4–5 (shifted):** Grafana + ADOT (was D1–3). Global Table stays D6? No — Global
  Table moves to W6 D6, chaos prep merges into Week 7 D2.
- **CI:** add a frontend job — npm ci/build → aws s3 sync → CloudFront invalidation
  (OIDC role already covers it; add s3/cloudfront permissions).
- Backend endpoint additions land in the weeks their services are built (see CLAUDE.md 28–30).
- Optional stretch for Task 8 if time allows: ONE Playwright smoke test
  (login → place order → status flips) — e2e testing evidence almost nobody submits.

## H.4 Revised descope order (replaces the earlier list)
1. Grafana (CloudWatch dashboards suffice) · 2. Global Table (keep as designed+costed) ·
3. ZAP/schemathesis depth · 4. ARM64 fallback to x86 · 5. UI styling polish (NEVER UI features).
Never cut: UI features, saga compensation, Pipes, WebSocket, testing week, report time.
