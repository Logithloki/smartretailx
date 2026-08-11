# SmartRetailX Partial-Apply Recovery Audit

> Sections 1-13 preserve the pre-apply recovery record. Section 14 records
> the successful recovery deployment and the final post-deployment Terraform
> convergence work.

**Audit date:** 2026-08-11  
**Repository:** `D:\APIIT\ECADWP_2\Implementation\smartretailx`  
**Branch:** `codex/production-readiness`  
**AWS account/region:** `322551984077` / `eu-west-1`  
**Terraform context:** Existing baseline backend, workspace `default`, `environment_name=baseline`, `live=true`, `enable_grafana=false`  
**Recovery plan:** `infra/baseline-live-recovery.tfplan`  
**Recovery plan SHA-256:** `64224A1708D6EC38924F58C9E7161BCF87FB7C1182B5D671FF1A38F6FCF942FC`

## 1. Root cause

The partial apply failed only when AWS validated `aws_cloudwatch_dashboard.operations`. Two widget definitions used Terraform's recursive `flatten()` function around lists of metric rows:

- `DynamoDB requests and throttling`
- `Lambda errors and throttles`

`flatten()` erased every inner metric-row boundary. `jsonencode()` consequently emitted one long list containing strings and renderer objects instead of a list of metric arrays. CloudWatch rejected that structure with 176 schema errors such as `properties/metrics/0 Should be array`.

A fresh, targeted, refresh-free Terraform plan reproduced the exact defect locally before any fix. It showed widget 1 beginning with a bare `"AWS/DynamoDB"` item and widget 7 beginning with a bare `"AWS/Lambda"` item. The other seven metric widgets already rendered correctly as nested arrays.

This was a deterministic Terraform data-shape defect, not AWS drift, IAM denial, partial state corruption, or an eventual-consistency failure.

## 2. Resources confirmed successfully applied

All items below were verified through both current Terraform state and read-only AWS APIs rather than inferred from the failed terminal log.

| Area | Verified post-apply state |
|---|---|
| NAT/EIP/egress | NAT `nat-0a538f516aaa20f17` is `available`; EIP allocation `eipalloc-07d0d3bc9006efb0a` is attached; the private route table has an active `0.0.0.0/0` route through that NAT. |
| Internal ALB | `smartretailx-alb` is `active`, scheme `internal`, with HTTP listener port 80. |
| ALB listener rules | Priorities 10/20/30/40 route `/v1/orders*`, `/v1/inventory*`, `/v1/users*`, and `/v1/products*`; default action is a fixed response. |
| HTTP API | One VPC Link `HTTP_PROXY` integration exists; all eight canonical base/proxy `/v1` routes exist with JWT authorization; `$default` stage auto-deploys. |
| WebSocket API | Connect/default/disconnect integrations and routes exist; `$connect` uses the custom authorizer; `prod` stage exists with auto-deploy. |
| Order outbox table | `smartretailx-order-outbox` is `ACTIVE` with `NEW_IMAGE` stream enabled. |
| WebSocket table | `smartretailx-websocket-connections` has an `ACTIVE` `userId-index`. |
| Outbox Lambda | `smartretailx-order-outbox-publisher` is active; `development` alias points to version 1. |
| Outbox event-source mapping | UUID `0edcd605-6610-4e50-b44e-030e1f427df8` is `Enabled`, targets the `development` alias, reads the outbox stream, and sends failures to the outbox DLQ. |
| Outbox DLQ | Queue exists with zero visible messages at inspection. |
| Lambda aliases | Notification, reconciliation, outbox publisher, WebSocket authorizer/connect/disconnect/push all have `development` aliases pointing to version 1. |
| EventBridge | `smartretailx-order-status-changed` is enabled and targets the WebSocket push `development` alias. |
| EventBridge Pipe | `smartretailx-order-status` is `RUNNING` from the orders DynamoDB stream to the SmartRetailX event bus. |
| WAF logging | Logging writes to `aws-waf-logs-smartretailx-cloudfront`; authorization and cookie headers are redacted. |
| CloudWatch alarms | API, Aurora, four ALB target-health, six Lambda-error, orders queue/age/DLQ, and outbox-DLQ alarms exist; all were `OK` at inspection. |
| ECS | Four services are active at desired/running `1/1`, pending `0`; all primary deployments are `COMPLETED`. Order runs task revision 12; inventory 11; product/user 10. |
| CloudFront behavior | Distribution `E1LFQ5YHORDZ6P` is `Deployed` and now exposes only `/v1/*`; removal of legacy `/api/*` succeeded. |
| Cognito SPA client | Authorization-code flow, `openid email profile`, localhost and CloudFront callback/logout URLs are present. |
| GitHub OIDC roles | Deploy, release, and Terraform-plan roles and policies are present in state/AWS. |

Terraform state contains these resources and does not contain `aws_cloudwatch_dashboard.operations`. `aws cloudwatch list-dashboards --dashboard-name-prefix smartretailx` also returned an empty list. There is no dashboard state/AWS mismatch and no import is needed.

## 3. Resources still pending

The new recovery plan contains exactly three remaining actions:

| Resource | Action | Reason |
|---|---|---|
| `aws_cloudwatch_dashboard.operations` | Create | The original apply failed before AWS created it; corrected JSON is now planned. |
| `aws_cloudfront_distribution.main` | Update in place | Raise `minimum_protocol_version` from `TLSv1` to `TLSv1.2_2021`; the prior behavior cleanup already succeeded. |
| `aws_iam_openid_connect_provider.github` | Update in place | Normalize the legacy configured thumbprint to the declared empty optional/computed list; provider ARN, audiences, URL, roles, and trust policies are not replaced. |

The OIDC update is not a replacement. The installed provider schema marks `thumbprint_list` optional and computed. Current [HashiCorp AWS provider documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_openid_connect_provider) states that GitHub is one of the providers AWS validates with its trusted root CA library rather than configured thumbprints. [AWS IAM documentation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc_verify-thumbprint.html) likewise states that AWS normally uses trusted root CAs and falls back to configured thumbprints only in specific TLS/certificate cases.

## 4. Dashboard code defect

The invalid pattern was:

```hcl
metrics = flatten([
  for value in values : [
    ["Namespace", "MetricName", "Dimension", value],
    [".", "OtherMetric", ".", value],
  ]
])
```

Terraform recursively flattened both the outer per-resource list and each inner metric row. The rendered JSON therefore violated CloudWatch's requirement that every `metrics` element be an array.

## 5. Exact dashboard fix

Only `infra/observability.tf` changed. Both `flatten()` expressions were replaced by explicit nested metric arrays:

- Eight DynamoDB rows: read, write, throttled, and system errors for orders and products.
- Twelve Lambda rows: errors and throttles for notification, reconciliation, order-outbox publisher, WebSocket connect, disconnect, and push.

Every row is now independently encoded, and any `{ stat = "Sum" }` renderer remains the final row item. The other API request/latency, ECS CPU/memory, SQS/DLQ, and Aurora widgets were inspected and left unchanged because they already generated the correct shape.

## 6. New regression test

`tests/architecture/test_cloudwatch_dashboard_contract.py` runs a real refresh-free targeted Terraform plan, reads `aws_cloudwatch_dashboard.operations.change.after.dashboard_body`, decodes the JSON, and asserts:

1. All nine expected metric widgets exist.
2. Every `properties.metrics` value is a list.
3. Every metrics element is itself a list.
4. A renderer object can occur only as the final metric-row item; all preceding items are strings.

RED evidence before the fix named exactly the DynamoDB and Lambda widgets. GREEN evidence after the fix was `3 passed`.

## 7. Validation results

| Validation | Result |
|---|---|
| `terraform fmt -recursive -check` | Pass |
| `terraform validate` | Pass — configuration valid |
| Dashboard contract | Pass — 3/3 |
| Full architecture suite | Pass — 31/31 |
| Checkov | Pass — 497 passed, 0 failed, 0 skipped |
| Read-only AWS/state reconciliation | Pass — successful resources verified; dashboard absent from both AWS and state |
| Saved-plan deletion policy | Pass — 0 unapproved deletes, 0 replacements |

No `PutDashboard` call was made manually because that API is mutating. Local validation instead exercised the exact JSON Terraform will submit.

## 8. New Terraform plan summary

```text
Plan: 1 to add, 2 to change, 0 to destroy.
```

The plan was generated with an AWS/state refresh after the partial apply using explicit `baseline`, `live=true`, and `enable_grafana=false` values. The text rendering is `infra/baseline-live-recovery-plan.txt`.

## 9. Every replacement or destruction

There are no replacement (`-/+`) actions and no destroy actions. The saved-plan policy reports:

```text
PASS: no unapproved delete actions; 0 approved replacement(s).
```

The old `infra/baseline-live.tfplan` is stale and must never be reused. The temporary targeted pre-fix diagnostic plan was removed after root-cause evidence was captured.

## 10. Protected infrastructure safety

The recovery plan was inspected in JSON and contains zero delete actions for all protected address families.

| Protected infrastructure | Recovery-plan action |
|---|---|
| VPC | `no-op` |
| Six subnets | all `no-op` |
| Aurora cluster and writer | `no-op` |
| Persistent DynamoDB tables | `no-op` |
| Cognito user pool | `no-op` |
| S3 SPA bucket | `no-op` |
| CloudFront distribution | update in place; no replacement |
| Four ECR repositories | all `no-op` |
| ECS cluster | `no-op` |
| Grafana runtime | remains disabled; no Grafana service/target/rule creation |

No import, state operation, backend change, rollback, or AWS deletion is required.

## 11. Recovery classification

# SAFE TO COMPLETE APPLY

The new recovery plan converges the current post-partial-apply state with one valid dashboard creation and two bounded in-place updates. It has no replacement or destruction and leaves every protected data/infrastructure resource intact.

## 12. Recovery plan SHA-256

```text
64224A1708D6EC38924F58C9E7161BCF87FB7C1182B5D671FF1A38F6FCF942FC
```

The binary plan can contain sensitive Terraform values. Do not commit or share it. If configuration or remote state changes, discard it and generate/re-audit a new plan.

## 13. Next exact operator command

From `D:\APIIT\ECADWP_2\Implementation\smartretailx\infra`:

```powershell
terraform apply "baseline-live-recovery.tfplan"
```

This command was not run during recovery preparation.

## 14. Post-deployment convergence

**Convergence date:** 2026-08-11  
**Recovery apply result reported by operator:** `1 added, 2 changed, 0 destroyed`  
**Terraform context:** Existing baseline backend and workspace, `environment_name=baseline`, `live=true`, `enable_grafana=false`

The recovery apply successfully created `aws_cloudwatch_dashboard.operations`,
but its immediate follow-up plan contained two recurring in-place differences:

```text
Plan: 0 to add, 2 to change, 0 to destroy.
```

### CloudFront default-certificate protocol representation

`infra/frontend.tf` used `cloudfront_default_certificate = true` together with
`minimum_protocol_version = "TLSv1.2_2021"`. The default certificate serves the
CloudFront distribution domain rather than a custom domain. For that certificate
mode, the CloudFront API and HashiCorp AWS provider represent the minimum protocol
as `TLSv1`; selectable policies such as `TLSv1.2_2021` require a custom ACM or IAM
certificate. AWS therefore continued returning `TLSv1`, producing the perpetual
plan difference.

The configuration now explicitly declares:

```hcl
viewer_certificate {
  # The default certificate is represented by TLSv1 in the CloudFront
  # API/provider; selectable stronger policies require a custom certificate.
  cloudfront_default_certificate = true
  minimum_protocol_version       = "TLSv1"
}
```

No ACM certificate, custom domain, distribution replacement, or unrelated
CloudFront change was introduced.

### GitHub OIDC retained thumbprint

`infra/oidc.tf` declared `thumbprint_list = []`, while the existing IAM OIDC
provider retained the legacy value
`ab9d0263244dd0326eb67015705a667e79cfe998`. AWS uses its trusted root CA library
for GitHub, so that retained value is not used for GitHub certificate validation.
However, removing a thumbprint argument after originally creating the provider
does not make IAM retrieve or clear it; AWS continues returning the initial list,
which produced the perpetual Terraform removal diff.

Terraform now declares the already-retained value:

```hcl
thumbprint_list = ["ab9d0263244dd0326eb67015705a667e79cfe998"]
```

This is deterministic state/configuration convergence rather than drift
suppression. No `ignore_changes` was added, and the OIDC provider ARN, URL,
audience, IAM roles, and trust policies were not changed or replaced.

### Architecture contracts

`tests/architecture/test_terraform_convergence_contract.py` evaluates a real,
refresh-free targeted Terraform plan and verifies:

- the default CloudFront certificate resolves to the supported `TLSv1` value;
- the GitHub OIDC provider preserves the retained legacy thumbprint;
- both managed resources have `no-op` actions.

The RED run before the configuration changes reported four expected failures:
the two wrong configured values and the two planned update actions. The GREEN run
after the changes passed all 18 convergence and protected-resource cases.

`tests/architecture/test_baseline_plan_policy.py` also now includes
`aws_iam_openid_connect_provider.github` in the protected-address replacement
matrix. CloudFront was already protected. The deletion policy continues to reject
any destroy/replacement of either resource.

### Validation and final plan

| Validation | Final result |
|---|---|
| `terraform fmt -recursive -check` | Pass |
| `terraform validate` | Pass — configuration valid |
| Convergence plus protected-resource tests | Pass — 18/18 |
| Complete architecture suite | Pass — 36/36 |
| Checkov 3.3.9 | Pass — 497 passed, 0 failed, 0 skipped |
| Refreshed baseline-live Terraform plan | **No changes. Your infrastructure matches the configuration.** |

The final plan used the existing backend/workspace and the required explicit
values:

```powershell
terraform plan `
  -var="environment_name=baseline" `
  -var="live=true" `
  -var="enable_grafana=false"
```

It contained no create, update, replace, or destroy actions. Consequently no
protected resource replacement/destruction exists and there is no follow-up
apply to run. No AWS mutation, Terraform apply, state manipulation, import,
backend migration, destroy, or replacement was performed during this
post-deployment convergence task.
