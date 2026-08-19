"""Unit contracts for the saved baseline-plan deletion policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
POLICY_SCRIPT = ROOT / "scripts" / "check_baseline_plan.py"
PROTECTED_ADDRESSES = (
    "aws_vpc.main",
    "aws_subnet.private[0]",
    "aws_rds_cluster.inventory",
    "aws_rds_cluster_instance.writer",
    "aws_dynamodb_table.orders",
    "aws_cognito_user_pool.main",
    "aws_s3_bucket.spa",
    "aws_cloudfront_distribution.main",
    "aws_iam_openid_connect_provider.github",
    'aws_ecr_repository.services["order-service"]',
    "aws_ecs_cluster.main",
)
ALLOWED_REPLACEMENTS = (
    'aws_ecs_task_definition.bootstrap_services["order"]',
    'aws_ecs_task_definition.bootstrap_services["inventory"]',
    'aws_ecs_task_definition.bootstrap_services["product"]',
    'aws_ecs_task_definition.bootstrap_services["user"]',
    "aws_lambda_permission.notification_sns",
    "aws_lambda_permission.ws_authorizer_invoke",
    "aws_sns_topic_subscription.notification",
)
UNKNOWN_ECS_REPLACEMENT = 'aws_ecs_task_definition.bootstrap_services["grafana"]'
REQUIRED_STATE_ADDRESSES = {
    "aws_vpc.main",
    "aws_ecs_cluster.main",
    "aws_cognito_user_pool.main",
    "aws_rds_cluster.inventory",
    "aws_dynamodb_table.orders",
    "aws_dynamodb_table.products",
    "aws_s3_bucket.spa",
    "aws_cloudfront_distribution.main",
}


def _load_policy_module():
    assert POLICY_SCRIPT.exists(), "saved-plan policy implementation is missing"
    spec = importlib.util.spec_from_file_location("check_baseline_plan", POLICY_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plan_with_replacements(*addresses: str) -> dict:
    return {
        "resource_changes": [
            {
                "address": address,
                "change": {"actions": ["delete", "create"]},
            }
            for address in addresses
        ]
    }


@pytest.mark.parametrize("address", PROTECTED_ADDRESSES)
def test_policy_rejects_protected_resource_replacement(address: str) -> None:
    policy = _load_policy_module()

    violations = policy.evaluate_plan(_plan_with_replacements(address))

    assert violations == [f"unapproved delete/replacement: {address}"]


def test_policy_accepts_only_the_approved_application_replacements() -> None:
    policy = _load_policy_module()

    violations = policy.evaluate_plan(_plan_with_replacements(*ALLOWED_REPLACEMENTS))

    assert violations == []


@pytest.mark.parametrize(
    "address",
    [
        'aws_ecs_task_definition.bootstrap_services["order"]',
        'aws_ecs_task_definition.bootstrap_services["inventory"]',
        'aws_ecs_task_definition.bootstrap_services["product"]',
        'aws_ecs_task_definition.bootstrap_services["user"]',
    ],
)
def test_policy_allows_each_bootstrap_task_definition_replacement(address: str) -> None:
    policy = _load_policy_module()

    assert policy.evaluate_plan(_plan_with_replacements(address)) == []


def test_policy_rejects_an_unapproved_application_replacement() -> None:
    policy = _load_policy_module()

    violations = policy.evaluate_plan(_plan_with_replacements(UNKNOWN_ECS_REPLACEMENT))

    assert violations == [f"unapproved delete/replacement: {UNKNOWN_ECS_REPLACEMENT}"]


def test_policy_rejects_stale_pre_rename_task_definition_address() -> None:
    policy = _load_policy_module()
    stale_address = 'aws_ecs_task_definition.services["order"]'

    violations = policy.evaluate_plan(_plan_with_replacements(stale_address))

    assert violations == [f"unapproved delete/replacement: {stale_address}"]


def test_policy_rejects_pure_destroy_of_a_bootstrap_task_definition() -> None:
    policy = _load_policy_module()
    plan = {
        "resource_changes": [
            {
                "address": 'aws_ecs_task_definition.bootstrap_services["order"]',
                "change": {"actions": ["delete"]},
            }
        ]
    }

    violations = policy.evaluate_plan(plan)

    assert violations == [
        "approved address is being destroyed without replacement: "
        'aws_ecs_task_definition.bootstrap_services["order"]'
    ]


def test_policy_rejects_pure_destroy_of_an_approved_address() -> None:
    policy = _load_policy_module()
    plan = {
        "resource_changes": [
            {
                "address": "aws_lambda_permission.notification_sns",
                "change": {"actions": ["delete"]},
            }
        ]
    }

    violations = policy.evaluate_plan(plan)

    assert violations == [
        "approved address is being destroyed without replacement: "
        "aws_lambda_permission.notification_sns"
    ]


def test_state_sanity_accepts_the_existing_baseline_sentinels() -> None:
    policy = _load_policy_module()

    assert policy.evaluate_state_addresses(REQUIRED_STATE_ADDRESSES) == []


def test_state_sanity_rejects_an_empty_state() -> None:
    policy = _load_policy_module()

    violations = policy.evaluate_state_addresses(set())

    assert violations == [
        f"required baseline state address is missing: {address}"
        for address in sorted(REQUIRED_STATE_ADDRESSES)
    ]


def test_state_sanity_rejects_a_partial_state() -> None:
    policy = _load_policy_module()
    partial = REQUIRED_STATE_ADDRESSES - {"aws_cloudfront_distribution.main"}

    assert policy.evaluate_state_addresses(partial) == [
        "required baseline state address is missing: aws_cloudfront_distribution.main"
    ]
