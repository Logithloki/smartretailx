"""Evaluated Terraform contracts for baseline parking and live restoration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
APPLICATION_TARGETS = {
    f'aws_appautoscaling_target.ecs_target["{service}"]'
    for service in ("order", "inventory", "product", "user")
}
GRAFANA_RUNTIME = {
    "aws_ecs_service.grafana[0]",
    "aws_lb_target_group.grafana[0]",
    "aws_lb_listener_rule.grafana[0]",
}
PERSISTENT_ADDRESSES = {
    "aws_vpc.main",
    "aws_rds_cluster.inventory",
    "aws_rds_cluster_instance.writer",
    "aws_dynamodb_table.orders",
    "aws_dynamodb_table.products",
    "aws_dynamodb_table.idempotency",
    "aws_dynamodb_table.websocket_connections",
    "aws_cognito_user_pool.main",
    "aws_s3_bucket.spa",
    "aws_cloudfront_distribution.main",
    "aws_ecs_cluster.main",
    *{f"aws_subnet.{tier}[{index}]" for tier in ("public", "private", "data") for index in range(2)},
    *{
        f'aws_ecr_repository.services["{service}-service"]'
        for service in ("order", "inventory", "product", "user")
    },
}


def _run_terraform(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["terraform", *args],
        cwd=INFRA,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="session")
def baseline_plans(tmp_path_factory: pytest.TempPathFactory) -> dict[bool, dict]:
    plan_dir = tmp_path_factory.mktemp("baseline-runtime-contract")
    plans: dict[bool, dict] = {}

    for live in (False, True):
        plan_path = plan_dir / f"baseline-live-{str(live).lower()}.tfplan"
        plan = _run_terraform(
            "plan",
            "-refresh=false",
            "-lock=false",
            "-input=false",
            "-no-color",
            "-var=environment_name=baseline",
            f"-var=live={str(live).lower()}",
            f"-out={plan_path}",
        )
        assert plan.returncode == 0, plan.stdout + plan.stderr

        rendered = _run_terraform("show", "-json", str(plan_path))
        assert rendered.returncode == 0, rendered.stdout + rendered.stderr
        plans[live] = json.loads(rendered.stdout)

    return plans


def _changes_by_address(plan: dict) -> dict[str, dict]:
    return {change["address"]: change for change in plan.get("resource_changes", [])}


def test_live_false_preserves_persistent_and_data_resources(baseline_plans: dict[bool, dict]) -> None:
    parked = _changes_by_address(baseline_plans[False])

    assert PERSISTENT_ADDRESSES <= parked.keys()
    destructive = {
        address
        for address in PERSISTENT_ADDRESSES
        if "delete" in parked[address]["change"]["actions"]
    }
    assert destructive == set()


def test_live_false_parks_application_runtime_floor(baseline_plans: dict[bool, dict]) -> None:
    parked = _changes_by_address(baseline_plans[False])

    assert APPLICATION_TARGETS <= parked.keys()
    assert {
        parked[address]["change"]["after"]["min_capacity"]
        for address in APPLICATION_TARGETS
    } == {0}


def test_live_true_restores_one_baseline_task_per_service(baseline_plans: dict[bool, dict]) -> None:
    live = _changes_by_address(baseline_plans[True])

    assert APPLICATION_TARGETS <= live.keys()
    assert {
        live[address]["change"]["after"]["min_capacity"]
        for address in APPLICATION_TARGETS
    } == {1}


def test_grafana_runtime_remains_optional_by_default(baseline_plans: dict[bool, dict]) -> None:
    live_addresses = _changes_by_address(baseline_plans[True]).keys()

    assert GRAFANA_RUNTIME.isdisjoint(live_addresses)

