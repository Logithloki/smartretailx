"""Evaluated contracts for post-deployment Terraform convergence."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
CLOUDFRONT_ADDRESS = "aws_cloudfront_distribution.main"
GITHUB_OIDC_ADDRESS = "aws_iam_openid_connect_provider.github"
GITHUB_LEGACY_THUMBPRINT = "ab9d0263244dd0326eb67015705a667e79cfe998"


def _run_terraform(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["terraform", *args],
        cwd=INFRA,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="session")
def convergence_changes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict]:
    plan_path = tmp_path_factory.mktemp("terraform-convergence-contract") / "convergence.tfplan"
    plan = _run_terraform(
        "plan",
        "-refresh=false",
        "-lock=false",
        "-input=false",
        "-no-color",
        "-var=environment_name=baseline",
        "-var=live=true",
        "-var=enable_grafana=false",
        f"-target={CLOUDFRONT_ADDRESS}",
        f"-target={GITHUB_OIDC_ADDRESS}",
        f"-out={plan_path}",
    )
    assert plan.returncode == 0, plan.stdout + plan.stderr

    rendered = _run_terraform("show", "-json", str(plan_path))
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    plan_json = json.loads(rendered.stdout)
    return {
        change["address"]: change
        for change in plan_json.get("resource_changes", [])
    }


def test_cloudfront_default_certificate_uses_supported_tls_representation(
    convergence_changes: dict[str, dict],
) -> None:
    change = convergence_changes[CLOUDFRONT_ADDRESS]
    certificate = change["change"]["after"]["viewer_certificate"][0]

    assert certificate["cloudfront_default_certificate"] is True
    assert certificate["minimum_protocol_version"] == "TLSv1"


def test_github_oidc_preserves_the_aws_retained_legacy_thumbprint(
    convergence_changes: dict[str, dict],
) -> None:
    change = convergence_changes[GITHUB_OIDC_ADDRESS]

    assert change["change"]["after"]["url"] == "token.actions.githubusercontent.com"
    assert change["change"]["after"]["client_id_list"] == ["sts.amazonaws.com"]
    assert change["change"]["after"]["thumbprint_list"] == [GITHUB_LEGACY_THUMBPRINT]


def test_terraform_keeps_promoted_ecs_release_pointers_out_of_reconciliation() -> None:
    """A successful immutable promotion, not Terraform, selects an ECS revision."""
    compute = (INFRA / "compute.tf").read_text(encoding="utf-8")

    service = compute.split('resource "aws_ecs_service" "services" {', 1)[1].split(
        "\n}", 1
    )[0]
    bootstrap_task_definition = compute.split(
        'resource "aws_ecs_task_definition" "bootstrap_services" {', 1
    )[1].split("\n}\n\n#", 1)[0]

    assert "ignore_changes = [desired_count, task_definition]" in service
    assert "aws_ecs_task_definition.bootstrap_services[each.key].arn" in service
    assert 'family                   = "${var.project_name}-${each.key}-bootstrap"' in bootstrap_task_definition
    assert 'removed {' in compute
    assert 'from = aws_ecs_task_definition.services' in compute
    assert 'destroy = false' in compute
    assert 'resource "aws_ecs_task_definition" "services"' not in compute
    assert "ignore_changes = [container_definitions]" not in compute


def test_release_managed_lambda_code_and_aliases_do_not_roll_back() -> None:
    """Terraform retains Lambda structure while promotions select code/version."""
    source = "\n".join(
        (INFRA / name).read_text(encoding="utf-8")
        for name in ("lambdas.tf", "websocket.tf")
    )

    for function in (
        "order_outbox_publisher",
        "notification",
        "reconciliation",
        "ws_authorizer",
        "ws_connect",
        "ws_disconnect",
        "ws_push",
    ):
        block = source.split(f'resource "aws_lambda_function" "{function}" {{', 1)[1].split(
            "\n}", 1
        )[0]
        alias = source.split(f'resource "aws_lambda_alias" "{function}" {{', 1)[1].split(
            "\n}", 1
        )[0]
        assert "ignore_changes = [filename, source_code_hash]" in block
        assert "ignore_changes = [function_version]" in alias


def test_pipe_and_cognito_normalization_are_explicit_and_convergent() -> None:
    pipes = (INFRA / "pipes.tf").read_text(encoding="utf-8")
    security = (INFRA / "security.tf").read_text(encoding="utf-8")

    assert pipes.count("maximum_retry_attempts = 3") == 3
    assert 'css = replace(<<-EOF' in security
    assert '"\\r\\n", "\\n"' in security


@pytest.mark.parametrize("address", (CLOUDFRONT_ADDRESS, GITHUB_OIDC_ADDRESS))
def test_post_deployment_resources_have_no_perpetual_diff(
    convergence_changes: dict[str, dict], address: str
) -> None:
    assert convergence_changes[address]["change"]["actions"] == ["no-op"]
