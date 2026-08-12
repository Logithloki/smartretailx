"""Generated-JSON contract for the CloudWatch operations dashboard."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
DASHBOARD_ADDRESS = "aws_cloudwatch_dashboard.operations"
EXPECTED_WIDGET_TITLES = {
    "HTTP API requests, 4XX and 5XX",
    "HTTP API latency percentiles",
    "ECS CPU by service",
    "ECS memory by service",
    "Queue backlog and DLQs",
    "Lambda errors and throttles",
    "Aurora capacity, connections and latency",
    "DynamoDB requests and throttling",
    "Queue depth and oldest message age",
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
def dashboard_body(tmp_path_factory: pytest.TempPathFactory) -> dict:
    plan_path = tmp_path_factory.mktemp("cloudwatch-dashboard-contract") / "dashboard.tfplan"
    plan = _run_terraform(
        "plan",
        "-refresh=false",
        "-lock=false",
        "-input=false",
        "-no-color",
        "-var=environment_name=baseline",
        "-var=live=true",
        "-var=enable_grafana=false",
        f"-target={DASHBOARD_ADDRESS}",
        f"-out={plan_path}",
    )
    assert plan.returncode == 0, plan.stdout + plan.stderr

    rendered = _run_terraform("show", "-json", str(plan_path))
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    plan_json = json.loads(rendered.stdout)
    dashboard_change = next(
        change
        for change in plan_json["resource_changes"]
        if change["address"] == DASHBOARD_ADDRESS
    )
    return json.loads(dashboard_change["change"]["after"]["dashboard_body"])


def _metric_widgets(dashboard_body: dict) -> list[dict]:
    return [widget for widget in dashboard_body["widgets"] if widget["type"] == "metric"]


def test_dashboard_contains_every_operations_metric_widget(dashboard_body: dict) -> None:
    titles = {
        widget["properties"]["title"]
        for widget in _metric_widgets(dashboard_body)
    }

    assert titles == EXPECTED_WIDGET_TITLES


def test_every_metrics_value_is_a_list_of_metric_rows(dashboard_body: dict) -> None:
    invalid_widgets: list[str] = []

    for widget in _metric_widgets(dashboard_body):
        metrics = widget["properties"].get("metrics")
        if not isinstance(metrics, list) or not all(
            isinstance(metric, list) for metric in metrics
        ):
            invalid_widgets.append(widget["properties"]["title"])

    assert invalid_widgets == []


def test_metric_renderer_object_can_only_be_the_final_row_item(dashboard_body: dict) -> None:
    invalid_rows: list[str] = []

    for widget in _metric_widgets(dashboard_body):
        title = widget["properties"]["title"]
        metrics = widget["properties"].get("metrics", [])
        if not isinstance(metrics, list):
            invalid_rows.append(title)
            continue
        for metric in metrics:
            if not isinstance(metric, list):
                invalid_rows.append(title)
                continue
            values = metric[:-1] if metric and isinstance(metric[-1], dict) else metric
            if not values or not all(isinstance(value, str) for value in values):
                invalid_rows.append(title)

    assert sorted(set(invalid_rows)) == []

