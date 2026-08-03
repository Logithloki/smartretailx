# CW-4 + CW-5 raw session evidence — 2026-08-03

This file captures the raw command output from the single window that closed
both Week 4 (notifications) and Week 5 chunk 1 (Pipes + WebSocket seams). It
exists so the report can quote actual timestamps and IDs, and so a viva examiner
can see the tests were really executed end-to-end without polishing.

**Region:** `eu-west-1`
**Session start:** 2026-08-03 ≈ 16:47 UTC (apply live=true)
**Session end:** 2026-08-03 ≈ 17:15 UTC (this evidence saved)
**Account:** `322551984077`

## Terraform outputs after unpark

```
api_endpoint             = https://e5yvcy9p5m.execute-api.eu-west-1.amazonaws.com/
websocket_endpoint       = wss://ik50k8qsle.execute-api.eu-west-1.amazonaws.com/prod
websocket_api_id         = ik50k8qsle
orders_event_bus_arn     = arn:aws:events:eu-west-1:322551984077:event-bus/smartretailx-events
orders_event_bus_name    = smartretailx-events
orders_table_stream_arn  = arn:aws:dynamodb:eu-west-1:322551984077:table/smartretailx-orders/stream/2026-08-01T21:39:32.077
cognito_user_pool_id     = eu-west-1_QutfhUEHK
cognito_app_client_id    = 270ec376iist6pggvkukqdtjsc
```

## ECS service state after apply

```
+---------+----------------------------------+----------+-----------+
| desired |              name                | pending  |  running  |
+---------+----------------------------------+----------+-----------+
|  1      |  smartretailx-order-service      |  0       |  1        |
|  1      |  smartretailx-inventory-service  |  0       |  1        |
|  1      |  smartretailx-user-service       |  0       |  1        |
|  1      |  smartretailx-product-service    |  0       |  1        |
+---------+----------------------------------+----------+-----------+
```

## SES sender verification

```
{
    "VerificationAttributes": {
        "logithsivakumar07@gmail.com": {
            "VerificationStatus": "Success"
        }
    }
}
```

## CW-4 Step 1 — auth wall + products smoke

```
== 1. Auth wall (no token) - expect 401 ==
  status: 401
== 2. Products list as customer ==
  status: 200
  body: {"products":[{"productName":"MacBook Pro 14","price":"1299.99",
        "category":"Electronics","description":null,"productId":"prod-laptop-001"}],
        "count":1}
```

## CW-4 Step 2 — real order → SES email

```
POST /v1/orders (as customer, Idempotency-Key: cw4-first-order)
  status: 201
  body: {"orderId":"ord-971430cce104","userId":"e265c4c4-50d1-7084-c072-07a0a32ad148",
         "status":"PENDING", ... "totalAmount":"2599.98", ...}

Poll GET /v1/orders/ord-971430cce104:
  [t=3s] status=CONFIRMED
```

**Inventory stock after order (expect 8):**
```
{"productId":"prod-laptop-001","quantity":8,"updatedAt":"2026-08-03T16:48:09.218796Z"}
```

**Notification Lambda log (single invocation):**
```
INIT_START Runtime Version: python:3.12.mainlinev2.v27 ...
START RequestId: 4b4e36b9-aece-4638-a3e5-30f0c218988d Version: $LATEST
{"level":"INFO","location":"deliver:102","message":"notification sent",
 "timestamp":"2026-08-03 16:48:11,861+0000","service":"notification-lambda",
 "cold_start":true,"function_name":"smartretailx-notification",
 "function_memory_size":"256",
 "function_arn":"arn:aws:lambda:eu-west-1:322551984077:function:smartretailx-notification",
 "function_request_id":"4b4e36b9-aece-4638-a3e5-30f0c218988d",
 "orderId":"ord-971430cce104","eventType":"order-confirmed",
 "messageId":"0102019fc88697ec-30680389-a28a-4eb7-b878-6d4a2b21ac0b-000000",
 "xray_trace_id":"1-6a70c649-4606a59c149d36d42d9b0997"}
REPORT Duration: 1853.84 ms Init Duration: 470.23 ms Max Memory Used: 110 MB
XRAY TraceId: 1-6a70c649-4606a59c149d36d42d9b0997 Sampled: true
```

**SES MessageId `0102019fc88697ec-30680389-a28a-4eb7-b878-6d4a2b21ac0b-000000`
was accepted at 16:48:11 UTC.** The Gmail inbox `logithsivakumar07@gmail.com`
should show a "Order ord-971430cce104 confirmed" email dated 2026-08-03 16:48 UTC
(≈ 22:18 IST); capture `31-order-confirmation-email.png` from Gmail directly.

## CW-4 Step 3 — idempotency

Same synthetic SNS MessageId `cw4-idempotency-test-msg-1` invoked twice:

```
== 1st invocation ==
  StatusCode: 200
  {"processed":1,"results":[{"sent":true,
    "messageId":"0102019fc887e133-6cb62c99-e7ef-4989-9065-fae9f025f7b9-000000"}]}

== 2nd invocation (same MessageId - expect suppression) ==
  StatusCode: 200
  {"processed":1,"results":[
    {"messageId":"0102019fc887e133-6cb62c99-e7ef-4989-9065-fae9f025f7b9-000000",
     "sent":true}]}
```

Second response returned the **identical** SES MessageId → Powertools Idempotency
cached the first result. SES was not called twice.

## CW-4 Step 4 — reconciliation Lambda

```
== Manually invoke reconciliation Lambda ==
  StatusCode: 200
  response: {"stuck":0,"cutoffMinutes":30,"orders":[]}
```

Schedule is `smartretailx-stock-reconciliation`, cron `cron(0 0 * * ? *)`,
timezone `Asia/Colombo`, state ENABLED (Terraform-managed).

## CW-5 Step 2 — Pipes baseline (no WS client)

**ws-push Lambda log immediately after the CW-4 order:**
```
START RequestId: 4d6a9a11-01a4-47e3-9bfa-0cf64f57af16
[INFO] ws push: no active connections for user e265c4c4-50d1-7084-c072-07a0a32ad148
END RequestId: 4d6a9a11-01a4-47e3-9bfa-0cf64f57af16
REPORT Duration: 1219.85 ms Init Duration: 318.08 ms Max Memory Used: 96 MB
XRAY TraceId: 1-6a70c64b-3499967c7a50843003a042f3 Sampled: true
```

Prove point: the DDB Stream MODIFY on `ord-971430cce104` (PENDING → CONFIRMED)
travelled through Pipes → bus → EventBridge rule → ws-push Lambda. The Lambda
correctly reported "no active connections" because no client was attached.

## CW-5 Step 3 — live WebSocket push

Started `python scripts/ws-listen.py` (customer JWT in `?token=`):

```
[t=0.00s] connecting to wss://ik50k8qsle.execute-api.eu-west-1.amazonaws.com/prod ...
[t=3.45s] connected (authorizer accepted token)
[t=3.45s] waiting up to 90s for status push ...
```

Placed a new order in the parallel shell:
```
POST /v1/orders (Idempotency-Key: cw5-ws-live-order)
  orderId: ord-f6c9745b753a (initial status PENDING)
```

Listener received:
```
[t=39.19s] << {"type": "order.status-changed", "orderId": "ord-f6c9745b753a", "status": "CONFIRMED"}
```

End-to-end latency ~36 s from POST → push. The bulk of that is one SQS
`ReceiveMessage` long-poll cycle (20 s) and normal saga round-trip.

## CW-5 Step 4 — authorizer denial

```
== WS with FAKE token (this.is.not.a.jwt) ==
INVALID_STATUS: server rejected WebSocket connection: HTTP 403
```

Authorizer Lambda invocation (short-circuit deny, ~230 ms):
```
START RequestId: f3b52438-f222-4081-8e69-82b122161853
END   RequestId: f3b52438-f222-4081-8e69-82b122161853
REPORT Duration: 230.04 ms Init Duration: 306.00 ms Max Memory Used: 69 MB
XRAY TraceId: 1-6a70c725-5d211cde01a8db61105e79d8 Sampled: true
```

No connect message was billed because the handshake terminates at authorizer
denial.
