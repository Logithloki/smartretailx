# SmartRetailX Load Testing with k6

This directory contains comprehensive k6 test scripts for the SmartRetailX platform.

## Prerequisites

- Install [k6](https://k6.io/docs/get-started/installation/)
- A valid CloudFront URL pointing to the API Gateway
- A valid Cognito JWT Bearer token

## Tests Overview

1. **Load Test (`load-test.js`)**: Evaluates performance under expected production loads (50 VUs). Target: `/v1/products`.
2. **Stress Test (`stress-test.js`)**: Pushes system to breaking point (200 VUs) to test ECS autoscaling and API Gateway throttling (rate: 50, burst: 100).
3. **Spike Test (`spike-test.js`)**: Simulates sudden traffic bursts (150 VUs) to verify system stability and recovery.
4. **Order Smoke Test (`order-smoke.js`)**: Verifies the order saga flow (1-2 VUs) with a `loadTest` flag to prevent SES spam.
5. **Concurrent Users (`concurrent-users.js`)**: Runs an eight-minute, three-VU catalogue profile below the single-runner WAF rate limit. Override `CONCURRENT_USERS` only when traffic is distributed across approved test sources.

## Running Tests

Set the necessary environment variables and run a script using the `k6 run` command:

```bash
# Load Test
k6 run --env BASE_URL=https://<your-cloudfront-id>.cloudfront.net --env AUTH_TOKEN=<your-jwt-token> k6-tests/load-test.js

# Stress Test
k6 run --env BASE_URL=https://<your-cloudfront-id>.cloudfront.net --env AUTH_TOKEN=<your-jwt-token> k6-tests/stress-test.js

# Spike Test
k6 run --env BASE_URL=https://<your-cloudfront-id>.cloudfront.net --env AUTH_TOKEN=<your-jwt-token> k6-tests/spike-test.js

# Order Smoke Test
k6 run --env BASE_URL=https://<your-cloudfront-id>.cloudfront.net --env AUTH_TOKEN=<your-jwt-token> k6-tests/order-smoke.js
```

## CloudWatch Observability

While tests are running, monitor the following metrics in AWS CloudWatch:

- **ECS CPUUtilization**: Should spike > 70%, triggering ECS autoscaling to scale from 1 → 5 tasks.
- **API Gateway RequestCount & 4XX/5XX Errors**: To observe throttling hits (429 Too Many Requests).
- **ALB TargetResponseTime**: To track backend latency variations.
- **Application Logs**: Check ECS container logs for unexpected panics or DB connection saturation.
