# Baseline Live Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a validated, saved `baseline`/`live=true` Terraform plan that retains persistent infrastructure, keeps Grafana disabled by default, and restores one application ECS task per service without applying it.

**Architecture:** Terraform evaluates the application runtime from `live` and a default desired count of one, while a separate Grafana feature flag gates only Grafana's billable runtime attachments. Python safety contracts exercise real Terraform plan JSON and a saved-plan analyzer enforces a deletion allowlist before the final audit is classified.

**Tech Stack:** Terraform 1.x, AWS provider, Python 3.12, pytest, PowerShell, AWS `eu-west-1` baseline state.

## Global Constraints

- Do not run `terraform apply`, `terraform destroy`, Terraform import/state mutation, backend migration, or a mutating AWS CLI command.
- Use the configured S3 backend and current `default` Terraform workspace without reconfiguration.
- Preserve the `baseline` to `development` Lambda alias and GitHub environment compatibility mapping.
- `enable_grafana` defaults to `false` and gates only the Grafana ECS service, target group, and listener rule.
- Preserve the Grafana task definition, IAM, secret, configuration, and source code.
- `live=false` parks application ECS runtime at zero and preserves persistent/data resources.
- `live=true` restores the default baseline ECS desired count to exactly one.
- Accept deletion only as part of replacement for the order ECS task definition, notification Lambda permission, WebSocket authorizer Lambda permission, and SNS notification subscription.
- Stop after the saved-plan audit; do not apply.

---

### Task 1: Add evaluated Terraform runtime safety contracts

**Files:**
- Create: `tests/architecture/test_baseline_runtime_contract.py`

**Interfaces:**
- Consumes: `terraform plan -refresh=false -target=... -out=<path>` and `terraform show -json <path>`.
- Produces: pytest assertions over evaluated `resource_changes[*].change.actions` and `after` values for parked/live application autoscaling targets and optional Grafana runtime resources.

- [ ] **Step 1: Write failing tests**

Create helpers that run targeted, refresh-free Terraform plans in temporary files for `live=false` and `live=true`, then assert:

```python
assert parked_target["change"]["after"]["min_capacity"] == 0
assert live_target["change"]["after"]["min_capacity"] == 1
assert grafana_addresses == set()
```

Also assert every persistent resource address is present in the parked plan and has no `delete` action.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/architecture/test_baseline_runtime_contract.py -q`

Expected: failure because the live autoscaling target evaluates to zero and Grafana runtime resources still appear when `live=true`.

- [ ] **Step 3: Leave the failing tests in place for Task 2**

Do not weaken assertions or inspect source strings. The production changes that should make them pass are the new feature flag and desired-count default.

### Task 2: Implement minimal Grafana and desired-count reconciliation

**Files:**
- Modify: `infra/variables.tf`
- Modify: `infra/grafana.tf`

**Interfaces:**
- Consumes: existing `var.live`, `aws_lb.main`, and application autoscaling configuration.
- Produces: `var.enable_grafana : bool`, `local.grafana_runtime_enabled : bool`, and a default `var.service_desired_count` of `1`.

- [ ] **Step 1: Add the two variable defaults**

Add:

```hcl
variable "enable_grafana" {
  description = "Run the optional Grafana ECS service and ALB attachments when the stack is live."
  type        = bool
  default     = false
}
```

Change only the `service_desired_count` default to `1` and update its description to document the `live=false` zero-task guard.

- [ ] **Step 2: Gate only Grafana runtime resources**

Add to `infra/grafana.tf`:

```hcl
locals {
  grafana_runtime_enabled = var.live && var.enable_grafana
}
```

Use `local.grafana_runtime_enabled ? 1 : 0` only for `aws_lb_target_group.grafana`, `aws_lb_listener_rule.grafana`, and `aws_ecs_service.grafana`. Use the same local only as the condition selecting ALB URLs versus existing localhost values in the preserved Cognito client, task definition, and output.

- [ ] **Step 3: Format and run the focused tests for GREEN**

Run: `terraform fmt infra/variables.tf infra/grafana.tf`

Run: `.venv\Scripts\python.exe -m pytest tests/architecture/test_baseline_runtime_contract.py -q`

Expected: all runtime contracts pass, including parked zero, live one, and no default Grafana runtime resources.

### Task 3: Add the saved-plan deletion policy

**Files:**
- Create: `scripts/check_baseline_plan.py`
- Create: `tests/architecture/test_baseline_plan_policy.py`

**Interfaces:**
- Produces: `evaluate_plan(plan: dict[str, object]) -> list[str]` and CLI exit code `0` when safe, `1` with diagnostics when unsafe.
- Consumes: Terraform plan JSON from a filename or standard input (`-`).

- [ ] **Step 1: Write failing policy tests**

Use literal synthetic Terraform plan JSON to prove a delete action is rejected for each protected address family:

```python
PROTECTED = [
    "aws_vpc.main",
    'aws_subnet.private[0]',
    "aws_rds_cluster.inventory",
    'aws_rds_cluster_instance.writer[0]',
    "aws_dynamodb_table.orders",
    "aws_cognito_user_pool.main",
    "aws_s3_bucket.spa",
    "aws_cloudfront_distribution.main",
    'aws_ecr_repository.services["order"]',
    "aws_ecs_cluster.main",
]
```

Add tests proving the four exact approved replacements pass and a fifth unapproved replacement fails.

- [ ] **Step 2: Run the policy tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/architecture/test_baseline_plan_policy.py -q`

Expected: failure because `scripts/check_baseline_plan.py` does not yet implement the policy.

- [ ] **Step 3: Implement the minimal analyzer**

For each `resource_changes` entry containing `delete`, reject it unless its exact address is one of:

```python
ALLOWED_REPLACEMENTS = {
    'aws_ecs_task_definition.services["order"]',
    "aws_lambda_permission.notification_sns",
    "aws_lambda_permission.ws_authorizer_invoke",
    "aws_sns_topic_subscription.notification",
}
```

Emit one diagnostic per violation and return a nonzero CLI status.

- [ ] **Step 4: Run policy tests for GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/architecture/test_baseline_plan_policy.py -q`

Expected: all policy tests pass.

### Task 4: Validate the repository

**Files:**
- Modify only files changed by automatic Terraform formatting.

**Interfaces:**
- Consumes: completed Terraform and Python safety contracts.
- Produces: fresh validation evidence for the audit.

- [ ] **Step 1: Run Terraform validation**

Run: `terraform fmt -recursive -check`

Run: `terraform validate`

- [ ] **Step 2: Run Terraform security and architecture checks**

Run: `.venv\Scripts\checkov.exe -d infra --config-file .checkov.yml`

Run: `.venv\Scripts\python.exe -m pytest tests/architecture -q`

- [ ] **Step 3: Run application and frontend validation**

Run all service pytest suites using `.venv\Scripts\python.exe -m pytest`, then run `npm run lint`, `npm test -- --run`, and `npm run build` in `frontend`.

- [ ] **Step 4: Validate local orchestration**

Run: `docker compose config --quiet`

Record every command, result, count, and any non-blocking warning in the final audit.

### Task 5: Generate and enforce the final saved plan

**Files:**
- Create: `infra/baseline-live.tfplan`
- Create: `infra/baseline-live-plan.txt`

**Interfaces:**
- Consumes: configured baseline backend, `environment_name=baseline`, `live=true`, default `enable_grafana=false`, and default service desired count `1`.
- Produces: the exact binary plan and its human-readable rendering.

- [ ] **Step 1: Create the binary plan**

From `infra`, run:

```powershell
terraform plan -var='environment_name=baseline' -var='live=true' -out='baseline-live.tfplan' -input=false -no-color
```

- [ ] **Step 2: Render the plan text**

Run:

```powershell
terraform show -no-color baseline-live.tfplan | Set-Content -Encoding utf8 baseline-live-plan.txt
```

- [ ] **Step 3: Enforce the deletion policy on the saved artifact**

Run:

```powershell
terraform show -json baseline-live.tfplan | ..\.venv\Scripts\python.exe ..\scripts\check_baseline_plan.py -
```

Expected: exit `0`, exactly four approved delete/replacement addresses, and no protected-resource deletion.

### Task 6: Complete the final audit and stop

**Files:**
- Create: `docs/final-baseline-live-audit.md`

**Interfaces:**
- Consumes: saved plan, policy result, AWS/state reconciliation, and validation evidence.
- Produces: one strict classification and one next action.

- [ ] **Step 1: Document the audit evidence**

Include scope/constraints, current AWS reality, plan counts, every replacement, protected-resource safety results, parked/live contracts, Grafana optionality, validation results, cost impact, and remaining operational notes.

- [ ] **Step 2: Apply the classification rule**

Use exactly one heading value: `SAFE TO APPLY`, `SAFE AFTER MANUAL ACTION`, or `NOT SAFE TO APPLY`. Classify as safe only if all protected resources avoid deletion/replacement, every deletion is approved, and all blocking checks pass.

- [ ] **Step 3: Provide exactly one next action and stop**

If safe, the audit may identify `terraform apply "baseline-live.tfplan"` as the future operator action, but do not execute it. Print the audit summary to the terminal and end the task before apply.
