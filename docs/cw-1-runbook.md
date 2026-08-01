# CW-1 Runbook — first checkpoint window

**Goal:** prove the corrected infrastructure applies, the auth wall works, and Aurora
auto-pauses — then park. **Budget:** ~2 hours, ≈ £0.30–0.60.
**Expected end state:** screenshots `10-…`–`19-…` captured, stack parked, ledger updated.

Nothing runs any application code this window: `service_desired_count` is 0 because no
images exist in ECR yet. A JWT-authenticated call returning **503** is the correct result —
it proves the request traversed API Gateway → VPC Link → internal ALB and found no targets.

---

## 1. Pre-flight

- [ ] `git pull` — confirm you are on commit `4d2fac2` or later.
- [ ] `cd infra && terraform plan -var="live=true"` — **read it**. Expect `110 to add, 0 to change, 0 to destroy`.
- [ ] Note the start time. Aurora cluster creation dominates (~10 min); budget 12–15 min total.

## 2. Apply

- [ ] `terraform apply -var="live=true"` — review, type `yes`.
- [ ] Confirm the state object now exists: `aws s3 ls s3://smartretailx-tfstate-322551984077/smartretailx/`
- [ ] `terraform output` → paste values into `docs/aws-values.txt` (gitignored, stays local).

## 3. Verify the architecture in the console (screenshots)

- [ ] **`10-internal-alb.png`** — EC2 → Load Balancers → scheme is **internal**, subnets are the two *private* ones.
- [ ] **`11-alb-sg.png`** — the ALB security group: inbound is the VPC Link SG only, **no 0.0.0.0/0**.
- [ ] **`12-data-subnet-rt.png`** — VPC → Route Tables → `smartretailx-data-rt`: only the local route plus the two gateway endpoints. **No 0.0.0.0/0.**
- [ ] **`13-dynamodb-orders.png`** — orders table: PITR **On**, `userId-index` present, **TTL disabled**.
- [ ] **`14-products-streams.png`** — products table: `category-index` + Streams NEW_AND_OLD_IMAGES.
- [ ] **`15-cognito-pool.png`** — the single Terraform pool, with `admin` and `customer` groups.
- [ ] **`16-http-api-authorizer.png`** — HTTP API → Authorization: JWT authorizer attached to all eight `/v1/*` routes.

## 4. Prove the auth wall

```bash
export SRX_TEST_PASSWORD='<choose a 12+ char password; do not commit it>'
./scripts/seed-users.sh
API=$(terraform -chdir=infra output -raw api_endpoint)
```

- [ ] **No token → 401.** `curl -i "$API/v1/products"` → **`17-401-no-token.png`**
- [ ] **Garbage token → 401.** `curl -i -H "Authorization: Bearer not.a.jwt" "$API/v1/products"`
- [ ] **Valid token → 503.** 
      `TOKEN=$(./scripts/get-jwt.sh customer@smartretailx.test)` then
      `curl -i -H "Authorization: Bearer $TOKEN" "$API/v1/products"` → **`18-503-valid-token.png`**
      *(503 = authoriser passed, ALB reached, no targets yet. This is the win.)*
      **Redact the Authorization header before saving any screenshot.**
- [ ] **Hosted UI exists.** Open `terraform output -raw cognito_hosted_ui_url` + 
      `/login?client_id=<client_id>&response_type=code&scope=openid+email+profile&redirect_uri=http://localhost:5173`
      → login page renders → **`19-hosted-ui.png`**

## 5. Aurora auto-pause — the money screenshot

- [ ] Note the time the cluster became **Available**.
- [ ] Leave it idle ~10–15 min (do step 6 meanwhile).
- [ ] RDS → cluster → Monitoring → **ServerlessDatabaseCapacity** drops to **0 ACU** → **`19b-aurora-autopause.png`**.
- [ ] Record the observed wake latency later (~15 s on first query) — you will pre-warm at the viva.

## 6. While waiting

- [ ] Subscribe to alerts (one-time, needs an email click):
      `aws sns subscribe --topic-arn $(terraform -chdir=infra output -raw alerts_topic_arn) --protocol email --notification-endpoint <your email>`
      then confirm from your inbox.
- [ ] Screenshot the Billing → Credits page as **`00-aws-credits.png`** if not already done.
- [ ] Confirm both CloudWatch alarms exist (DLQ depth, queue depth) in `INSUFFICIENT_DATA` — that is normal with no traffic.

## 7. Park

- [ ] `terraform apply -var="live=false"` — expect **18 to destroy**: NAT, EIP, egress route, ALB, listener, 4 listener rules, API integration, 8 routes.
      *Resolved after CW-1:* the four ECS services are **updated in place**, not replaced, when the
      `load_balancer` block drops — confirmed against real state. No service churn on park.
- [ ] Console check: **no NAT Gateway**, **no load balancer**, EIP released → **`19c-parked.png`**.
- [ ] Confirm Aurora shows 0 ACU / paused.

## 8. Close out

- [ ] Add a row to `docs/cost-ledger.md`: date, duration, "CW-1", estimated £.
- [ ] Tick the `10s` row in `docs/evidence-index.md`.
- [ ] Add one line to `docs/ai-usage-log.md`.
- [ ] `git add assignment-screenshots docs && git commit -m "docs: CW-1 evidence" && git push`

## Abort conditions

Stop and park immediately if: the apply errors twice on the same resource, Aurora fails to
reach Available within 20 minutes, or anything unexpected appears in Billing. A parked stack
costs pennies; a confused live one costs pounds.
