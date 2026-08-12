# Final retail feature implementation

## Scope completed locally

| Capability | Implementation | Authority and safety property |
|---|---|---|
| Server-authoritative money | Order Service accepts only `productId` and `quantity`; prices, discounts and totals are Decimal snapshots. | A browser-supplied `unitPrice` is rejected (`extra=forbid`). |
| Promotions | Product Service owns admin create/edit/enable-disable and conditional `SCHEDULED -> ACTIVE -> EXPIRED` lifecycle projections. | Promotions are retained rather than hard-deleted; checkout reads `enabled`, `startsAt`, and `endsAt` directly. |
| Price freshness | Promotions and Products DynamoDB Streams -> EventBridge Pipes -> WebSocket push -> authoritative SPA API refetch. | Public messages contain only product IDs and revision; delayed events cannot make checkout pricing wrong. |
| Fulfilment | Admin conditional progression: `NOT_STARTED -> PACKING -> DISPATCHED -> OUT_FOR_DELIVERY -> DELIVERED`. | Order state and EventEnvelope outbox record are written in one DynamoDB transaction. |
| Stock-aware cart | Bounded availability endpoint, multi-line CartContext, and response-backed checkout confirmation. | Availability is advisory; Order Service response renders authoritative subtotal/discount/total. |
| Operations | Admin fulfilment queue and existing product, stock and user administration. | Admin RBAC is enforced by backend dependencies. |
| Cancellation compensation | Order cancellation request, inventory reservation ledger, and `order-cancelled` outcome. | `RESERVED -> RELEASED` is preserved; duplicate release changes zero stock. |

## Multi-task promotion reconciliation

Every Product Service task may run reconciliation, but each lifecycle move is a
conditional DynamoDB `UpdateItem`. Only one task can win a particular state
transition. The stream record is then handled by the existing zero-glue Pipe
pattern. Pipe delivery is at-least-once, which is safe because its public
message requests an idempotent catalogue refetch and never affects pricing.

## Event and privacy contract

Private order and fulfilment events are routed only to connections found via
`userId-index`. Public promotion events use a paginated connection-ID scan,
prune stale API Gateway connections, reject source records containing private
fields, and whitelist the outbound payload. No customer/order/user field is
carried in the public branch.

## Runtime event contract table

| Event | Producer | Transport | Consumer | Visibility | Purpose |
|---|---|---|---|---|---|
| `order-created` | Order Service transactional outbox | DynamoDB Stream -> outbox Lambda -> SQS | Inventory Service | Private command | Request an inventory reservation. |
| `order-confirmed` | Inventory Service Aurora outbox | SNS -> filtered SQS | Order Service | Private domain outcome | Complete the reservation Saga successfully. |
| `order-rejected` | Inventory Service Aurora outbox | SNS -> filtered SQS | Order Service | Private domain outcome | Compensate an order when stock cannot be reserved. |
| `order-cancel-requested` | Order Service transactional outbox | DynamoDB Stream -> outbox Lambda -> SQS | Inventory Service | Private command | Request exactly-once release of a durable reservation. |
| `order-cancelled` | Inventory Service Aurora outbox | SNS -> filtered SQS | Order Service | Private domain outcome | Move `CANCEL_PENDING` to `CANCELLED`. |
| `fulfilment-status-changed` | Order Service transactional outbox | EventBridge | WebSocket push Lambda | Private domain event | Notify the owning customer of delivery progression. |
| `order.status-changed` | Orders DynamoDB Stream | EventBridge Pipe -> EventBridge | WebSocket push Lambda | Private native-stream event | Notify the owning customer of Saga/cancellation status. |
| `promotion.price-refresh` | Promotions DynamoDB Stream | EventBridge Pipe -> EventBridge | WebSocket push Lambda | Public invalidation | Signal a promotion lifecycle/configuration refresh. |
| `product.price-refresh` | Products DynamoDB Stream | EventBridge Pipe -> EventBridge | WebSocket push Lambda | Public invalidation | Signal a base-price refresh without publishing money. |
| `catalogue.price-refresh` | WebSocket push Lambda | API Gateway WebSocket | React catalogue | Public invalidation | Refetch affected products, or all products for an empty ID list. |

Application-created commands/outcomes use `srx_common.EventEnvelope`. The
native DynamoDB Stream/Pipe events retain AWS stream-record semantics instead.
There are no separate runtime `price-updated` or `inventory-released` event
types; those were superseded design labels, not additional contracts.

## Evidence-oriented tests

Focused tests cover client price rejection, current-record pricing after a
stale browser observation, promotion boundaries (`startsAt <= now < endsAt`),
multi-task lifecycle races, public/private WebSocket separation, fulfilment
outbox atomicity, availability projection, reservation-ledger idempotence, and
the cancellation-versus-dispatch race.

## Deployment status

No Terraform apply, AWS CLI mutation, infrastructure deployment, commit, or
push was performed. Terraform resources added or changed are source-only and
must be reviewed in a normal plan before any deployment window.
