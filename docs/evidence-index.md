# Evidence Index — SmartRetailX

Every screenshot in `assignment-screenshots/` indexed against the Task 1–8 brief requirements
(guide Appendix E numbering scheme, Appendix F traceability matrix).

## Screenshot series plan (Appendix E)

| Series | Content | Status |
|--------|---------|--------|
| 00 | AWS credits page · billing alarm | pending |
| 10s | Corrected infra applied · auth wall (401 without JWT) · Aurora auto-pause observed | pending (CW-1) |
| 20s | Services responding via API GW → VPC Link → ALB | pending (CW-2) |
| 30s | Saga both paths (CONFIRMED / REJECTED) · DLQ alarm | pending (CW-3) |
| 30s | **Week 4 — notifications.** `30` SES verified-identity console · `31` real order-confirmation email in the inbox · `32` CloudWatch structured JSON showing one correlation id across API/SQS/SNS/Lambda · `33` idempotency suppressing a second delivery of the same SNS MessageId · `34` X-Ray service map including the notification hop · `35` stock-reconciliation schedule ENABLED in Asia/Colombo · `36` reconciliation alert for an order stuck in PENDING | pending (CW-4) |
| 40s | (renumbered — Weeks 5–6 seams: Pipes, WebSocket, CloudFront, OIDC, Grafana, ADOT, Global Table) | pending (CW-3/CW-4) |
| 50s | Pipes event flow · WebSocket live status in browser · empty GitHub secrets page | pending (CW-5) |
| 60s | Grafana dashboards · X-Ray service map · Global Table both regions | pending (CW-6) |
| 70s | k6 graphs · autoscaling 1→5 · chaos task-kill timeline · ZAP/bandit reports | pending (Week 7) |
| 80s | Cost Explorer monthly · destroy→apply DR timing drill | pending (Week 7/8) |

## Traceability matrix (Appendix F — fill as evidence lands)

| Brief requirement | Where implemented | Evidence |
|---|---|---|
| T1 microservices/ECS/Lambda/multi-region | infra/compute.tf, Global Table | 10s, 62 |
| T2 ≥3 services, /v1, Swagger, inter-service comms | services/*, /docs | 20s, 30s |
| T3 OAuth2/JWT/RBAC/secrets/GDPR/PCI | Cognito TF, middleware, managed pwd | 10s, 21, report §3 |
| T4 real-time, events, eventual consistency, saga | Pipes, WS, SNS/SQS, compensation | 30s, 50s |
| T5 retries, breaker, LB, autoscaling, multi-AZ, DR | tenacity/pybreaker, ALB, RTO drill | 70s, 84 |
| T6 load/stress testing + analysis | k6 + CloudWatch | 70s |
| T7 logging, tracing, dashboards, alerting | Powertools, X-Ray, Grafana, alarms | 40s, 60s |
| T8 unit/integration/API/e2e/security tests | pytest+moto, LocalStack CI, ZAP/bandit | 74–77 |
