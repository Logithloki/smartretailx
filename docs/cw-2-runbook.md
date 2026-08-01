# CW-2 Runbook — second checkpoint window

**Goal:** confirm the CW-1 routing fix, then get User + Order services answering
through the full chain. **Budget:** ~3 hours, ≈ £0.75.
**Screenshots:** `20-…` series.

Carry-over from CW-1: the `overwrite:path` parameter mapping on the private
integration is **unverified on real AWS** — it is the first thing this window proves.

---

## 1. Pre-flight

- [ ] `git pull`; `terraform plan -var="live=true"` — read it.
- [ ] Confirm the plan shows `aws_apigatewayv2_integration.alb[0]` being **updated in place**
      with `request_parameters` gaining `overwrite:path` (not replaced).
- [ ] `terraform apply -var="live=true"`.

## 2. Verify the routing fix BEFORE building anything

Do this first — if the fix did not work, everything after it is wasted effort.

```bash
export SRX_TEST_PASSWORD='<your test password>'
./scripts/route-matrix.sh
```

- [ ] **No row returns 404** (except the deliberate `/v1/nonexistent` control).
      A 404 means the path is still not reaching the ALB — stop and re-diagnose.
- [ ] Every service row returns **503** at this point (no images yet). That is success.
- [ ] Screenshot the matrix → **`20-route-matrix-fixed.png`**

### The curl matrix

| # | Method | Path | Before images | After images | Meaning of a 404 |
|---|--------|------|---------------|--------------|------------------|
| 1 | GET | `/v1/orders` | 503 | 200 | path not forwarded |
| 2 | GET | `/v1/orders/{id}` | 503 | 200/404* | path not forwarded |
| 3 | GET | `/v1/inventory` | 503 | 503 (W3) | path not forwarded |
| 4 | GET | `/v1/inventory/{id}` | 503 | 503 (W3) | path not forwarded |
| 5 | GET | `/v1/users` | 503 | 200 | path not forwarded |
| 6 | GET | `/v1/users/{id}` | 503 | 200 | path not forwarded |
| 7 | GET | `/v1/products` | 503 | 503 (W3) | path not forwarded |
| 8 | GET | `/v1/products/{id}` | 503 | 503 (W3) | path not forwarded |

\* Once the Order Service is live, a 404 for a genuinely missing order id is an
**application** 404 with a FastAPI JSON body — distinguish it from the ALB's
`{"error":"route not found"}`. Always check the body, not just the status.

**Control row:** `GET /v1/nonexistent` must return the ALB body
`{"error":"route not found"}` — that proves the default rule still fires, so the
absence of 404s above is meaningful rather than an artefact.

**If a 404 reappears**, pull the access log and read the new `path` field:
```bash
MSYS_NO_PATHCONV=1 aws logs filter-log-events \
  --log-group-name "/aws/apigateway/smartretailx" \
  --region eu-west-1 --limit 20 --query "events[].message" --output text
```
`routeKey` populated + `integrationError: "-"` + 404 ⇒ the backend rejected the
path, i.e. the mapping is still wrong. `routeKey: "$default"` ⇒ API Gateway
itself never matched a route.

## 3. Build and push ARM64 images

```bash
ECR=$(aws ecr get-authorization-token --region eu-west-1 --query 'authorizationData[0].proxyEndpoint' --output text)
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin "${ECR#https://}"
docker buildx build --platform linux/arm64 -t <ecr-url>/smartretailx/order-service:v0.2.0 --push services/order-service
docker buildx build --platform linux/arm64 -t <ecr-url>/smartretailx/user-service:v0.2.0 --push services/user-service
```

- [ ] Tags are immutable — bump `image_tag` rather than reusing `v0.1.0`.
- [ ] `terraform apply -var="live=true" -var="image_tag=v0.2.0" -var="service_desired_count=1"`
- [ ] ECS → both services reach 1/1 running, target groups healthy → **`21-targets-healthy.png`**

## 4. Full chain and auth

- [ ] Re-run `./scripts/route-matrix.sh`: orders/users rows now 200 → **`22-chain-200.png`**
- [ ] `POST /v1/orders` with a customer token → **201** → **`23-order-created.png`**
- [ ] No token → **401**; admin-only route with a customer token → **403** → **`24-rbac.png`**
- [ ] Redact every Authorization header before saving a screenshot.

## 5. Park

- [ ] `terraform apply -var="live=false"` — 18 destroyed; NAT and ALB gone.
- [ ] Ledger row, evidence-index ticks, ai-usage line, commit and push.
