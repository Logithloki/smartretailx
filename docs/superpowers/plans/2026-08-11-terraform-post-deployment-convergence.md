# Terraform Post-Deployment Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the two post-deployment perpetual Terraform diffs without applying Terraform, mutating AWS, or manipulating state.

**Architecture:** Represent the deployed CloudFront default certificate using its provider-supported `TLSv1` API value and preserve the legacy GitHub OIDC thumbprint that AWS retains but does not use for GitHub certificate verification. Prove the behavior with an evaluated Terraform-plan contract, the existing protected-resource deletion policy, and a fresh full convergence plan.

**Tech Stack:** Terraform, HashiCorp AWS provider, Python 3.12, pytest, Checkov.

## Global Constraints

- Do not run `terraform apply` or modify AWS.
- Do not destroy, replace, import, or manipulate Terraform state.
- Keep `environment_name=baseline`, `live=true`, and `enable_grafana=false`.
- Do not add an ACM certificate, custom domain, lifecycle drift suppression, or unrelated infrastructure changes.

---

### Task 1: Reproduce and contract the perpetual diffs

**Files:**
- Create: `tests/architecture/test_terraform_convergence_contract.py`
- Modify: `tests/architecture/test_baseline_plan_policy.py`

**Interfaces:**
- Consumes: The existing baseline Terraform backend/state and the two managed resource addresses.
- Produces: A targeted refresh-free plan contract that requires the deployed resources to be no-ops and validates their supported configured values.

- [x] Run the baseline-live refresh-free plan and confirm only the two reported in-place updates.
- [x] Add tests asserting the default CloudFront certificate resolves to `TLSv1`, the GitHub OIDC provider preserves `ab9d0263244dd0326eb67015705a667e79cfe998`, and both actions are `no-op`.
- [x] Add the GitHub OIDC provider to the existing protected-resource replacement matrix.
- [x] Run the new convergence tests and confirm they fail for the two diagnosed configuration differences.

### Task 2: Apply the minimal deterministic configuration repair

**Files:**
- Modify: `infra/frontend.tf`
- Modify: `infra/oidc.tf`

**Interfaces:**
- Consumes: HashiCorp's CloudFront default-certificate and IAM OIDC retention semantics.
- Produces: Configuration matching the already-deployed resource identities and values.

- [x] Set the default-certificate protocol representation to `TLSv1` and document that selectable stronger policies require a custom certificate.
- [x] Replace the empty OIDC thumbprint declaration with the retained legacy value and document that AWS retains but does not use it for GitHub validation.
- [x] Run the convergence contract and confirm it passes without `ignore_changes`.

### Task 3: Validate convergence and document the result

**Files:**
- Modify: `docs/partial-apply-recovery-audit.md`

**Interfaces:**
- Consumes: The final validation and Terraform-plan output.
- Produces: A post-deployment convergence record with causes, exact changes, evidence, and zero-change outcome.

- [x] Run `terraform fmt -recursive -check` and `terraform validate`.
- [x] Run the complete architecture suite and Checkov.
- [x] Run the baseline-live plan with refresh and require `No changes. Your infrastructure matches the configuration.`
- [x] Confirm the zero-change plan and protected-resource policy contain no deletion or replacement.
- [x] Update the recovery audit with both causes, exact code changes, validation results, and the final zero-change result.
- [x] Inspect the final repository diff and stop before apply.
