# Baseline Live Reconciliation Design

**Date:** 2026-08-11  
**Scope:** Existing `baseline` Terraform state in `eu-west-1`  
**Approved outcome:** A saved `live=true` plan that preserves all persistent infrastructure, keeps Grafana optional, restores one baseline task per application service, and contains only the four accepted application-level replacements.

## Constraints

- Reuse the configured S3 backend and the current `default` workspace.
- Do not import resources, edit state, migrate the backend, destroy resources, or apply Terraform.
- Preserve the existing `baseline` to `development` compatibility mapping for Lambda aliases and GitHub environments.
- Keep `live=false` as the parking contract: application ECS services have zero runtime tasks while persistent and data resources remain managed.
- Set the default live baseline to one task per application ECS service.
- Preserve Grafana's task definition, IAM, secret, log/configuration resources, and source code.
- Gate only the Grafana ECS service, target group, and listener rule behind `enable_grafana`, whose default is `false`.

## Current-State Findings

The read-only reconciliation found the VPC, six subnets, Aurora cluster and writer, persistent DynamoDB tables, Cognito pool, SPA bucket, CloudFront distribution, ECR repositories, and ECS cluster aligned between AWS and Terraform state. The diagnostic plan contained no pure destruction and no evidence that an unmanaged AWS resource needed import.

The diagnostic plan's five delete actions were replacement halves. Four are approved immutable application revisions:

1. `aws_ecs_task_definition.services["order"]`
2. `aws_lambda_permission.notification_sns`
3. `aws_lambda_permission.ws_authorizer_invoke`
4. `aws_sns_topic_subscription.notification`

The fifth was the Grafana task definition, caused only by deriving its root URL from the live ALB. Making the Grafana runtime optional and retaining localhost configuration while disabled removes that replacement.

## Terraform Design

`variable "enable_grafana"` defaults to `false`. A local value combines it with `live`:

```hcl
grafana_runtime_enabled = var.live && var.enable_grafana
```

Only the Grafana target group, listener rule, and ECS service use this value for `count`. The preserved Grafana Cognito client and task definition also use the value only to choose between live ALB URLs and their existing localhost fallback; they are never count-gated.

`service_desired_count` defaults to `1`. Existing application service and autoscaling expressions remain conditional:

```hcl
desired_count = var.live ? var.service_desired_count : 0
min_capacity  = var.live ? var.service_desired_count : 0
```

Consequently, `live=false` remains parked at zero and `live=true` restores the baseline to one. Environment profiles can still override the value explicitly.

## Safety Contracts

Two complementary test boundaries provide evidence:

- Terraform configuration contracts evaluate actual `terraform plan` JSON for both `live=false` and `live=true`, proving persistence, parking, baseline restoration, and Grafana optionality from Terraform's evaluated behavior.
- A saved-plan policy analyzer rejects any deletion action for the VPC, subnets, Aurora cluster or writer, DynamoDB tables, Cognito pool, SPA bucket, CloudFront distribution, ECR repositories, or ECS cluster. It also rejects every unapproved delete elsewhere.

The final binary plan is saved as `infra/baseline-live.tfplan`; its human-readable rendering is saved as `infra/baseline-live-plan.txt`. The analyzer is executed against the saved plan's JSON representation before the audit can classify it.

## Classification Rule

- **SAFE TO APPLY:** all protected resources avoid deletion/replacement; every deletion is one of the four approved application-level replacements; validation and safety contracts pass.
- **SAFE AFTER MANUAL ACTION:** the plan itself is safe but a specific prerequisite outside Terraform must be completed first.
- **NOT SAFE TO APPLY:** a protected resource is deleted/replaced, an unapproved deletion exists, validation fails, or a blocking mismatch remains.

No apply is part of this design. The workflow stops after producing and auditing the saved plan.
