# Commerce concurrency validation

Date: 20 August 2026
Environment: isolated repository tests; Test runtime validation is recorded separately
CI run: `32358575679`

The suite exercises the persistence operations that form the concurrency boundaries. It does not rely on frontend state or timing sleeps.

| Scenario | Expected invariant | Result | Evidence |
|---|---|---|---|
| Two buyers compete for the final unit | One reservation succeeds, one fails, final stock is zero | PASS | `test_two_concurrent_buyers_cannot_oversell_last_item` |
| Twenty attempts compete for five units | Exactly five reservations succeed and stock never becomes negative | PASS | `test_twenty_concurrent_attempts_never_consume_more_than_five` |
| Two checkouts use one idempotency key | One order and one outbox command are committed | PASS | `test_concurrent_same_key_creates_one_order_and_one_command` |
| Cancellation races dispatch | Exactly one valid transition wins; no cancel-pending/dispatched combination exists | PASS | `test_cancellation_and_dispatch_race_allows_exactly_one_transition` |
| Two administrators dispatch the same order | One update wins, one conflicts, one deterministic outbox event exists | PASS | `test_two_admins_cannot_emit_duplicate_dispatch_transitions` |
| Duplicate command/event delivery | Stock, compensation and notification handlers remain idempotent | PASS | Inventory inbox/outbox, order compensation and notification idempotency suites |

The implementation boundaries under test are the conditional Aurora stock decrement, DynamoDB conditional idempotency claim, conditional fulfilment transition and deterministic outbox event identifiers.
