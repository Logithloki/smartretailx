# Partial Apply Dashboard Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the CloudWatch dashboard metric-row schema, validate the generated JSON, and produce a new non-destructive recovery plan against the current post-partial-apply state.

**Architecture:** The existing partially applied AWS resources and Terraform state remain untouched. A pytest contract obtains the real dashboard body from a refresh-free targeted Terraform plan and validates every metric widget structurally; the Terraform fix replaces only the two recursive `flatten()` expressions with explicit nested metric rows. A full refreshed recovery plan then determines the remaining convergence work.

**Tech Stack:** Terraform, AWS CloudWatch dashboards, Python 3.12, pytest, Checkov, AWS CLI, PowerShell.

## Global Constraints

- Do not run Terraform apply/destroy/import/state mutation or any mutating AWS CLI command.
- Do not reuse `infra/baseline-live.tfplan` or roll back successfully applied resources.
- Remain on the configured baseline backend and `default` workspace.
- Plan with `environment_name=baseline`, `live=true`, and `enable_grafana=false`.
- Preserve persistent resources and all user-owned dirty-worktree changes.
- Stop after producing and auditing `infra/baseline-live-recovery.tfplan`.

---

### Task 1: Add the generated-dashboard schema contract

**Files:**
- Create: `tests/architecture/test_cloudwatch_dashboard_contract.py`

**Interfaces:**
- Consumes: refresh-free targeted `terraform plan` JSON for `aws_cloudwatch_dashboard.operations`.
- Produces: `dashboard_body: dict` fixture and assertions over all metric widgets and metric rows.

- [ ] **Step 1: Write the failing test**

Generate a temporary targeted plan, decode `change.after.dashboard_body`, and assert every `properties.metrics` value is a list whose elements are metric-row lists. For each row, allow a renderer dictionary only in the final position and require every preceding item to be a string.

```python
for widget in metric_widgets:
    metrics = widget["properties"]["metrics"]
    assert isinstance(metrics, list)
    for metric in metrics:
        assert isinstance(metric, list)
        values = metric[:-1] if metric and isinstance(metric[-1], dict) else metric
        assert values and all(isinstance(value, str) for value in values)
```

Assert the nine expected widget titles so a missing widget cannot make the structural loop pass vacuously.

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/architecture/test_cloudwatch_dashboard_contract.py -q -p no:cacheprovider`

Expected: failure for `DynamoDB requests and throttling` because its first element is the string `AWS/DynamoDB`; after reporting all invalid widgets, Lambda must also be listed.

### Task 2: Restore metric-row boundaries

**Files:**
- Modify: `infra/observability.tf`
- Test: `tests/architecture/test_cloudwatch_dashboard_contract.py`

**Interfaces:**
- Consumes: existing DynamoDB table names and `local.operational_lambdas` values.
- Produces: valid CloudWatch `metrics` arrays for all nine widgets.

- [ ] **Step 1: Replace the DynamoDB flatten expression**

Use eight explicit metric rows: read, write, throttled, and system-error metrics for both orders and products. Each row remains its own list and may end in `{ stat = "Sum" }`.

- [ ] **Step 2: Replace the Lambda flatten expression**

Use twelve explicit metric rows: Errors and Throttles for notification, reconciliation, order-outbox publisher, WebSocket connect, disconnect, and push. Each row remains its own list.

- [ ] **Step 3: Format and verify GREEN**

Run: `terraform fmt observability.tf`

Run: `.venv\Scripts\python.exe -m pytest tests/architecture/test_cloudwatch_dashboard_contract.py -q -p no:cacheprovider`

Expected: pass with all nine widget titles and every metric row structurally valid.

### Task 3: Run complete static and local validation

**Files:**
- No new production files.

**Interfaces:**
- Consumes: corrected Terraform and regression contract.
- Produces: fresh validation evidence for the recovery audit.

- [ ] **Step 1: Run Terraform checks**

Run `terraform fmt -recursive -check` and `terraform validate` from `infra`.

- [ ] **Step 2: Run architecture contracts**

Run `.venv\Scripts\python.exe -m pytest tests/architecture -q -p no:cacheprovider`.

- [ ] **Step 3: Run Checkov**

Run the installed Checkov package against `infra` with `.checkov.yml`; require zero failed checks.

- [ ] **Step 4: Confirm AWS dashboard absence without mutation**

Run `aws cloudwatch list-dashboards --dashboard-name-prefix smartretailx --region eu-west-1`; do not call `put-dashboard`.

### Task 4: Generate and enforce the current-state recovery plan

**Files:**
- Create: `infra/baseline-live-recovery.tfplan`
- Create: `infra/baseline-live-recovery-plan.txt`
- Modify: `scripts/check_baseline_plan.py` only if a failing policy test proves the current allowlist is unsafe for recovery.

**Interfaces:**
- Consumes: current remote state after partial apply and corrected dashboard configuration.
- Produces: a refreshed recovery plan, text rendering, SHA-256, and deletion-policy result.

- [ ] **Step 1: Generate a new full plan**

Run from `infra`:

```powershell
terraform plan "-var=environment_name=baseline" "-var=live=true" "-var=enable_grafana=false" "-out=baseline-live-recovery.tfplan" "-input=false" "-no-color"
```

- [ ] **Step 2: Render and analyze the exact saved plan**

Render with `terraform show -no-color`, inspect every delete/replacement, and run `scripts/check_baseline_plan.py` against its JSON. Verify protected VPC, subnets, Aurora, DynamoDB, Cognito, S3, CloudFront, ECR, and ECS-cluster addresses contain no delete action.

- [ ] **Step 3: Hash the binary plan**

Compute SHA-256 with `Get-FileHash baseline-live-recovery.tfplan -Algorithm SHA256`.

### Task 5: Document recovery readiness and stop

**Files:**
- Create: `docs/partial-apply-recovery-audit.md`

**Interfaces:**
- Consumes: AWS/state reconciliation, root-cause evidence, validation results, plan analysis, and SHA-256.
- Produces: exactly one classification and exactly one next operator command.

- [ ] **Step 1: Write all required audit sections**

Document root cause, confirmed applied resources, pending resources, defect/fix/test, validation, exact plan counts, every deletion/replacement, protected-resource safety, classification, SHA-256, and one future command.

- [ ] **Step 2: Classify strictly**

Use exactly one of `SAFE TO COMPLETE APPLY`, `SAFE AFTER MANUAL ACTION`, or `NOT SAFE TO APPLY` based only on the new saved plan.

- [ ] **Step 3: Stop before apply**

Print the audit summary to the terminal. Do not execute the recovery-plan apply command.
