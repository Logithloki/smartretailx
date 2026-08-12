# SmartRetailX final retail features design

## Goal

Close the two explicit COMP60010 Task 4 gaps while turning the existing SPA into a credible retail application. The work adds authoritative pricing, promotions, fulfilment/delivery, a secure user-deletion path, a cart, customer-safe availability, an operations view, and cancellation compensation. It preserves the existing ECS, API Gateway, Cognito, DynamoDB, Aurora, SQS, SNS, EventBridge, Pipes and WebSocket architecture.

## Boundaries and ownership

Product Service exclusively creates and changes products and creates/edits/enables/disables promotions. Promotions are retained for historical interpretation rather than hard-deleted. It owns the promotions DynamoDB table and emits native-stream `promotion.price-refresh` and `product.price-refresh` invalidations. Order Service owns order totals, immutable price snapshots, order cancellation state and fulfilment state. Inventory Service owns stock reservations and their release ledger. User Service is the only component that invokes Cognito administrative user deletion.

Order Service receives a deliberately narrow, read-only pricing read model: `dynamodb:GetItem`/`BatchGetItem` on products and `dynamodb:GetItem`/`Query` only on the promotions table and its required active-promotions index. It receives no pricing writes, scans or wildcard DynamoDB access. This is the demo-scale CQRS trade-off: it avoids adding a new internal transport/auth subsystem when no secure inter-service mechanism already exists, while Product Service retains all write ownership.

## Pricing and promotions

`POST /v1/orders` accepts only `productId` and positive `quantity`; Pydantic forbids unknown fields, so `unitPrice`, `price`, and `totalAmount` cause a 422 response. Order Service resolves each product and all applicable current promotions itself. The pricing calculation uses `Decimal`, rounds monetary values to two decimal places with `ROUND_HALF_UP`, and chooses one best applicable percentage promotion (largest discount, promotion ID as deterministic tie-breaker). Events never determine a price.

An order line persists `productId`, `productName`, `quantity`, `baseUnitPrice`, `effectiveUnitPrice`, `unitDiscount`, `lineDiscount`, `lineTotal`, and optional `promotionId`. Order totals are `subtotal`, `discountTotal`, and `totalAmount`. Old rows using `unitPrice` remain readable by mapping that field to the new snapshot values with zero discount. Product responses expose base/effective pricing and a safe promotion summary.

Promotions support percentage discounts, `PRODUCT` or `CATEGORY` scope, `enabled`, and UTC `startsAt`/`endsAt` boundaries. They are calculated at every product and order read. Product Service reconcilers race through conditional lifecycle writes; the successful record is converted by an EventBridge Pipe into at-least-once `promotion.price-refresh`. Price-changing Product writes similarly produce `product.price-refresh`. A missed event cannot change the authoritative calculation; it only delays a browser refetch.

## Event and WebSocket model

Application-created commands and outcomes use `srx_common.EventEnvelope`: `fulfilment-status-changed`, `order-cancel-requested`, and `order-cancelled` are the new contracts. Native DynamoDB Stream/Pipe events retain AWS record semantics and use `order.status-changed`, `promotion.price-refresh`, and `product.price-refresh`. The WebSocket public output is `catalogue.price-refresh`. The existing order outbox gains a `destination` field: commands are delivered to SQS and domain events to EventBridge. Thus fulfilment and cancellation event publication is transactionally tied to its Order write.

The WebSocket push Lambda has two explicit branches:

- A private branch queries `userId-index` and can push only a matched user's `order.status-changed`, `order.fulfilment-changed`, or `order.cancelled` message.
- A public catalogue branch scans only connection IDs and sends `catalogue.price-refresh` with a revision and affected product IDs. It contains no order ID, user ID, customer data or price authority. Catalogue clients refetch Product Service data after receiving it.

Tests prove that private traffic cannot reach another user and that public traffic cannot carry private fields.

## Fulfilment and cancellation

Order reservation status remains `PENDING`, `CONFIRMED` or `REJECTED`. Fulfilment is a separate state: `NOT_STARTED`, `PACKING`, `DISPATCHED`, `OUT_FOR_DELIVERY`, `DELIVERED`. The admin-only fulfilment endpoint permits only forward transitions on a confirmed, non-cancelling order. Conditional DynamoDB writes include the current fulfilment and order state, preventing `PACKING -> DISPATCHED` and cancellation from both succeeding.

Eligible customers may request cancellation only from `CONFIRMED` plus `NOT_STARTED`/`PACKING`. The transaction moves the order to `CANCEL_PENDING` and adds `order-cancel-requested` to the existing outbox. Inventory records every successful reservation in Aurora. Its cancellation consumer atomically records the incoming event, changes that reservation from `RESERVED` to `RELEASED`, increments exactly the recorded stock lines, and writes `order-cancelled` to its outbox. Duplicate commands, publisher retries and restarts observe the inbox/reservation ledger and cannot release stock twice. Order consumes the final event and conditionally becomes `CANCELLED`.

## HTTP API and UI

New routes are versioned and JWT-protected. Admin-only routes manage promotions, fulfilment, operations and user deletion; customer routes read catalogue/availability, create own orders and cancel only their own eligible order.

The SPA gains a persistent local cart, stock-aware product cards and checkout, Admin Promotions, Admin Fulfilment, and an application operations dashboard. Cart prices are display-only. Checkout sends IDs/quantities only and renders the returned server price snapshot. Availability is a public read-only Inventory endpoint; it is advisory while the inventory reservation remains the final concurrency control.

## Infrastructure and deployment limits

Terraform adds only the promotions table, narrow IAM grants, EventBridge/EventBridge-target permissions, container environment variables and the existing route mappings needed for new `/v1` paths. Aurora receives a single forward-only Alembic migration for the reservation ledger. LocalStack gets a matching promotions table. No Terraform state operation, apply, destroy, import, live data mutation, deployment, commit or push is permitted.

## Verification and assignment impact

Each phase follows red-green-refactor: focused test must fail before code changes, then pass, then relevant existing tests run. The final evidence maps price trust/RBAC to Task 3; promotions, live prices, delivery, WebSockets and choreography to Task 4; cancellation retry/idempotency to Task 5; and automated/API/component tests to Task 8.
