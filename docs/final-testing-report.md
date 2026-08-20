# SmartRetailX final testing report

Date: 20 August 2026
Scope: Development, Test and Staging only
Production: not touched

## Release baseline

The storefront sign-in regression was corrected in merge `c6964283f668f7e7c289429fec6930aebf064635` and immutable build `32356155756` (`c6964283f668-78`). Development and Test served this release during the focused validation. Staging remained on `f0d345097529-76` until the final evidence changes were ready for one orderly immutable promotion.

## Regression diagnosis

The first Test browser run exposed two independent test/application defects:

1. successful custom Cognito sign-in did not navigate from `/login` to `/products`; the auth state updated, but the page remained on the sign-in route;
2. the order-summary E2E read a newly opened popup during its initial blank document before the signed S3 URL navigation committed.

The application redirect and Playwright synchronization were fixed at their sources. No assertion, RBAC rule or security control was weakened.

## Concurrency and distributed correctness

Focused repository tests passed for final-unit contention, twenty-way stock contention, concurrent idempotent checkout, cancellation versus dispatch, duplicate administrator transitions and duplicate event delivery. The results and exact invariants are in `evidence/testing/concurrency/`.

The tests exercise the actual conditional persistence boundaries: an atomic Aurora decrement, DynamoDB conditional idempotency claims, conditional fulfilment updates and deterministic outbox identifiers.

## Persona and business acceptance

The Test Newman suite executed 22 requests and 32 assertions with zero failures. It covered JWT enforcement, Customer/Admin RBAC, product administration, order idempotency, the order Saga, inventory access, fulfilment operations and private order-summary authorization.

Playwright covered the public storefront, custom sign-in, product browsing, cart checkout, terminal Saga status, Customer-to-Admin denial, Admin fulfilment and product/inventory administration. Cancellation, insufficient-stock compensation and duplicate delivery are covered in the service and LocalStack integration suites.

See `evidence/testing/client-acceptance-matrix.md` for the persona matrix and evidence layer for each result.

## Performance and edge protection

A 50-VU, 14-minute single-runner catalogue profile reached the deployed CloudFront WAF rate control. It generated 34,636 HTTP requests at 41.21 requests/second; 31,828 requests were blocked by the edge control. API Gateway saw only 2,809 requests, one 4xx and one 5xx in the same window, confirming that the 403 volume did not originate in the services.

This run is edge-protection evidence, not an application scalability result. The WAF rule was not disabled or bypassed. A separate eight-minute profile with three virtual users completed 1,894 requests with 0% failures, p95 430.99 ms and p99 451.39 ms. CloudWatch recorded zero API 4xx/5xx responses, zero WAF blocks and peak ECS CPU of 11.25%. Autoscaling was not observed because the bounded profile did not reach its target. Full results are in `evidence/performance/final/summary.md`.

## Resilience

During authenticated Test traffic, one `smartretailx-test-product-service` task was stopped. ECS created a different replacement task and restored desired/running count in 81.9 seconds. The exact task identifiers and timestamps are in `evidence/resilience/ecs-task-recovery.json`.

This experiment validates scheduler self-healing at demo scale. It does not prove zero downtime with a desired count of one, multi-AZ capacity under every failure mode, or production-scale resilience.

## Security regression

- PR CI secret scan passed with no broad suppression.
- Unauthenticated Test probes returned 200 for `/` and 401 for `/v1/products`.
- Customer admin mutations remained 403; cross-customer order resources remained 404.
- The order-summary bucket retained all four S3 Block Public Access controls and AES-256 server-side encryption.
- Signed summary URLs remained short-lived and were obtained only through the JWT-authorized order API.
- No credentials, tokens, verification codes or TOTP values were stored in evidence.

## Final acceptance

Final immutable release metadata and environment promotion results are recorded after the evidence PR merge. Completion requires the same release in Development, Test and Staging, including green Test/Staging seed, smoke, 32-assertion Newman and the expanded responsive Playwright gates.

No known P0/P1 defect may remain when this report is finalized.
