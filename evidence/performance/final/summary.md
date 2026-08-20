# Final non-production performance summary

Date: 20 August 2026
Environment: Test
Production: not touched

## Bounded application profile

GitHub Actions run `32360229422` executed the authenticated concurrent profile for eight minutes with three virtual users. The runner completed 947 iterations and 1,894 HTTP requests at 3.94 requests per second. All 1,894 checks passed and the failed-request rate was 0%.

| Metric | Result |
|---|---:|
| Average | 261.18 ms |
| p90 | 425.87 ms |
| p95 | 430.99 ms |
| p99 | 451.39 ms |
| Maximum | 685.35 ms |
| API Gateway 4xx | 0 |
| API Gateway 5xx | 0 |
| WAF blocked requests | 0 |

CloudWatch recorded the same 1,894 API Gateway requests. Peak ECS CPU was 11.25% for Product, 1.05% for Order, 1.15% for Inventory and 0.69% for User. Peak memory stayed between 9.57% and 12.50%. Autoscaling was not observed because this bounded profile remained well below the configured CPU target.

## Edge rate-control profile

Run `32358604668` used a single runner and reached 50 virtual users. It produced 34,636 requests, of which 31,828 were blocked by the CloudFront WAF `per-ip-rate-limit` rule. API Gateway received 2,809 requests in that window, confirming that the large 403 volume originated at the edge rather than in the services.

The WAF rule was not disabled, raised or bypassed. This run proves the deployed edge rate control, not application scalability. Its mixed response latency must not be used as an application latency measurement. Machine-readable results for both runs are stored beside this summary.

## Interpretation

The bounded profile demonstrates healthy behavior at the assignment's demo-scale load: zero request failures, zero API 4xx/5xx responses, low ECS utilization and latency within the profile thresholds. It does not prove production-scale capacity or autoscaling behavior. A distributed load source would be required to exercise materially higher traffic without conflating the result with the intentional per-IP WAF control.
