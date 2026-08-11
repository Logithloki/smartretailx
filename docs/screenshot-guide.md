# Master Screenshot Guide

This guide consolidates all required screenshots (00 to 80s) for your assignment evidence pack into one simple checklist. 
Save all screenshots in the `assignment-screenshots/` directory.

## 00s: Base Requirements
- [ ] **`00-aws-credits.png`**: AWS Billing Console → Credits. Shows your AWS credits to prove cost management.
- [ ] **`01-billing-alarm.png`**: AWS Billing Console → Budgets/Alarms. Shows your $50/£40 budget alarm is active.

## 10s: Week 1 (Corrected Infrastructure)
- [ ] **`10-aurora-auto-pause.png`**: RDS Console. Show the Aurora cluster status as "Paused" to prove Serverless v2 scale-to-zero.
- [ ] **`11-auth-wall.png`**: Postman/Browser. Show a `401 Unauthorized` when calling `/v1/orders` without a JWT token.
- [ ] **`12-cognito-pool.png`**: Cognito Console. Show the `smartretailx-users` pool.
- [ ] **`13-dynamodb-pitr.png`**: DynamoDB Console. Show Point-in-Time Recovery (PITR) is enabled on the `smartretailx-orders` table.

## 20s: Week 2 (Microservices & VPC Link)
- [ ] **`20-internal-alb.png`**: EC2 Console → Load Balancers. Show the ALB is `internal` and in private subnets.
- [ ] **`21-api-gw-vpc-link.png`**: API Gateway Console → VPC Links. Show the VPC link connecting API Gateway to your internal ALB.
- [ ] **`22-successful-api-call.png`**: Postman/Browser. Show a `201 Created` or `200 OK` when calling `/v1/orders` with a valid JWT.
- [ ] **`23-rbac-denied.png`**: Postman/Browser. Log in as a normal customer and try to call an admin route (e.g., `DELETE /v1/products/123`). Show the `403 Forbidden` response.

## 30s: Week 3 (Saga Pattern & Resilience)
- [ ] **`30-saga-confirmed.png`**: DynamoDB Console. Show an order in the `CONFIRMED` state (proves the happy path of the saga).
- [ ] **`31-saga-rejected.png`**: DynamoDB Console. Show an order in the `REJECTED` state (proves the compensation path of the saga worked when inventory failed).
- [ ] **`32-dlq-alarm.png`**: CloudWatch Console. Show the `smartretailx-orders-dlq-depth` alarm.

## 40s: Week 4 (Notifications & Idempotency)
- [ ] **`40-ses-verified.png`**: SES Console → Verified Identities. Show your email address is verified.
- [ ] **`41-idempotency.png`**: DynamoDB Console → `smartretailx-idempotency` table. Show a stored idempotency key.
- [ ] **`42-cloudwatch-structured-log.png`**: CloudWatch Logs Insights. Query the notification lambda logs to show a structured JSON log containing the `correlationId`.
- [ ] **`43-reconciliation-schedule.png`**: EventBridge Scheduler. Show the `smartretailx-stock-reconciliation` schedule is active.

## 50s: Week 5 (WebSockets, EventBridge Pipes & CI/CD)
- [ ] **`50-pipes-running.png`**: EventBridge Pipes Console. Show the `smartretailx-order-status` pipe is in the `Running` state.
- [ ] **`51-live-websocket.png`**: Browser. Show the SmartRetailX Web App updating an order status live without refreshing the page.
- [ ] **`52-github-actions-success.png`**: GitHub Actions. Show a successful green pipeline run (build, test, deploy).
- [ ] **`53-github-secrets-empty.png`**: GitHub Repo Settings → Secrets. Show there are NO AWS access keys stored (proves Zero Trust OIDC).

## 60s: Week 6 (UI, Observability & Multi-Region)
- [ ] **`60-cognito-email.png`**: Gmail. Screenshot the beautiful HTML "Welcome to SmartRetailX - Your Verification Code" email you receive upon signup.
- [ ] **`61-admin-users.png`**: Web App. Log in as Admin, go to `/admin/users`, and screenshot the Cognito user directory.
- [ ] **`62-delete-account.png`**: Web App. Click "Delete Account" and screenshot the GDPR self-service deletion confirmation.
- [ ] **`63-grafana.png`**: Grafana. Access via the CloudFront URL and screenshot the dashboard showing metrics (e.g., API 5xx errors or CPU).
- [ ] **`64-xray-map.png`**: CloudWatch → X-Ray Traces → Service Map. Screenshot the full architecture graph (API GW → Order Service → DDB → SQS).
- [ ] **`65-global-table.png`**: DynamoDB Console → `smartretailx-products` → Global Tables. Screenshot showing `eu-west-1` and `ap-south-1` active.

## 70s: Week 7 (Testing & Security)
- [ ] **`70-k6-load-test.png`**: Terminal. Show the k6 summary output after a load test run.
- [ ] **`71-autoscaling-graph.png`**: CloudWatch Metrics. Show the ECS tasks scaling up from 1 to 5 during the k6 load test.
- [ ] **`72-chaos-recovery.png`**: ECS Console. Kill a task manually, then screenshot the ECS event log showing a new task starting automatically to replace it.
- [ ] **`73-zap-bandit-reports.png`**: Terminal/Browser. Show the output of the OWASP ZAP or Bandit security scans.

## 80s: Final Evidence
- [ ] **`80-cost-explorer.png`**: AWS Cost Explorer. Screenshot your parked vs live billing graph (critical for the Cost chapter of the report).
- [ ] **`81-rto-drill-timing.png`**: Terminal. Run `terraform destroy`, then `terraform apply`. Screenshot the terminal showing the "Apply complete!" execution time (e.g., 11m 45s) to prove your Disaster Recovery RTO.
