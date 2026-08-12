# Deployment and evidence handbook

## GitHub setup required once

Create GitHub Environments named `development`, `test`, `staging`, and `production`. Restrict each to `main`; require a reviewer for production (and preferably staging). Add these environment variables using the corresponding Terraform outputs:

- `SMARTRETAILX_DEPLOY_ROLE_ARN`
- `SMARTRETAILX_PROJECT_NAME`
- `SMARTRETAILX_ECS_CLUSTER_NAME`
- `SMARTRETAILX_SPA_BUCKET`
- `SMARTRETAILX_DISTRIBUTION_ID`
- `SMARTRETAILX_PUBLIC_URL` (CloudFront URL, no trailing slash)
- `SMARTRETAILX_WEBSOCKET_URL`
- `SMARTRETAILX_COGNITO_AUTHORITY`
- `SMARTRETAILX_COGNITO_DOMAIN`
- `SMARTRETAILX_COGNITO_CLIENT_ID`

Repository variable `SMARTRETAILX_RELEASE_ROLE_ARN` is the main-only ECR role. `SMARTRETAILX_TERRAFORM_PLAN_ROLE_ARN` is the main-only planning role. `SMARTRETAILX_TERRAFORM_APPLY_ROLE_ARN` must be a separately bootstrapped production provisioning role; do not reuse the application deploy role.

Add short-lived test secrets per live environment: `SMARTRETAILX_SMOKE_ACCESS_TOKEN`, customer/admin tokens for Newman, and customer/admin usernames/passwords for Playwright. Never commit these values. Rotate them after evidence windows.

## Safe sequence

1. Merge only after `PR quality gates` is green.
2. Record the successful `Build immutable release` run ID and download its manifest.
3. Provision/plan an isolated environment using its backend and tfvars; inspect add/change/destroy.
4. Run `Promote immutable release` for development. Confirm smoke artifact.
5. Repeat the same run ID for test; require Newman and Playwright evidence.
6. Repeat the same run ID for staging; run the k6 load profile and intentional resilience tests.
7. Run `Production reviewed-plan deployment` from `main`. Review `plan-summary.json` and `tfplan.json` before approving the production Environment.
8. Confirm production smoke/E2E, alarms and observation window. Download rollback/evidence artifacts.
9. Park non-production: `powershell -File scripts/set-live.ps1 -Environment staging -Action park`. Review the plan and type the displayed confirmation.

The production workflow is intentionally unusable until GitHub protections and the apply role exist. This fails closed.

## Migration rules

Alembic migrations must be additive/backward compatible for rolling deployments. Run `alembic upgrade head --sql` in review. The ECS workflow runs the migration task before updating Inventory. Destructive changes require a separate reviewed release and backup evidence; never hide them inside application startup.

## Rollback verification

Before production apply the workflow stores `production-rollback-targets`. On failure it restores the four task definitions, seven Lambda aliases, and prior S3 release, then waits for ECS stability. Verify the `production-rollback-result` artifact, primary task definitions, Lambda alias versions, `/release.json`, 5xx/unhealthy alarms, queue/DLQ depth, and a fresh authenticated smoke.

## Evidence without secrets

Download coverage XML, LocalStack logs, release manifest/SBOMs, plan JSON/summary, Newman JUnit/JSON, Playwright report/traces, k6 JSON and smoke/rollback JSON into the numbered assignment evidence set. Screenshots must show timestamp/environment/release ID. Redact JWTs, cookies, email addresses and secret values.
