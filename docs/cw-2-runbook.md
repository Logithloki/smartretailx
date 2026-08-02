# CW-2 Runbook — second checkpoint window

**Goal:** confirm the CW-1 routing fix, then run the full saga on real AWS.
**Budget:** ~3 hours, ≈ £0.75. **Screenshots:** `20-…` series.

Two carry-overs this window settles:
1. The `overwrite:path` mapping that fixes the CW-1 routing defect is **unverified on
   real AWS** — step 2 proves it before any time is spent on builds.
2. All four services now exist, so the **saga can run end-to-end on AWS at CW-2**,
   a window earlier than the guide's CW-3. If time is short, the routing fix and the
   order/user path are the required outcomes; the saga can slip to CW-3 as planned.

---

## 1. Pre-flight

- [ ] `git pull` — expect commit `6b13725` or later.
- [ ] `cd infra && terraform plan -var="live=true"` — **read it**. From parked, expect
      roughly `23 to add, 5 to change, 2 to destroy`. The two destroys are superseded
      ECS task-definition revisions (task defs are immutable; a new revision is normal).
- [ ] `terraform apply -var="live=true"`
- [ ] `terraform output` → refresh `docs/aws-values.txt` (gitignored).

## 2. Verify the routing fix BEFORE building anything

If this fails, everything after it is wasted effort.

```bash
export SRX_TEST_PASSWORD='<your test password>'
./scripts/seed-users.sh
./scripts/route-matrix.sh
```

- [ ] **No row returns 404** except the deliberate `/v1/nonexistent` control.
- [ ] Every service row returns **503** (no tasks yet). That is success.
- [ ] Screenshot → **`20-route-matrix-fixed.png`**

### The curl matrix

| # | Method | Path | Before images | After images |
|---|--------|------|---------------|--------------|
| 1 | GET | `/v1/orders` | 503 | 200 |
| 2 | GET | `/v1/orders/{id}` | 503 | 200 / 404* |
| 3 | GET | `/v1/inventory` | 503 | 403 as customer, 200 as admin |
| 4 | GET | `/v1/inventory/{id}` | 503 | 403 / 200 |
| 5 | GET | `/v1/users` | 503 | 403 as customer, 200 as admin |
| 6 | GET | `/v1/users/{id}` | 503 | 200 |
| 7 | GET | `/v1/products` | 503 | 200 |
| 8 | GET | `/v1/products/{id}` | 503 | 200 |

\* An application 404 for a missing order carries a FastAPI body. The ALB's is
`{"error":"route not found"}` — **check the body, not just the status.**

**Control row:** `/v1/nonexistent` must return the ALB body, proving the default
rule still fires and the absence of 404s above is meaningful.

**If a 404 reappears**, read the new `path` field in the access log:
```bash
MSYS_NO_PATHCONV=1 aws logs filter-log-events --log-group-name "/aws/apigateway/smartretailx" --region eu-west-1 --limit 20 --query "events[].message" --output text
```
`routeKey` populated + `integrationError "-"` + 404 ⇒ the backend rejected the path.
`routeKey: "$default"` ⇒ API Gateway never matched a route.

## 3. Build and push all four ARM64 images

**The build context is `services/`, not the service directory** — every image copies
the shared `srx_common` package, which lives outside the service folder. Use `-f`, or
the build fails on the COPY.

```bash
REGISTRY=322551984077.dkr.ecr.eu-west-1.amazonaws.com
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin $REGISTRY
for svc in user order inventory product; do
  docker buildx build --platform linux/arm64 \
    -f services/$svc-service/Dockerfile \
    -t $REGISTRY/smartretailx/$svc-service:v0.2.0 --push services/
done
```

- [ ] ECR tags are **IMMUTABLE** — bump the version rather than reusing `v0.2.0`.
- [ ] QEMU makes ARM64 builds slow on an x86 laptop. Expect several minutes each.

## 4. Bring the services up

```bash
cd infra
terraform apply -var="live=true" -var="image_tag=v0.2.0" -var="service_desired_count=1"
```

This is the one flip that is deliberately manual (guide correction GC-2: the count
defaults to 0 so CW-1 could not churn failed pulls).

- [ ] ECS → all four services reach 1/1 running; target groups healthy →
      **`21-targets-healthy.png`**
- [ ] Confirm the consumer wiring actually reached the tasks:
```bash
aws ecs describe-task-definition --task-definition smartretailx-order --region eu-west-1 \
  --query "taskDefinition.containerDefinitions[0].environment[?name=='ORDER_EVENTS_QUEUE_URL'||name=='COMPENSATION_CONSUMER_ENABLED']"
aws ecs describe-task-definition --task-definition smartretailx-inventory --region eu-west-1 \
  --query "taskDefinition.containerDefinitions[0].environment[?name=='CONSUMER_ENABLED'||name=='SNS_TOPIC_ARN']"
```
      Both must return values. If `COMPENSATION_CONSUMER_ENABLED` is absent the order
      is placed but never leaves PENDING, which looks like a saga bug and is not one.
- [ ] Aurora wakes on the first inventory query (~15 s). Note the figure — you
      pre-warm at the viva.

## 5. Full chain and auth

- [ ] Re-run `./scripts/route-matrix.sh`: rows now 200/403 per the table →
      **`22-chain-200.png`**
- [ ] `POST /v1/orders` with a customer token → **201** → **`23-order-created.png`**
- [ ] Same request with the same `Idempotency-Key` → **200** and header
      `Idempotent-Replay: true`, and **no second order** → **`24-idempotency.png`**
- [ ] No token → **401**; admin route with a customer token → **403** →
      **`25-rbac.png`**
- [ ] Redact every Authorization header before saving a screenshot.

## 6. The saga on AWS (bonus — CW-3 material if time is short)

- [ ] Seed stock: `PATCH /v1/inventory/prod-laptop-001 {"quantity":10}` as admin.
- [ ] Order 3 → poll `GET /v1/orders/{id}` until **CONFIRMED**; stock 10 → 7 →
      **`26-saga-confirmed.png`**
- [ ] Order 50 → **REJECTED** with `insufficient stock for prod-laptop-001`;
      stock still 7 → **`27-saga-rejected.png`**
- [ ] Line items are capped at 100 by Pydantic, so ask for 50 rather than 999 —
      999 is refused at the edge with 422 and never reaches the saga.
- [ ] CloudWatch → `/ecs/smartretailx-order` and `/ecs/smartretailx-inventory`:
      capture the structured JSON showing `saga event published` and
      `saga outcome applied` with a shared correlation id → **`28-saga-logs.png`**

## 7. Park

- [ ] `terraform apply -var="live=false"` — NAT, EIP, egress route, ALB, listener,
      4 listener rules, API integration and 8 routes destroyed. ECS services are
      updated in place, not replaced.
- [ ] Console check: no NAT Gateway, no load balancer, EIP released.
- [ ] Ledger row in `docs/cost-ledger.md`, evidence-index ticks, ai-usage line,
      commit and push.

## Abort conditions

Stop and park if: the apply errors twice on the same resource, Aurora fails to reach
Available within 20 minutes, or anything unexpected appears in Billing.
