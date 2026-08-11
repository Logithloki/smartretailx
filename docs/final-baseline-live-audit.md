# SmartRetailX Final Baseline Live Audit

**Audit date:** 2026-08-11  
**Repository:** `D:\APIIT\ECADWP_2\Implementation\smartretailx`  
**Branch:** `codex/production-readiness`  
**AWS account:** `322551984077`  
**AWS region:** `eu-west-1`  
**Terraform environment:** `environment_name=baseline`, `live=true`, `enable_grafana=false`  
**Backend/workspace:** Existing configured S3 backend, workspace `default`; unchanged  
**Saved plan:** `infra/baseline-live.tfplan`  
**Plan SHA-256:** `8C31A1EEE745A51DA412A11BF8BC05B0B1BD910402D7BE3E5EA7B005B2461805`

## 1. Executive result

# SAFE TO APPLY

The saved plan contains no replacement or destruction of the VPC, subnets, route tables, API Gateway APIs, ECS cluster, Aurora cluster/writer, persistent DynamoDB tables, Cognito user pool, SPA bucket, CloudFront distribution, or ECR repositories. Its four delete actions are replacement halves for the four application-level categories explicitly approved for this reconciliation.

The plan was not applied. No imports, Terraform state operations, backend migration, destroy, or mutating AWS CLI commands were performed.

## 2. Current AWS reality

| Area | Read-only AWS finding |
|---|---|
| ALB | `smartretailx-alb` is absent. The four application target groups exist and are currently detached from a load balancer. |
| NAT | The tagged NAT Gateway and its live EIP are absent. |
| ECS | `smartretailx-cluster` is active. Order, inventory, product, and user services exist and were desired/running `1` at inspection. Grafana service is absent. Existing task definitions include order/inventory revision 11, product/user revision 10, and Grafana revision 4. |
| HTTP API | API `e5yvcy9p5m` and its `$default` stage exist. Live ALB integration and application routes are absent. |
| WebSocket API | API `ik50k8qsle` exists. Its integrations, routes, and stage are absent. |
| EventBridge Pipes | No `smartretailx` Pipe currently exists. |
| Aurora | `smartretailx-inventory` exists and is available on PostgreSQL 16.14 with its writer instance. |
| DynamoDB | Orders, products, idempotency, and websocket-connections tables exist. Products already has its `ap-south-1` replica. The order-outbox table is absent. |
| Cognito | User pool `eu-west-1_QutfhUEHK`, SPA client, Grafana client, customer/admin groups, and hosted domain exist. |
| CloudFront/S3 | Distribution `E1LFQ5YHORDZ6P` and the SPA bucket exist. CloudFront currently has both legacy `/api/*` and canonical `/v1/*` behavior; the plan removes only the legacy behavior in place. |
| Lambda | Existing notification, reconciliation, WebSocket, and Cognito functions exist. No Lambda aliases currently exist. The order-outbox publisher function is absent. |
| WAF | The CloudFront web ACL exists; WAF logging is absent. |
| SQS/SNS/EventBridge | Core orders queues, orders DLQ, order-events queue, SNS topics, subscriptions, and the event bus exist. Outbox publisher DLQ and new event rules are absent. |
| Grafana | Task definition, task IAM, secret, and log group exist. Grafana ECS service and target group are absent. |

These findings came from AWS read-only APIs and were checked against `terraform state list`; absence was not inferred from Terraform alone.

## 3. AWS / Terraform state reconciliation

| Resource/group | AWS | State | Config at baseline/live | Status | Recommended action |
|---|---:|---:|---|---|---|
| VPC and six subnets | Exists | Exists | Preserve | A — aligned | No action |
| Route tables and gateway endpoints | Exists | Exists | Preserve/update in place only | A — aligned | No action |
| Internal ALB/listener | Absent | Absent | Create when live | B — legitimate live restore | Let saved plan create |
| Four application target groups | Exists | Exists | Reuse | A — aligned | No action |
| NAT Gateway/EIP/private egress route | Absent | Absent | Create when live | B — legitimate live restore | Let saved plan create |
| HTTP API and `$default` stage | Exists | Exists | Reuse | A — aligned | No action |
| HTTP integrations/routes | Absent | Absent | Create when live | B — legitimate live restore | Let saved plan create |
| WebSocket API | Exists | Exists | Reuse | A — aligned | No action |
| WebSocket routes/integrations/stage | Absent | Absent | Create when live | B — legitimate live restore | Let saved plan create |
| Order-status EventBridge Pipe | Absent | Absent | Create when live | B — new managed feature | Let saved plan create |
| ECS cluster and four app services | Exists | Exists | Reuse/update in place | A — aligned | No action |
| Grafana task/IAM/secret/config | Exists | Exists | Preserve | A — aligned | No action |
| Grafana service/target group/rule | Absent | Absent | Disabled by default | B — intentionally optional | Keep absent unless explicitly enabled |
| Aurora cluster/writer | Exists | Exists | Preserve; harden in place | A — aligned | No action |
| Four existing DynamoDB tables | Exists | Exists | Preserve; selected in-place hardening | A — aligned | No action |
| Order-outbox DynamoDB table | Absent | Absent | Create | B — new managed feature | Let saved plan create |
| Cognito pool/clients/groups/domain | Exists | Exists | Preserve | A — aligned | No action |
| SPA S3 bucket/CloudFront distribution | Exists | Exists | Preserve/update in place | A — aligned | No action |
| Existing ECR repositories | Exists | Exists | Preserve | A — aligned | No action |
| Existing Lambda functions | Exists | Exists | Publish revisions and add aliases | A — aligned | Let saved plan update/create |
| Order-outbox publisher Lambda | Absent | Absent | Create | B — new managed feature | Let saved plan create |
| WAF ACL | Exists | Exists | Update in place | A — aligned | No action |
| WAF logging/log group | Absent | Absent | Create | B — new managed feature | Let saved plan create |
| CloudWatch dashboard/new alarms | Mostly absent | Absent | Create | B — new managed observability | Let saved plan create |
| GitHub release/plan OIDC roles | Absent | Absent | Create | B — new managed CI/CD feature | Let saved plan create |

There were no category C resources (AWS exists/state missing) and no category D resources (state exists/AWS missing). No import or state correction is required.

## 4. Terraform fixes made

| File | Problem | Fix and reason |
|---|---|---|
| `infra/variables.tf` | Baseline live desired count defaulted to `0`; Grafana had no independent feature flag. | Set `service_desired_count` default to `1`; added `enable_grafana=false`. The existing live condition still yields a zero parked floor. |
| `infra/grafana.tf` | `live=true` always created Grafana runtime resources and changed the preserved task definition URL, causing an unnecessary replacement. | Added `local.grafana_runtime_enabled = var.live && var.enable_grafana`; used it as `count` only for Grafana ECS service, target group, and listener rule. Preserved task/IAM/secret/config/source resources and retained localhost configuration while disabled. |
| `scripts/check_baseline_plan.py` | No executable policy prevented an unexpected delete from reaching the final plan. | Added a plan-JSON deletion allowlist. It rejects all unapproved deletes and rejects pure destruction even for an approved address. |
| `tests/architecture/test_baseline_runtime_contract.py` | Parking/live/Grafana behavior was not protected by evaluated plan tests. | Added refresh-free Terraform plan contracts for persistent-resource survival, parked floor `0`, live floor `1`, and optional Grafana runtime. |
| `tests/architecture/test_baseline_plan_policy.py` | Critical resource replacement categories lacked negative tests. | Added contracts for VPC, subnet, Aurora cluster/writer, DynamoDB, Cognito, S3, CloudFront, ECR, ECS cluster, the four approved replacements, unapproved replacements, and pure destruction. |
| `docs/superpowers/specs/2026-08-11-baseline-live-reconciliation-design.md` | The approved safety boundary needed a durable design record. | Recorded the approved minimal reconciliation and classification rule. |
| `docs/superpowers/plans/2026-08-11-baseline-live-reconciliation.md` | The implementation needed a test-first execution record. | Recorded exact RED/GREEN, validation, saved-plan, and audit steps. |
| `infra/baseline-live.tfplan` | Final executable plan was required. | Generated from the configured baseline state with `environment_name=baseline`, `live=true`; not applied. |
| `infra/baseline-live-plan.txt` | Human-readable final plan was required. | Rendered directly from the saved binary plan with `terraform show -no-color`. |

The baseline-to-development compatibility mapping was not changed. The saved plan evaluates all seven Lambda aliases to `development`, and the GitHub deploy trust subject remains `repo:Logithloki/smartretailx:environment:development`.

## 5. Final Terraform plan

```text
Plan: 74 to add, 31 to change, 4 to destroy.
```

The four destroys are all replacement halves; there are no pure destroys. The saved-plan policy result was:

```text
PASS: no unapproved delete actions; 4 approved replacement(s).
```

The plan creates previously absent live/runtime and production-readiness resources, updates existing resources in place, and registers immutable application revisions. It does not duplicate AWS resources that exist outside state.

## 6. Every replacement

| Resource | Replacement trigger | Data affected | Possible interruption | Assessment |
|---|---|---|---|---|
| `aws_ecs_task_definition.services["order"]` | `container_definitions` changes to the transactional outbox environment/configuration. ECS task definitions are immutable. | No DynamoDB data is deleted. A new task-definition revision is registered. | The ECS service performs a rolling deployment with deployment circuit breaker/rollback; healthy capacity is retained subject to normal deployment health. | Safe and explicitly approved. |
| `aws_lambda_permission.notification_sns` | `qualifier` moves SNS invocation permission from the unqualified function to the `development` alias. | No application data. | A short permission replacement window can delay SNS-to-Lambda invocation; SNS asynchronous retries mitigate transient failure. | Safe and explicitly approved. |
| `aws_lambda_permission.ws_authorizer_invoke` | `qualifier` moves API Gateway invocation permission to the `development` alias. | No application data. | New WebSocket connections may briefly fail authorization during replacement; existing connections are not deleted by this permission change. | Safe and explicitly approved. |
| `aws_sns_topic_subscription.notification` | `endpoint` moves from the unqualified notification function ARN to the `development` alias ARN. | No order/inventory data. | Brief notification delivery gap is possible while the subscription is replaced; this affects email notification delivery, not order persistence. | Safe and explicitly approved. |

Grafana task definition is now `no-op` and is not a fifth replacement.

## 7. Critical resource safety

| Protected resource | Saved-plan action | Destroyed/replaced? |
|---|---|---:|
| VPC | `no-op` | No |
| Six subnets | all `no-op` | No |
| Route tables | no replacement/destruction | No |
| Aurora cluster | `update` in place: PostgreSQL log export, snapshot tag copy, backup window | No |
| Aurora writer | `no-op` | No |
| DynamoDB orders | `no-op` | No |
| DynamoDB products | `update` in place | No |
| DynamoDB idempotency | `update` in place | No |
| DynamoDB websocket-connections | `update` in place | No |
| DynamoDB order-outbox | `create` (new table) | No existing data |
| Cognito user pool | `no-op` | No |
| S3 SPA bucket | `no-op` | No |
| CloudFront distribution | `update` in place | No |
| Four ECR repositories | all `no-op` | No |
| ECS cluster | `no-op` | No |
| HTTP and WebSocket API resources | API objects `no-op`; routes/integrations added | No |

The `live=false` evaluated contract showed the same persistent/data addresses with no delete actions and all four application autoscaling minimums at `0`. The `live=true` evaluated plan showed all four minimums at `1`. This preserves the contract that a service already parked at zero can remain there, while the live baseline is restored to one task per service.

## 8. New features being added

- Transactional order-outbox table, stream publisher Lambda, event-source mapping, DLQ, IAM, and alarms.
- Published Lambda versions and `development` aliases for baseline compatibility.
- Internal ALB, live NAT/private egress, API Gateway VPC Link integration, and canonical `/v1` routes.
- WebSocket routes, integrations, stage, JWT-checking authorizer alias, connection handling, and push path.
- DynamoDB Streams to EventBridge Pipe for order status events.
- CloudWatch operations dashboard plus API, ECS, Lambda, queue/DLQ, Aurora, and deployment alarms.
- WAF logging with sensitive headers redacted and an in-place per-IP rate-limit rule.
- DynamoDB PITR/index/stream hardening, including the WebSocket user index and product Global Table support.
- SPA runtime configuration support and CloudFront behavior cleanup from legacy `/api/*` to `/v1/*`.
- GitHub OIDC plan/release IAM roles and least-privilege deployment policy updates.
- Default security-group hardening and S3 lifecycle management.

## 9. Cost impact

- NAT Gateway and its data processing are billable only while `live=true`; this is the largest documented idle network cost in the project model.
- The internal ALB is billable while `live=true`.
- Four ARM64 application Fargate services have a baseline floor of one task each while live. Their floor returns to zero when parked.
- Aurora remains persistent, encrypted, and recoverable. Serverless v2 minimum capacity is zero so it can auto-pause when idle; live inventory traffic wakes it.
- WAF remains present and billable independently of the live toggle by settled design; CloudWatch logs/alarms add usage-based charges.
- Lambda, SQS, SNS, EventBridge, and Pipes are primarily usage-based at demo scale.
- Grafana Fargate remains disabled by default, avoiding its documented approximately USD 3/month demo-task cost. Its task definition, IAM, secret, configuration, and code remain ready for an explicit `enable_grafana=true` session.

The operator must park the stack after any live validation session.

## 10. Test results

| Validation | Result |
|---|---|
| `terraform fmt -recursive -check` | Pass |
| `terraform validate` | Pass — configuration valid |
| Checkov | Pass — 497 passed, 0 failed, 0 skipped |
| Architecture contracts | Pass — 28 passed, including 17 new baseline safety/policy cases |
| Python service/Lambda suites | Pass — 237 tests across common, inventory, notification, outbox publisher, order, product, reconciliation, user, and WebSocket packages |
| Frontend ESLint | Pass — zero warnings allowed |
| Frontend Vitest | Pass — 3 files, 8 tests |
| Frontend production build | Pass — TypeScript and Vite build completed |
| Docker Compose configuration | Pass; Docker emitted only an environment warning that the user-level Docker config file was unreadable in the sandbox |
| Saved-plan deletion policy | Pass — exactly four approved replacements, zero unapproved deletes |

Initial sandbox-only failures to access the Windows pytest temp root and start Vitest fork workers were rerun with appropriate local permissions and passed. Checkov's optional online guideline lookup was unavailable, but its local Terraform scan completed successfully. TFLint is not installed locally; the repository's blocking CI job pins and installs TFLint `v0.53.0` before running `tflint --recursive`.

## 11. Blockers

There is no Terraform state import, backend, credential, or destructive-plan blocker. No manual action is required before the saved Terraform plan itself can be applied.

Operational follow-ups that are not apply blockers:

- The GitHub `development` environment must retain its expected reviewers/variables before release workflows are used; the compatibility mapping was deliberately preserved.
- SES sandbox identities/recipients must remain verified before end-to-end email evidence is collected.
- TFLint is enforced in CI rather than by this local workstation because the local executable is absent.
- The saved binary plan can contain sensitive Terraform values and should not be committed or shared. Apply only this reviewed SHA-256 artifact; regenerate and re-audit if configuration or state changes.

## 12. Next exact command

From `D:\APIIT\ECADWP_2\Implementation\smartretailx\infra`, the one operator action is:

```powershell
terraform apply "baseline-live.tfplan"
```

This command was not run during the audit.
