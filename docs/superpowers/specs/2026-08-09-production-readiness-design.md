# SmartRetailX Production-Readiness Design

**Status:** Approved by the implementation brief dated 2026-08-09.

## Objective

Turn the current demo-capable SmartRetailX baseline into an internally consistent,
production-style assignment implementation without destroying or blindly replacing
the existing AWS stack. The application, Terraform, tests, delivery workflows,
evidence and documentation must describe the same system.

## Safety Boundary

- Preserve the current dirty working tree and all assignment screenshots.
- Work on `codex/production-readiness`.
- Never run `terraform apply`, `terraform destroy`, destructive state commands, or
  mutating AWS CLI commands without explicit user approval.
- Treat the current flat Terraform stack as the preserved `baseline` environment.
- Do not combine provider upgrades, resource-address moves, state splitting and ECS
  deployment-strategy migration in one change.
- Any plan that replaces Cognito, Aurora, DynamoDB, the SPA bucket, CloudFront, ECR,
  API Gateway, the VPC, or IAM/OIDC must stop for review.

## Delivery Order

1. Correct the current application and delivery baseline.
2. Add tests for every behavioral correction using red-green-refactor.
3. Harden asynchronous failure paths and observability.
4. Introduce runtime frontend configuration and immutable release artifacts.
5. Build reusable, blocking CI and digest-based CD.
6. Add environment-isolated Terraform alongside the preserved baseline.
7. Add production protection, HA and a Terraform-ready, non-continuous DR design.

## Canonical Edge Contract

The only public API prefix is `/v1`. CloudFront forwards `/v1/*` to HTTP API v2
with caching disabled and the Authorization header preserved. `/api/*` is removed.
The SPA, k6, smoke scripts, Postman collection and documentation all use `/v1`.

## Authentication

The browser uses Cognito Managed Login/Hosted UI through `react-oidc-context` and
`oidc-client-ts` using authorization code, state, nonce and PKCE. Direct
`USER_PASSWORD_AUTH` is removed from the production frontend. The active session is
held in session storage, renews through library behavior, validates callback state,
handles expiry, and logs out through Cognito. UI roles come only from
`cognito:groups`; backend RBAC remains authoritative.

Runtime settings are loaded and schema-validated before React starts. The immutable
bundle consumes API URL, WebSocket URL, Cognito authority/client/redirect/logout,
environment and release ID from `/config.json`.

## Reliable Order Publication

Order Service writes the order and an `order-created` outbox record in one DynamoDB
transaction. The outbox table has its own stream. An order-command publisher Lambda
consumes INSERT records, validates the versioned event, sends it to the orders SQS
queue, then marks the outbox item delivered. Lambda/event-source retries and an
on-failure SQS queue make publication observable and recoverable. A send-success /
mark-failure race can duplicate the command, so the inventory inbox is the final
idempotency boundary.

## Inventory Inbox/Outbox

One Aurora transaction:

1. checks `processed_order_commands.order_id`;
2. reserves every inventory line only when the command is new;
3. persists the terminal result;
4. inserts a versioned event in `inventory_outbox`;
5. commits.

Redelivery reads the stored result and never reserves stock again. A background
publisher claims pending outbox rows, publishes SNS, and marks them delivered. A
publish failure leaves the row retryable. Alembic owns schema changes; production
startup no longer performs uncontrolled schema creation.

## Event Contract

Important events carry `eventType`, `eventVersion`, `eventId`, `timestamp`,
`correlationId`, `aggregateId`, and a typed `payload`. HTTP middleware accepts a
valid `X-Correlation-ID` or creates a UUID, binds it to structured logging, returns
it in the response, and propagates it into commands and outcomes.

## WebSocket Isolation

The connection table gains a `userId-index`. Terminal order events retain the owning
user ID. The push Lambda queries only that user's connections and never scans or
broadcasts to unrelated users. Access logs omit query strings/tokens. TLS remains
mandatory; the query-token limitation is documented until a larger protocol change
is justified.

## Deployment Model

Pull requests have blocking Python, frontend, Terraform, security, LocalStack,
OpenAPI and event-contract checks. A merge builds one release: ARM64 images, Lambda
ZIPs, SPA archive, checksums, SBOMs and a release manifest.

ECS deployment resolves and records ECR digests, registers exact digest-based task
definitions, preserves the previous revision, updates the service, waits for stable
state, inspects deployment/target health and runs smoke tests. Any failed check or
rollback fails the job. Rolling deployment with ECS circuit breaker and CloudWatch
alarms is the required strategy.

Formal promotion is development -> test -> staging -> production using the same
release manifest. Production uses a reviewed Terraform plan followed by GitHub
Environment approval. Sandbox is isolated and never promotes automatically.

## Infrastructure Evolution

The current root remains the baseline until address-preserving migration is proven.
New reusable module/environment roots use isolated state keys and names. Persistent
production resources receive deletion protection, PITR/retention and no
`force_destroy`. Production uses at least two stateless service tasks where cost
permits. EU DR is Terraform-ready/pilot-light in `eu-central-1`; product-only Mumbai
replication remains unchanged.

## Verification Standard

No feature is called complete solely because configuration exists. Completion needs
fresh local tests and, where AWS behavior is claimed, explicitly approved AWS
verification. Anything not deployed is labelled configured, not verified.

