# SmartRetailX assignment screenshot catalogue

All 53 PNG files in `assignment-screenshots/` were opened and inspected at original resolution. Classification is based on visible content, not filenames. Originals must remain unchanged; create redacted copies only for the report/slide assets.

| No. | Filename | Visible system/service and action | Visible result/status/metric | Authenticated? | Evidence type | Task(s) | Valid? | Mislabelled? | Keep for report? | Recapture needed? |
|---:|---|---|---|---|---|---|---|---|---|---|
| 00 | `00-aws-credits.png` | AWS Billing credit page | $0 remaining/used and no active credits | N/A | Cost context | T1 | Yes, weak | No | Appendix/context only | Optional: real Cost Explorer/budget view is stronger |
| 10 | `10-internal-alb.png` | EC2 ALB details | `smartretailx-alb` active, scheme Internal, private subnets in two AZs | N/A | Deployment/config | T1, T2, T3, T5 | Yes | No | Yes | No; `49` is newer/stronger |
| 11 | `11-cognito-groups.png` | Cognito group list | `admin` and `customer` groups with precedence | N/A | Security config | T3 | Yes | No | Maybe | No; duplicates `46` conceptually |
| 12 | `12-orders-table.png` | DynamoDB orders table | Active, on-demand, PITR On; zero items at capture time | N/A | Deployment/config | T1, T5 | Yes | No | Yes | Optional current PITR page only |
| 15 | `15-ecs-services.png` | ECS cluster/services | Four active services and four running tasks, 1/1 each | N/A | Deployment state | T1, T2 | Yes | No | Yes | No; `40` is richer |
| 16 | `16-ecr-images.png` | ECR repositories | Four repositories, immutable tags, AES-256 | N/A | Deployment/security config | T1, T3 | Yes | No | Maybe | No; duplicates `42` conceptually |
| 21 | `21-route-matrix-200.png` | Terminal API route/auth matrix | Authenticated 200/403/404; missing/bad token 401; invalid route 404 | Yes where required | Executed API/security test | T2, T3, T8 | Yes, strong | No | Yes | No |
| 22 | `22-rbac-403.png` | Authenticated customer DELETE product request | HTTP 403; detail says admin group required | Yes; token held in variable, not printed | Executed RBAC negative test | T3, T8 | Yes, very strong | No — filename is correct | Yes | No |
| 23 | `23-saga-confirmed.png` | Authenticated GET order | Terminal status `CONFIRMED` with order details | Yes | Executed Saga result | T4, T8 | Yes, strong | No | Yes | No |
| 24a | `24-saga-rejected.png` | Authenticated POST deliberately excessive order | Accepted as `PENDING` | Yes | Executed Saga start | T4, T8 | Yes | No | Yes with next image | No |
| 24b | `24-saga-rejected1.png` | Authenticated GET same order | Terminal `REJECTED`, reason insufficient stock | Yes | Executed compensating Saga | T4, T5, T8 | Yes, strong | Filename suffix is awkward, content is correct | Yes | No |
| 25 | `25-stock-unchanged.png` | Authenticated admin inventory read after rejected order | Quantity remains 8 | Yes | Consistency/result evidence | T4, T8 | Yes in sequence | No | Yes with `24b` | No; explain that the sequence supplies context |
| 26 | `26-saga-logs.png` | CloudWatch tail for Order and Inventory | Reservation refused, `order-rejected` published, Saga outcome REJECTED | N/A | Logs/fault diagnosis | T4, T7, T8 | Yes, very strong | No | Yes | No |
| 27 | `27-xcache-hit.png` | Two authenticated product API reads | First `x-cache: MISS`, second `HIT` | Yes | Functional/cache test | T2, T6, T8 | Yes | No | Yes or appendix | No |
| 30 | `30-vpc-overview.png` | VPC overview/resource map | VPC available, `10.0.0.0/16`, six subnets and four route tables | N/A | Architecture deployment | T1, T5 | Yes | No | Yes | No |
| 31 | `31-subnets-list.png` | EC2 subnet list | Public/private/data tiers across `eu-west-1a` and `1b` | N/A | Architecture/HA config | T1, T5 | Yes, strong | No | Yes | No |
| 32 | `32-security-groups.png` | EC2 security-group list | Named Aurora, ECS, ALB and VPC Link groups | N/A | Security config | T2, T3 | Yes, medium | No | Appendix | Optional rule-level shot, not required |
| 33 | `33-nat-gateway.png` | NAT Gateway page | SmartRetailX NAT available/public in public subnet 1 | N/A | Network deployment | T1, T5 | Yes | No | Yes for cost/ADR | No |
| 34 | `34-s3-spa-bucket.png` | S3 SPA bucket objects | Only `assets/` and `index.html` visible at that time | N/A | Historical deployment | T1 | Authentic but superseded | No | No; P0 later added runtime/release files | No—use current CloudFront/SPA evidence instead |
| 36 | `36-aurora-cluster.png` | RDS Aurora cluster | Available PostgreSQL cluster/writer; internet access disabled | N/A | Database deployment/security | T1, T3, T5 | Yes, strong | No | Yes | Optional backup/capacity detail shot |
| 37 | `37-cloudfront-distribution.png` | CloudFront distribution | Two origins: API Gateway and S3 | N/A | Edge architecture | T1, T2, T3 | Yes | No | Yes | No |
| 38 | `38-waf-rules.png` | CloudFront-scope WAF | Three managed protections including common, bad-input and SQLi rules | N/A | Security configuration | T3, T8 | Yes, strong | No | Yes | No |
| 40 | `40-ecs-services-running.png` | ECS services page | Four application services running; Grafana service shown historical at 0/1 | N/A | Deployment state | T1, T2, T5 | Yes, historical | Grafana state is superseded, not mislabeled | Yes for four services; crop/annotate Grafana | Current four-service shot optional |
| 41 | `41-task-definition.png` | Product ECS task details | Task definition revision 10, app + ADOT containers, image digests | N/A | Container/tracing deployment | T1, T7 | Yes, strong | No | Yes | No |
| 42 | `42-ecr-repos.png` | ECR repositories | Four repos, immutable tags, AES-256 | N/A | Deployment/security config | T1, T3 | Yes | No | Yes | No; duplicates `16` conceptually |
| 43 | `43-api-gateway-routes.png` | HTTP API route list | Canonical `/v1` product/inventory/user/order routes | N/A | API deployment | T2, T3 | Yes, strong | No | Yes | No |
| 44 | `44-jwt-authorize.png` | API Gateway authorization view | JWT authorization attached to product/proxy routes | N/A | Auth configuration | T3 | Yes, strong | No | Yes | No |
| 45 | `45-cognito-pool.png` | Cognito user-pool overview | Pool/OIDC/JWKS details and five estimated users | N/A | Identity deployment | T3 | Yes | No | Yes | No |
| 46 | `46-cognito-groups.png` | Cognito groups | `admin` and `customer` visible | N/A | RBAC configuration | T3 | Yes | No | Yes | No; duplicates `11` conceptually |
| 47 | `47-sqs-queues.png` | SQS queue list | Three queues then, SSE-SQS, empty | N/A | Messaging configuration | T4, T5 | Yes, historical | Resource count now superseded | Appendix | Current four-queue view optional |
| 48 | `48-sns-topics.png` | SNS topics | SmartRetailX alerts and order-confirmed topics | N/A | Pub/sub configuration | T4, T7 | Yes | No | Yes | No |
| 49 | `49-internal-alb.png` | EC2 ALB details after reconciliation | Active internal ALB in two private AZ subnets | N/A | Deployment/security/HA | T1, T2, T3, T5 | Yes, very strong | No | Yes | No; preferred over `10` |
| 50 | `50-get-products-200.png` | Postman GET products | HTTP 200, authenticated, ~605 ms, product payload | Yes | Executed API test | T2, T3, T8 | Yes, strong | No | Yes only after redacting partial JWT/email if visible | Redacted copy required; fresh request optional |
| 51 | `51-post-order-201.png` | Postman POST order | HTTP 201, ~1.04 s, `PENDING` order | Yes | Executed order/API test | T2, T4, T8 | Yes, strong | No | Yes | No |
| 52 | `52-rbac-403.png` | Postman POST product without Authorization | HTTP 401 Unauthorized | No | Authentication-wall negative test | T3, T8 | Yes for 401 evidence | **Yes: filename says 403 but visible result is 401** | Keep only with corrected caption | No; `22` already proves real authenticated 403 |
| 53 | `53-saga-confirmed.png` | Postman GET orders | HTTP 200, ~390 ms; order shows `CONFIRMED` | Yes | Executed Saga/API result | T4, T8 | Yes, strong historical | No | Yes | No |
| 54 | `54-admin-create-product.png` | Postman admin POST product | HTTP 201, ~965 ms | Yes, admin | Executed admin CRUD/RBAC success | T2, T3, T8 | Yes, very strong | No | Yes | No |
| 55 | `55-get-inventory.png` | Postman admin GET inventory | HTTP 200, ~566 ms; stock payload | Yes, admin; token masked | Executed API/RBAC result | T2, T3, T4, T8 | Yes, strong | No | Yes | No |
| 56 | `56-idempotency-key.png` | Postman replay of order with same key | HTTP 200 and same order ID as the first response | Yes | Executed idempotency result | T4, T8 | Yes, strong | No | Yes | No |
| 60 | `60-cognito-sign-in.png` | Older custom SPA sign-in | UI explicitly says direct User Pool Authentication API | Credential entry UI | Historical auth UI | T3 | Authentic but obsolete for current mechanism | No | No as proof of current PKCE | **Yes: replace with current Hosted UI PKCE + callback evidence** |
| 61 | `61-spa-products-catalogue.png` | Authenticated customer SPA catalogue | 14 products, six categories | Yes, customer | Functional frontend result | T2, T3, T8 | Yes, strong historical | No | Yes after redacting email | Fresh current authenticated landing is recommended with PKCE sequence |
| 62 | `62-spa-place-order.png` | Authenticated customer checkout page | Product, quantity, summary and idempotency UX visible | Yes, customer | Frontend functional evidence | T2, T4, T8 | Yes, strong historical | No | Yes after redacting email | No |
| 63 | `63-spa-my-orders-live.png` | Authenticated customer My Orders | Customer identity, two confirmed orders and green `Live Sync` | Yes, customer | Real-time SPA result | T3, T4, T8 | Yes, very strong historical | No | Yes after redacting email | No; current mechanism recapture optional |
| 64 | `64-spa-admin-crud.png` | Authenticated admin product management | `ADMIN` role and full product CRUD UI visible | Yes, admin | RBAC/frontend result | T2, T3, T8 | Yes, very strong historical | No | Yes after redacting email | No |
| 65 | `65-spa-admin-stock.png` | Authenticated admin inventory UI | Stock table, quantities and save controls | Yes, admin | RBAC/inventory frontend result | T2, T3, T4, T8 | Yes, strong historical | No | Yes after redacting email | No |
| 66 | `66-eventbridge-pipes.png` | EventBridge Pipe details | Pipe Running; DDB Stream source/filter/EventBridge target; no records processed on this page | N/A | Deployed real-time configuration | T4, T7 | Yes | No | Yes | Optional metrics/execution shot; raw CW-5 supplies execution proof |
| 67 | `67-websocket-api.png` | API Gateway WebSocket routes | `$connect`, `$default`, `$disconnect`; custom authorizer on connect | N/A | WebSocket configuration | T3, T4 | Yes, strong | No | Yes | No |
| 68 | `68-lambda-functions.png` | Lambda function list | Seven functions visible at capture, including reconciliation/WS/notification | N/A | Serverless deployment | T1, T4, T7 | Yes, historical | Count now eight after outbox publisher | Yes/appendix | Current list optional |
| 69 | `69-cloudwatch-log-groups.png` | CloudWatch log-group list | API/ECS/Lambda groups visible; historical alarm sidebar state | N/A | Centralized logging configuration | T7 | Yes | No | Yes | Optional current dashboard shot is stronger |
| 70 | `70-k6-load-summary.png` | k6 terminal summary | 7m00.2s; 96,055 checks/requests; 100% checks; 0% request failures; 228.613642 req/s; avg 326.91 ms; med 282.98 ms; p90 494.9 ms; p95 623.76 ms; max 4.87 s; max 200 VUs | Not determinable from the screenshot; no token is visible | Executed historical performance test | T6, T8 | Yes, exceptionally strong | Filename is generic/imprecise; profile aligns with 7-minute 200-VU cache-busting stress test | Yes | No; fresh reconciled run optional |
| 71 | `71-cloudwatch-ecs-metrics.png` | CloudWatch ECS CPUUtilization graph | CPU around 0.27–0.29% in visible interval | N/A | Observed metric | T6, T7 | Yes | No | Yes with careful interpretation | Optional timestamp-correlated graph; does not prove scale-out |
| 72 | `72-autoscaling-policy.png` | ECS service autoscaling/deployment view | Min/max 1–5, CPU target 70%, service 1/1; “Rollback successful” visible | N/A | Autoscaling/rollback configuration | T5, T7 | Yes, strong | No | Yes | Actual scale-out graph optional |
| 73 | `73-cloudwatch-alarms.png` | CloudWatch alarms list | Ten alarms then; four ALARM/six OK in sidebar, including target-tracking low alarms | N/A | Alerting configuration/state | T5, T7 | Yes, historical | No | Use with historical-state caption | Optional current shot: read-only audit found 17/17 OK |

## Catalogue totals

- Total screenshots: **53**.
- Valid and useful evidence: **51**. The other two (`34`, `60`) are authentic historical captures but superseded for current claims.
- Conceptually duplicate/redundant files: **6 files in three pairs** (`10`/`49`, `11`/`46`, `16`/`42`), or three surplus selections when curating the report.
- Definitely mislabelled: **1** (`52-rbac-403.png` visibly shows 401). `70` is not invalid, but “load” is imprecise because its shape aligns with the seven-minute 200-VU stress profile.
- Obsolete for current-mechanism claims: **2** (`34` pre-P0 SPA contents; `60` direct-auth UI).
- Required fresh evidence before the final report: **one current authentication sequence, ideally two screenshots**—Hosted UI authorization-code/PKCE request and successful authenticated callback/SPA landing.
- Optional high-value recaptures: **five evidence targets**—current operations dashboard, X-Ray service map/trace, products Global Table regions, current 17/17-OK alarms, and actual autoscaling scale-out/recovery.

## Report-safety notes

- Keep every original unchanged.
- Use a redacted report copy of `50`; a bearer token fragment is visible.
- Redact/crop personal email addresses in `61`–`65`.
- Caption `52` as “missing token returns 401,” never as customer RBAC 403.
- Caption `70` as historical real-AWS performance/stress evidence and state only visible values; p99 is not shown.
- Historical screenshots should be dated/captioned as historical where later internals changed. They remain valid functional evidence.
