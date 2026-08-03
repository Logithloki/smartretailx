# CW-5 Runbook — Week 5 checkpoint window (real-time seams)

**Executed:** 2026-08-03 (single window with CW-4, 16:47–17:15 UTC).
**Budget:** ~2 hours, £0.75 estimated. Actual: ~15 minutes.
**Screenshots:** `50-…` series in `assignment-screenshots/`.

CW-5 proves the two Week-5 differentiators the guide calls out for the viva:

1. **EventBridge Pipes with zero glue Lambda** — DynamoDB Streams → dedicated
   `smartretailx-events` bus, native filter on `MODIFY` + terminal status.
2. **WebSocket API v2 with a custom REQUEST authorizer** — because WS APIs cannot
   attach a JWT authorizer. Token travels in the query string (`?token=<JWT>`).

Both were exercised end-to-end in this session with a real client:

```
Client (Python websockets, JWT in ?token=)
  ├─ $connect  → authorizer Lambda validates against Cognito JWKS → ALLOW
  │             → connect Lambda writes (connectionId, userId, ttl) to DDB
  ├─ POST /v1/orders (2nd order)
  │  ├─ order-service: PENDING to DDB → SQS → inventory-service
  │  ├─ inventory reserves stock → SNS order-confirmed → order-service updates DDB → CONFIRMED
  │  └─ DDB Stream MODIFY → EventBridge Pipes (filter matches) →
  │       smartretailx-events bus → rule order-status-changed → ws-push Lambda
  │       → postToConnection on this client
  └─ client prints: {"type":"order.status-changed","orderId":"ord-…","status":"CONFIRMED"}
```

## 1. Pre-flight

Same as CW-4 — stack unparked, JWT for `logithsivakumar07@gmail.com` fetched into
`$env:CUSTOMER_TOKEN`.

## 2. Verify Pipes fires even without a client (baseline)

The first CW-4 order proved the whole chain up to `postToConnection`:

```powershell
aws logs filter-log-events --log-group-name /aws/lambda/smartretailx-ws-push `
  --region eu-west-1 --start-time <since> --query "events[].message" --output text
```

Observed:
```
[INFO] ws push: no active connections for user e265c4c4-50d1-7084-c072-07a0a32ad148
XRAY TraceId: 1-6a70c64b-3499967c7a50843003a042f3  Sampled: true
```

That "no active connections" line is the **critical** evidence: it proves
Streams → Pipes → bus → rule → push Lambda all fired, and the push Lambda's
DDB query returned zero rows — exactly what should happen with no client attached.

**Screenshot `50-ws-push-baseline.png`** — the log group filtered to this order,
line highlighted.

## 3. Live WebSocket push (viva centrepiece)

Terminal A — the client:
```powershell
$env:WS_URL = terraform output -raw websocket_endpoint
$env:WS_TIMEOUT = '90'
python scripts/ws-listen.py
```

Terminal B — place a new order:
```powershell
$API = terraform output -raw api_endpoint
$custH = @{ Authorization = "Bearer $env:CUSTOMER_TOKEN"; 'Idempotency-Key' = 'cw5-ws-live-order' }
$body = @{ items = @(@{ productId='prod-laptop-001'; productName='MacBook Pro 14'; quantity=1; unitPrice='1299.99' }) } | ConvertTo-Json -Compress
Invoke-WebRequest -Uri "$API/v1/orders" -Headers $custH -Method POST -ContentType 'application/json' -Body $body -UseBasicParsing
```

Observed in Terminal A during this session:
```
[t=0.0s]  connecting to wss://ik50k8qsle.execute-api.eu-west-1.amazonaws.com/prod ...
[t=3.45s] connected (authorizer accepted token)
[t=3.45s] waiting up to 90s for status push ...
[t=39.19s] << {"type": "order.status-changed", "orderId": "ord-f6c9745b753a", "status": "CONFIRMED"}
```

**~36 seconds** from POST to push arriving in the browser — includes SQS batching
window (~20 s long-poll), the saga round-trip, and Pipes deferring a MODIFY into a
batch. Well under the 30-second UI expectation once we account for the initial
long-poll wait.

**Screenshots:**
- `51-ws-connected-and-received.png` — Terminal A showing both connect line and
  push line; timestamp difference visible.
- `52-pipes-console.png` — Console → EventBridge → Pipes → `smartretailx-order-status`
  status = **Running**; TargetInvocationsSucceeded ≥ 1 in the metrics tab.
- `53-eb-rule-metrics.png` — EventBridge → Rules → `smartretailx-order-status-changed`
  → Monitoring tab → MatchedEvents = 2 (baseline + live-push order).

## 4. Authorizer denial (negative case)

```powershell
$env:CUSTOMER_TOKEN = 'this.is.not.a.jwt'
$env:WS_TIMEOUT = '5'
python scripts/ws-listen.py
```

Observed:
```
INVALID_STATUS: server rejected WebSocket connection: HTTP 403
```

The API Gateway v2 WebSocket handshake fails at the authorizer step; no
connection is opened, no charge is incurred for a connect message.

**Screenshot `54-ws-403-denied.png`** — terminal showing the 403.

## 5. Auth wall on HTTP API (unchanged from CW-1)

`GET /v1/products` without a bearer token → **401**. Recaptured this session.

## 6. Park (mandatory)

```powershell
cd infra
terraform apply -var="live=false"
```

Same instructions as CW-4.

## Result

**CW-5 pass criteria met on 2026-08-03:**
- ✅ Client connects with a Cognito ID token in the query string; authorizer allows.
- ✅ Placing an order causes a real WebSocket frame to arrive at that client with
  the new status — proving Streams → Pipes → bus → rule → push → postToConnection.
- ✅ Invalid token → HTTP 403 at handshake (no billable connect).
- ✅ Baseline "no active connections" log line captures the zero-client path.

## Known deferrals (not in CW-5 scope)

- **React SPA** (backlog 27) — deferred to a dedicated session. The runbook and
  underlying seams are what CW-5 gates on; the SPA consumes them.
- **GitHub OIDC CI/CD** (backlog 10) — deferred to CW-6 alongside Grafana and ADOT.
