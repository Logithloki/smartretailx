# Cost Ledger — SmartRetailX

Standing rule (guide §0): one entry per LIVE session — date, length, purpose, estimated cost.
Screenshot Cost Explorer at each month end. This ledger is a report exhibit (cost chapter).

Budget: $50 CloudWatch billing alarm (may raise to $75 in the final month).

| Date | Session / event | Duration | Purpose | Est. cost | Actual (Cost Explorer) |
|------|-----------------|----------|---------|-----------|------------------------|
| 2026-07-14 → 2026-08-02 | **Unparked old stack (lesson entry)** | ~19 days | Old-design infra (VPC + NAT + ECR + DDB) applied 14 Jul and left running — NAT Gateway `nat-040cb5edec9d238b6` billed continuously | — | **$22.06 (July)** + ~$1.15/day into August until destroyed |
| 2026-08-02 | Audit + Week-1 correction session (no apply) | — | Read-only audit; corrected Terraform authored | $0 | — |
| 2026-08-02 | **`terraform destroy` — old stack removed** | ~2 min | 37 resources destroyed incl. NAT `nat-040cb5edec9d238b6`; billing leak stopped; account now ~$0/day | $0 | August NAT cost ≈ $1–2 (1–2 days) |
| 2026-08-03 | **CW-4 + CW-5 live window (unpark → test → park)** | ~30 min | Unpark to `live=true` (NAT, ALB, ECS 1 task/service, WSS API, Pipes, notification+push+authorizer Lambdas); run CW-4 evidence (order → SES email, idempotency, reconciliation) and CW-5 evidence (WebSocket connect, live status push, authorizer 403); park back to `live=false`. Screenshots outstanding but raw text evidence captured. | ~£0.30 (NAT + Aurora min-warm + Lambda invocations) | — |

## Lessons

- **2026-08-02:** Never leave a stack applied without the `live` toggle. The July NAT burn
  ($22.06, ~44% of budget) produced zero deliverables. From now on: park after every session
  (guide standing rule 1); the `live=false` default and gated NAT/route make "parked ≈ $0" real.

## Month-end Cost Explorer screenshots

| Month | Screenshot | Amount |
|-------|------------|--------|
| 2026-07 | _pending — capture at next console session_ | $22.06 |
