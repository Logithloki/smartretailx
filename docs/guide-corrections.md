# Guide corrections

Defects found in `docs/IMPLEMENTATION-GUIDE.md` while implementing it, each
corrected in the guide text itself and recorded here. These are **corrections,
not workarounds**: in each case the guide's instruction was incomplete or
wrong, and following it literally would have produced a broken system.

Worth a short paragraph in the report's methodology section — finding and
fixing defects in your own plan while executing it is evidence of engineering
judgement, and the viva panel is likely to ask why the code and the plan
differ. Cite the correction ID.

| ID | Area | Status |
|----|------|--------|
| GC-1 | SNS filter policy for the saga's confirm path | Corrected 2026-08-02, approved |
| GC-2 | ECS `desired_count` before images exist | Corrected 2026-08-02, approved |
| IC-1 | Test-user email domain | Corrected 2026-08-02 (self-inflicted, not a guide defect) |

---

## GC-1 — the order-events subscription must carry both event types

**What the guide said** (Week 2, Day 5):

> Also subscribe an **order-events SQS queue** to the SNS topic with a filter
> policy `{"eventType": ["order-rejected"]}` … this is the saga compensation
> receiver.

**Why it was wrong.** That filter admits only the rejection half of the saga.
Nothing else anywhere in the design moves an order from PENDING to CONFIRMED —
the Order Service publishes a command and then only ever learns the outcome
through this queue. With a rejected-only filter, every successful order stays
PENDING forever.

The guide contradicts itself on this point: its own Week 3 Day 5 gate requires
"create order → SQS → inventory consumes → Postgres decrements → SNS → order
flips CONFIRMED". Both statements cannot hold.

The wording is explicable — Week 2 was written before the publisher existed
(it lands in Week 3), so at that point in the narrative `order-rejected` was
the only event anyone published. The instruction was correct for the day it
was written and incomplete as a final design.

**Correction.** The subscription filters on both event types:

```hcl
filter_policy = jsonencode({
  eventType = ["order-confirmed", "order-rejected"]
})
```

One queue and one consumer handle both terminal transitions. Filtering stays
server-side, so the consumer is never woken for traffic it would discard.

**Where it lands:** `infra/messaging.tf`, `localstack-init/01-setup.sh`,
`services/order-service/app/compensation.py`.
**Evidence:** `scripts/saga-demo.sh` passes both directions; commit `81face4`.

---

## GC-2 — ECS desired_count must not be 1 before images exist

**What the guide said** (Week 1, Day 5):

> Four `aws_ecs_service` resources with `desired_count = var.live ? 1 : 0`

**Why it was wrong.** Week 1 creates the services; images do not reach ECR
until Week 2. With `desired_count = 1` at CW-1, ECS immediately tries to pull
a tag that does not exist, fails, retries, and trips the deployment circuit
breaker — leaving four FAILED deployments in the console during the very
window meant to demonstrate that the infrastructure is sound. The guide even
anticipates the symptom ("services will show 0 running; that's fine") without
noticing that its own configuration produces *failing* rather than *absent*
tasks.

**Correction.** A separate variable, defaulting to 0:

```hcl
desired_count = var.live ? var.service_desired_count : 0
```

`live` still gates everything billable, exactly as designed; the count is
raised to 1 in Week 2 once real images are pushed. Zero becomes clean rather
than failed.

**Where it lands:** `infra/compute.tf`, `infra/variables.tf`.
**Note:** raise it with `-var="service_desired_count=1"` at CW-2 (step 4 of
`docs/cw-2-runbook.md`).

---

## IC-1 — test users cannot live on a `.test` domain

**Provenance:** not a guide defect. `scripts/seed-users.sh` was written earlier
in this project and chose `@smartretailx.test`; the guide never specified an
address.

**Why it was wrong.** `.test` is reserved by RFC 2606 as a special-use domain,
and `email-validator` — which backs Pydantic's `EmailStr` — rejects it. The
User Service could not have deserialised its own seeded users, and the failure
would first have appeared at CW-2 rather than locally.

**Correction.** `@example.com`, which validates and is itself RFC 2606
reserved for documentation, so it can never route to a real mailbox — the
right property for seeded accounts.

**Where it lands:** `services/user-service/app/services.py`,
`scripts/seed-users.sh`, `scripts/route-matrix.sh`, `docs/cw-1-runbook.md`.
**Caveat for Week 4:** SES sandbox only delivers to *verified* addresses, so
the notification demo needs a real inbox you control — set
`SRX_CUSTOMER_EMAIL` when seeding rather than using the default.
