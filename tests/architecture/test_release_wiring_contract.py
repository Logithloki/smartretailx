"""Static release-wiring contracts that do not require Terraform state or AWS."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CALLER_CHECKER = ROOT / "scripts" / "check_order_callers.py"
BASELINE_WORKFLOW = ROOT / ".github" / "workflows" / "baseline-release.yml"


def _load_caller_checker():
    assert CALLER_CHECKER.exists(), "executable order-caller checker is missing"
    spec = importlib.util.spec_from_file_location("check_order_callers", CALLER_CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _order_event_filter() -> set[str]:
    source = (ROOT / "infra" / "messaging.tf").read_text(encoding="utf-8")
    subscription = re.search(
        r'resource\s+"aws_sns_topic_subscription"\s+"order_events"\s*\{(?P<body>.*?)\n\}',
        source,
        flags=re.DOTALL,
    )
    assert subscription, "order-events SNS subscription is missing"
    policy = re.search(
        r"filter_policy\s*=\s*jsonencode\(\{(?P<body>.*?)\}\)",
        subscription.group("body"),
        flags=re.DOTALL,
    )
    assert policy, "order-events SNS filter policy is missing"
    values = re.search(r"eventType\s*=\s*(?P<values>\[[^\]]+\])", policy.group("body"))
    assert values, "order-events eventType allow-list is missing"
    return set(json.loads(values.group("values")))


def test_order_event_subscription_has_the_exact_three_saga_outcomes() -> None:
    assert _order_event_filter() == {
        "order-confirmed",
        "order-rejected",
        "order-cancelled",
    }


def test_cancellation_producer_and_consumer_use_the_routed_name() -> None:
    producer = (
        ROOT / "services" / "inventory-service" / "app" / "services.py"
    ).read_text(encoding="utf-8")
    consumer = (
        ROOT / "services" / "order-service" / "app" / "compensation.py"
    ).read_text(encoding="utf-8")

    assert 'event_type="order-cancelled"' in producer
    assert '"order-cancelled": OrderStatus.CANCELLED' in consumer


def test_order_caller_checker_rejects_a_monetary_order_payload(tmp_path: Path) -> None:
    checker = _load_caller_checker()
    workflow = tmp_path / ".github" / "workflows" / "bad.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "curl -X POST /v1/orders -d "
        '\'{"items":[{"productId":"p1","quantity":1,"unitPrice":"0.01"}]}\'',
        encoding="utf-8",
    )

    violations = checker.find_violations(tmp_path)

    assert len(violations) == 1
    assert violations[0].field == "unitPrice"


def test_order_caller_checker_accepts_identifier_and_quantity_only(
    tmp_path: Path,
) -> None:
    checker = _load_caller_checker()
    workflow = tmp_path / "k6-tests" / "safe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "http.post('/v1/orders', JSON.stringify({items: "
        "[{productId: 'p1', quantity: 1}]}));",
        encoding="utf-8",
    )

    assert checker.find_violations(tmp_path) == []


def test_executable_repository_order_callers_have_no_monetary_fields() -> None:
    checker = _load_caller_checker()

    assert checker.find_violations(ROOT) == []


def test_baseline_release_is_manual_and_uses_the_default_state_lineage() -> None:
    assert BASELINE_WORKFLOW.exists(), "same-state baseline release workflow is missing"
    workflow = BASELINE_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "schedule:" not in workflow
    assert "terraform init -reconfigure" in workflow
    assert "-backend-config" not in workflow
    assert "environments/production/backend.hcl" not in workflow
    assert "smartretailx-prod" not in workflow
    assert "-var=environment_name=baseline" in workflow
    assert "-var=project_name=smartretailx" in workflow


def test_baseline_release_gates_state_before_plan_and_applies_the_reviewed_artifact() -> (
    None
):
    assert BASELINE_WORKFLOW.exists(), "same-state baseline release workflow is missing"
    workflow = BASELINE_WORKFLOW.read_text(encoding="utf-8")

    state_gate = workflow.index("check_baseline_plan.py --state-list")
    plan = workflow.index("terraform plan")
    destruction_gate = workflow.index("check_baseline_plan.py tfplan.json")
    assert state_gate < plan < destruction_gate
    assert "environment: development" in workflow
    assert "terraform apply tfplan" in workflow
    assert "reviewed-baseline-plan" in workflow


def test_plan_role_can_read_the_existing_baseline_state_key() -> None:
    oidc = (ROOT / "infra" / "oidc.tf").read_text(encoding="utf-8")

    assert (
        'arn:aws:s3:::smartretailx-tfstate-322551984077/smartretailx/terraform.tfstate"'
        in oidc
    )
    assert (
        'arn:aws:s3:::smartretailx-tfstate-322551984077/smartretailx/terraform.tfstate.tflock"'
        in oidc
    )


def test_product_price_refresh_reuses_the_existing_product_stream_and_marker_filter() -> (
    None
):
    data = (ROOT / "infra" / "data.tf").read_text(encoding="utf-8")
    pipes = (ROOT / "infra" / "pipes.tf").read_text(encoding="utf-8")

    assert 'resource "aws_dynamodb_table" "products"' in data
    assert "stream_enabled   = true" in data
    assert 'stream_view_type = "NEW_AND_OLD_IMAGES"' in data
    assert "ReadProductsStream" in pipes
    assert 'resource "aws_pipes_pipe" "product_price_refresh"' in pipes
    assert "source   = aws_dynamodb_table.products.stream_arn" in pipes
    assert 'priceEventPending = { S = ["true"] }' in pipes
    assert 'detail_type = "product.price-refresh"' in pipes
    assert 'source      = "smartretailx.products"' in pipes


def test_order_status_pipe_includes_live_cancellation_states() -> None:
    pipes = (ROOT / "infra" / "pipes.tf").read_text(encoding="utf-8")

    assert 'S = ["CONFIRMED", "REJECTED", "CANCEL_PENDING", "CANCELLED"]' in pipes


def test_promotions_use_disable_not_hard_delete_and_follow_least_privilege() -> None:
    main = (ROOT / "services" / "product-service" / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    security = (ROOT / "infra" / "security.tf").read_text(encoding="utf-8")
    promotion_statement = security.split('Sid      = "PromotionReadsAndWrites"', 1)[
        1
    ].split("Resource =", 1)[0]

    assert '@app.delete(\n        "/v1/promotions' not in main
    assert "dynamodb:DeleteItem" not in promotion_statement


def test_github_deploy_role_can_verify_alarms_with_least_privilege() -> None:
    oidc = (ROOT / "infra" / "oidc.tf").read_text(encoding="utf-8")
    deploy_policy = oidc.split('resource "aws_iam_role_policy" "gha_deploy"', 1)[
        1
    ].split('output "github_oidc_role_arn"', 1)[0]

    assert re.search(r'Sid\s*=\s*"CloudWatchDeploymentVerification"', deploy_policy)
    assert re.search(r'Action\s*=\s*\["cloudwatch:DescribeAlarms"\]', deploy_policy)
    assert re.search(r'Resource\s*=\s*"\*"', deploy_policy)
    assert '"cloudwatch:*"' not in deploy_policy

    workflow = (ROOT / ".github" / "workflows" / "reusable-deploy-ecs.yml").read_text(
        encoding="utf-8"
    )
    assert re.findall(r"aws cloudwatch ([a-z-]+)", workflow) == ["describe-alarms"]


def test_github_deploy_policy_uses_stable_lambda_names_without_resource_dependency() -> (
    None
):
    oidc = (ROOT / "infra" / "oidc.tf").read_text(encoding="utf-8")
    deploy_policy = oidc.split('resource "aws_iam_role_policy" "gha_deploy"', 1)[
        1
    ].split('output "github_oidc_role_arn"', 1)[0]

    assert "local.gha_deploy_lambda_names" in deploy_policy
    assert "local.operational_lambdas" not in deploy_policy
    assert "aws_lambda_function.cognito_auto_confirm" not in deploy_policy


def test_github_deploy_lambda_policy_scopes_ws_authorizer_least_privilege() -> None:
    oidc = (ROOT / "infra" / "oidc.tf").read_text(encoding="utf-8")
    names = re.search(
        r"gha_deploy_lambda_names\s*=\s*\[(?P<names>.*?)\]",
        oidc,
        flags=re.DOTALL,
    )
    assert names, "GHA deploy Lambda name set is missing"
    assert '"${var.project_name}-ws-authorizer"' in names.group("names")

    deploy_policy = oidc.split('resource "aws_iam_role_policy" "gha_deploy"', 1)[
        1
    ].split('output "github_oidc_role_arn"', 1)[0]
    lambda_promotion = deploy_policy.split('Sid    = "LambdaVersionPromotion"', 1)[
        1
    ].split("},", 1)[0]

    assert '"lambda:UpdateFunctionCode"' in lambda_promotion
    assert '"lambda:*"' not in lambda_promotion
    assert 'Resource = "*"' not in lambda_promotion
    assert "function:${function_name}" in lambda_promotion
    assert "function:${function_name}:*" in lambda_promotion


def test_nonbaseline_github_roles_do_not_generate_empty_ecr_resource_lists() -> None:
    oidc = (ROOT / "infra" / "oidc.tf").read_text(encoding="utf-8")

    release_policy = oidc.split('resource "aws_iam_role_policy" "gha_release"', 1)[
        1
    ].split("# Read-only planning", 1)[0]
    deploy_policy = oidc.split('resource "aws_iam_role_policy" "gha_deploy"', 1)[
        1
    ].split('output "github_oidc_role_arn"', 1)[0]

    # Builds publish only to baseline's central repositories. Test and Staging
    # consume immutable digests, so they must not render an IAM statement whose
    # resource collection is empty after their local ECR repositories are omitted.
    assert 'count = var.environment_name == "baseline" ? 1 : 0' in release_policy
    deploy_ecr = oidc.split("gha_deploy_ecr_statements = [", 1)[1].split(
        "\n  ]\n}", 1
    )[0]
    assert "gha_deploy_ecr_statements" in oidc
    assert (
        "for statement in local.gha_deploy_ecr_statements : statement\n"
        '        if var.environment_name == "baseline"'
    ) in deploy_policy
    assert 'var.environment_name == "baseline" ? [' not in deploy_policy
    assert 'Resource = ["*"]' in deploy_ecr
    assert (
        "Resource = [for repository in aws_ecr_repository.services : repository.arn]"
        in deploy_ecr
    )


def test_all_eventbridge_pipes_wait_for_their_execution_role_policy() -> None:
    pipes = (ROOT / "infra" / "pipes.tf").read_text(encoding="utf-8")

    for pipe_name in (
        "order_status",
        "product_price_refresh",
        "promotion_price_refresh",
    ):
        pipe = re.search(
            rf'resource "aws_pipes_pipe" "{pipe_name}" \{{(?P<body>.*?)\n\}}',
            pipes,
            flags=re.DOTALL,
        )
        assert pipe, f"{pipe_name} Pipe is missing"
        assert "depends_on = [aws_iam_role_policy.pipes]" in pipe.group("body")
