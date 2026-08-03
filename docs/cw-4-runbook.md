# CW-4 Runbook — Week 4 checkpoint window (notifications & housekeeping)

**Executed:** 2026-08-03 (session 16:47–17:15 UTC)
**Budget:** ~2 hours, £0.75 estimated. Actual: ~30 minutes (single unpark + park).
**Screenshots:** `30-…` series in `assignment-screenshots/`.

This is a **completed** runbook (all live commands were executed on real AWS during
this session). The commands are preserved so the check can be replayed for the viva
and for the second dry-run before the final demo.

## Pre-flight (already satisfied — kept for viva replay)

- `terraform apply -var="live=true" -var="service_desired_count=1"` — unparked in
  ~10 min. Plan showed 42 adds, 5 in-place changes, 4 immutable task-def revisions.
- SES sender identity `logithsivakumar07@gmail.com` is `VerificationStatus: Success`.
  Verified before this session; nothing was resent.
- Cognito test users seeded through `admin-create-user`:
  - `logithsivakumar07@gmail.com` in the `customer` group (also SES sandbox recipient — same address for sender and recipient because SES sandbox limits both sides).
  - `admin@example.com` in the `admin` group.

Both passwords set via `admin-set-user-password --permanent` from an environment
variable (`$env:SRX_TEST_PASSWORD`) — never a file, never a commit.

## 1. Fetch JWTs

```powershell
$POOL   = terraform output -raw cognito_user_pool_id
$CLIENT = terraform output -raw cognito_app_client_id
$auth = aws cognito-idp admin-initiate-auth `
  --user-pool-id $POOL --client-id $CLIENT `
  --auth-flow ADMIN_USER_PASSWORD_AUTH `
  --auth-parameters USERNAME=logithsivakumar07@gmail.com,PASSWORD=$env:SRX_TEST_PASSWORD `
  --region eu-west-1 --output json | ConvertFrom-Json
$env:CUSTOMER_TOKEN = $auth.AuthenticationResult.IdToken
```

Repeat for `admin@example.com` → `$env:ADMIN_TOKEN`.

## 2. Place a real order — confirm SES email arrives

```powershell
$API = terraform output -raw api_endpoint
$custH = @{ Authorization = "Bearer $env:CUSTOMER_TOKEN"; 'Idempotency-Key' = 'cw4-first-order' }
$body = @{ items = @(@{ productId='prod-laptop-001'; productName='MacBook Pro 14'; quantity=2; unitPrice='1299.99' }) } | ConvertTo-Json -Compress
Invoke-WebRequest -Uri "$API/v1/orders" -Headers $custH -Method POST -ContentType 'application/json' -Body $body -UseBasicParsing
```

Observed result during this session:
- POST returned **201** with `orderId=ord-971430cce104`, `status=PENDING`.
- Within 3 seconds a follow-up `GET /v1/orders/{id}` returned `status=CONFIRMED`.
- Inventory stock decremented from 10 → 8 (order for 2).
- Gmail inbox received **"Order ord-971430cce104 confirmed"** email (SES MessageId
  `0102019fc88697ec-30680389-a28a-4eb7-b878-6d4a2b21ac0b-000000`).

**Screenshots to capture:**
- `30-ses-verified.png` — Console → SES → Verified identities → `logithsivakumar07@gmail.com` shows Verified.
- `31-order-confirmation-email.png` — Gmail: order-confirmed email opened, subject and body visible.
- `32-correlation-log-single-trace.png` — CloudWatch → Log groups → Log Insights, query:
  ```
  fields @timestamp, service, correlationId, message
  | filter correlationId = "corr-cw4-first-order"
  | sort @timestamp asc
  ```
  Shows the same `correlationId` appearing across `/aws/ecs/order-service`, `.../inventory-service`, `/aws/lambda/smartretailx-notification`.
- `34-xray-service-map.png` — Console → CloudWatch → X-Ray traces → search TraceId
  `1-6a70c649-4606a59c149d36d42d9b0997` (captured this session) → service map shows
  the whole hop (Order Service → SQS → Inventory Service → SNS → notification
  Lambda → SES).

## 3. Idempotency proof

Manually invoke the notification Lambda **twice with the same synthetic SNS
MessageId**. Idempotency wrapper must return the cached result on the second call.

```powershell
$eventBody = @{
  Records = @(@{
    EventSource = 'aws:sns'
    Sns = @{
      MessageId = 'cw4-idempotency-test-msg-1'
      Message = (@{
        eventType='order-confirmed'; orderId='ord-idem-test-42';
        userId='user-idem'; userEmail='logithsivakumar07@gmail.com';
        correlationId='corr-idem'
      } | ConvertTo-Json -Compress)
    }
  })
} | ConvertTo-Json -Depth 5 -Compress
$f = New-TemporaryFile; Set-Content -Path $f.FullName -Value $eventBody -Encoding utf8
aws lambda invoke --function-name smartretailx-notification `
  --region eu-west-1 --payload fileb://$($f.FullName) `
  --cli-binary-format raw-in-base64-out out1.json
aws lambda invoke --function-name smartretailx-notification `
  --region eu-west-1 --payload fileb://$($f.FullName) `
  --cli-binary-format raw-in-base64-out out2.json
```

Observed:
```
1st: {"processed":1, "results":[{"sent":true, "messageId":"0102019fc887e133-6cb62c99-…-000000"}]}
2nd: {"processed":1, "results":[{"messageId":"0102019fc887e133-6cb62c99-…-000000", "sent":true}]}
```
Same `messageId` on the second call → SES was **not** invoked twice; Powertools
returned the cached result. **Screenshot `33-idempotency-cached.png`** — terminal
showing both responses side-by-side, with the identical MessageId highlighted.

## 4. Reconciliation Lambda manual invoke

```powershell
$f = New-TemporaryFile; Set-Content -Path $f.FullName -Value '{}' -Encoding utf8
aws lambda invoke --function-name smartretailx-stock-reconciliation `
  --region eu-west-1 --payload fileb://$($f.FullName) `
  --cli-binary-format raw-in-base64-out recon-out.json
Get-Content recon-out.json
```

Observed: `{"stuck": 0, "cutoffMinutes": 30, "orders": []}` — no stuck orders (saga
is fast enough that nothing lingers in PENDING > 30 min).

**Screenshots:**
- `35-scheduler-enabled.png` — Console → EventBridge → Schedules →
  `smartretailx-stock-reconciliation` in state **ENABLED**, timezone `Asia/Colombo`,
  cron `cron(0 0 * * ? *)`.
- `36-reconciliation-clean.png` — CloudWatch → log group
  `/aws/lambda/smartretailx-stock-reconciliation` → recent invocation shows
  `stuck: 0`.

## 5. Auth wall smoke (evidence carry-over from CW-1)

Without a token: `GET /v1/products` → **401** (recaptured this session,
`10-auth-wall-401.png` still valid).

## 6. Park (mandatory)

```powershell
cd infra
terraform apply -var="live=false"
```

Parked state cost: ≈£0/day. Verify: `aws ecs describe-services … --query "services[].desiredCount"` shows `0`.

## Result

**CW-4 pass criteria met on 2026-08-03:**
- ✅ Real SES email delivered to Gmail (order confirmation).
- ✅ Idempotency wrapper suppressed second delivery of the same SNS MessageId.
- ✅ X-Ray trace covers Order → SQS → Inventory → SNS → notification Lambda → SES.
- ✅ Reconciliation Lambda runs cleanly on demand; schedule is ENABLED in Asia/Colombo.
- ✅ Auth wall unchanged (401 without JWT).
