# Cost Ledger — SmartRetailX

Standing rule (guide §0): one entry per LIVE session — date, length, purpose, estimated cost.
Screenshot Cost Explorer at each month end. This ledger is a report exhibit (cost chapter).

Budget: $50 CloudWatch billing alarm (may raise to $75 in the final month).

| Date | Session / event | Duration | Purpose | Est. cost | Actual (Cost Explorer) |
|------|-----------------|----------|---------|-----------|------------------------|
| 2026-07-14 → 2026-08-02 | **Unparked old stack (lesson entry)** | ~19 days | Old-design infra (VPC + NAT + ECR + DDB) applied 14 Jul and left running — NAT Gateway `nat-040cb5edec9d238b6` billed continuously | — | **$22.06 (July)** + ~$1.15/day into August until destroyed |
| 2026-08-02 | Audit + Week-1 correction session (no apply) | — | Read-only audit; corrected Terraform authored; stack still pending manual `terraform destroy` | $0 | — |

## Lessons

- **2026-08-02:** Never leave a stack applied without the `live` toggle. The July NAT burn
  ($22.06, ~44% of budget) produced zero deliverables. From now on: park after every session
  (guide standing rule 1); the `live=false` default and gated NAT/route make "parked ≈ $0" real.

## Month-end Cost Explorer screenshots

| Month | Screenshot | Amount |
|-------|------------|--------|
| 2026-07 | _pending — capture at next console session_ | $22.06 |
