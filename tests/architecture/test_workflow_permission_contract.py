"""Validate local reusable-workflow permission contracts before Actions runs."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE_CALLERS = (
    "release.yml",
    "baseline-release.yml",
    "production.yml",
    "promote.yml",
)
PERMISSION_LEVEL = {"none": 0, "read": 1, "write": 2}


def _workflow(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        workflow = yaml.safe_load(source)
    assert isinstance(workflow, dict), f"{path.name} must contain a YAML mapping"
    return workflow


def _permissions(scope: dict) -> dict[str, str]:
    permissions = scope.get("permissions", {})
    assert isinstance(permissions, dict), "permissions must use an explicit mapping"
    return permissions


def _permission_level(permissions: dict[str, str], name: str) -> int:
    level = permissions.get(name, "none")
    assert level in PERMISSION_LEVEL, f"unsupported {name} permission level: {level}"
    return PERMISSION_LEVEL[level]


def _local_reusable(uses: str) -> Path | None:
    prefix = "./.github/workflows/"
    if not uses.startswith(prefix):
        return None
    return WORKFLOWS / uses.removeprefix(prefix)


def test_release_workflow_callers_grant_every_local_callee_permission() -> None:
    """Actions can instantiate each release path without permission elevation."""
    pending = deque(WORKFLOWS / name for name in RELEASE_CALLERS)
    visited: set[Path] = set()

    while pending:
        caller_path = pending.popleft()
        if caller_path in visited:
            continue
        visited.add(caller_path)

        caller = _workflow(caller_path)
        for job_name, job in (caller.get("jobs") or {}).items():
            if not isinstance(job, dict) or not isinstance(job.get("uses"), str):
                continue
            callee_path = _local_reusable(job["uses"])
            if callee_path is None:
                continue
            assert callee_path.exists(), f"{caller_path.name}:{job_name} references a missing workflow"

            callee = _workflow(callee_path)
            granted = _permissions(job) if "permissions" in job else _permissions(caller)
            for permission in _permissions(callee):
                assert _permission_level(granted, permission) >= _permission_level(
                    _permissions(callee), permission
                ), (
                    f"{caller_path.name}:{job_name} grants {permission}: "
                    f"{granted.get(permission, 'none')}, but {callee_path.name} requires "
                    f"{_permissions(callee)[permission]}"
                )
            pending.append(callee_path)


def test_workflow_yaml_and_expected_manual_release_triggers_are_valid() -> None:
    """Baseline, production, and promotion releases remain manually initiated."""
    workflows = {path.name: _workflow(path) for path in WORKFLOWS.glob("*.yml")}

    assert len(workflows) == len(list(WORKFLOWS.glob("*.yml")))
    for name in ("baseline-release.yml", "production.yml", "promote.yml"):
        trigger = workflows[name].get(True, workflows[name].get("on", {}))
        assert set(trigger) == {"workflow_dispatch"}


def test_pr_ci_and_release_keep_their_minimum_explicit_permissions() -> None:
    """Quality checks get no write token; release adds only its callee's read scope."""
    assert _permissions(_workflow(WORKFLOWS / "pr-ci.yml")) == {
        "contents": "read",
        "pull-requests": "read",
    }
    assert _permissions(_workflow(WORKFLOWS / "release.yml")) == {
        "id-token": "write",
        "contents": "read",
        "pull-requests": "read",
    }


def test_secret_scan_uses_a_local_pinned_redacted_git_range_without_write_access() -> None:
    """Secret scanning must not need GitHub's PR commit-list API."""
    workflow = _workflow(WORKFLOWS / "pr-ci.yml")
    assert _permissions(workflow) == {"contents": "read", "pull-requests": "read"}

    steps = workflow["jobs"]["secret-scan"]["steps"]
    checkout = steps[0]
    scan = next(step["run"] for step in steps if step.get("name") == "Scan checked-out Git history")

    assert checkout["uses"] == "actions/checkout@v4"
    assert checkout["with"]["fetch-depth"] == 0
    assert "github.event.pull_request.base.sha" in scan
    assert "github.event.pull_request.head.sha" in scan
    assert 'git cat-file -e "${BASE_SHA}^{commit}"' in scan
    assert 'git cat-file -e "${HEAD_SHA}^{commit}"' in scan
    assert "zricethezav/gitleaks:v8.24.3" in scan
    assert "git --redact --exit-code 1 --log-opts" in scan
    assert '--log-opts="$BASE_SHA..$HEAD_SHA"' in scan
    assert "pulls/" not in scan
    assert "continue-on-error" not in repr(workflow["jobs"]["secret-scan"])


def test_route_and_event_contract_job_installs_its_yaml_parser() -> None:
    """The workflow test module imports yaml before architecture test collection."""
    job = _workflow(WORKFLOWS / "pr-ci.yml")["jobs"]["route-and-event-contracts"]
    install = next(step["run"] for step in job["steps"] if "pip install" in step.get("run", ""))

    assert "PyYAML==6.0.3" in install
