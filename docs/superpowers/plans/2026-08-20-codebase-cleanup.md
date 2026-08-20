# SmartRetailX Codebase Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove only verified repository clutter and low-value comments while preserving application, infrastructure, evidence, and CI behaviour.

**Architecture:** Audit the isolated branch first, classify candidates by references and tooling, then make minimal edits limited to hygiene, comments, and confidently unused code. Protected evidence paths are excluded from all edits and deletions.

**Tech Stack:** Git worktrees, PowerShell, ripgrep, Python/pytest, frontend npm scripts, Terraform, existing gitleaks configuration.

**Spec:** `C:/Users/ACER/.codex/attachments/5db1ffd6-0cac-4e8b-bc58-43ec556309b3/pasted-text.txt`

## Global Constraints

- Do not add features, change APIs, alter AWS resources, deploy, or touch Production.
- Preserve `assignment-screenshots/`, `evidence/`, final-evidence documentation, source, tests, Terraform, workflows, lock files, diagrams, and performance/security evidence.
- Do not delete a file without checking references with Git/ripgrep and build/test configuration.
- Keep comments short and specific; retain comments explaining security, concurrency, platform behaviour, failure handling, and business rules.
- Never expose credentials, tokens, passwords, or secret values.

---

### Task 1: Audit and classify repository contents

**Files:**
- Read-only: repository tree, `.gitignore`, manifests, workflows, Dockerfiles, Terraform, README/docs, tests.

- [ ] **Step 1: Record baseline Git state**

Run `git status --short`, `git branch --show-current`, `git worktree list`, and `git ls-files` in the isolated worktree. Confirm the protected evidence directories are present and untouched.

- [ ] **Step 2: Identify candidates**

Search for temporary files, generated outputs, stale commented-out code, `TODO`/`FIXME`/`HACK`/`XXX`, debug calls, AI/tool attribution, and suspicious secret patterns. Classify each candidate as safe, keep, or uncertain.

- [ ] **Step 3: Verify references before changes**

For each safe candidate, use `git grep`, `rg`, package/build configuration, imports, and workflow references. Do not remove uncertain files.

### Task 2: Apply minimal cleanup

**Files:**
- Modify only verified source/config/comment files.
- Delete only verified disposable artifacts; never modify protected evidence paths.

- [ ] **Step 1: Remove stale comments and dead imports**

Edit only comments that repeat obvious code, describe removed behaviour, or contain completed temporary notes. Remove imports/code only when reference searches and configured checks prove they are unused.

- [ ] **Step 2: Improve retained comments**

Rewrite only non-obvious comments so they state the relevant reason, security/concurrency constraint, platform workaround, or failure-handling rule in one or two natural lines.

- [ ] **Step 3: Update `.gitignore` only for confirmed local/generated artifacts**

Keep all assignment evidence and required source visible to Git. Do not add broad patterns that could hide deliverables.

### Task 3: Validate and review

**Files:**
- Read-only validation of the final diff and configured checks.

- [ ] **Step 1: Run configured fast checks**

Run the existing frontend tests/lint/typecheck, backend tests/lint, `terraform fmt -check`/`terraform validate` where initialization permits, and the existing secret scan. Do not run deployment or expensive k6/resilience campaigns.

- [ ] **Step 2: Review the diff**

Run `git diff --stat` and `git diff`; confirm no evidence deletion, API/business/infrastructure/CI change, weakened test assertion, secret, or unrelated formatting churn.

- [ ] **Step 3: Commit the focused branch**

After fresh verification, commit with `chore: clean up project structure and code comments`.
