"""Reject destructive changes outside the approved baseline replacement set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO


ALLOWED_REPLACEMENTS = {
    'aws_ecs_task_definition.services["order"]',
    "aws_lambda_permission.notification_sns",
    "aws_lambda_permission.ws_authorizer_invoke",
    "aws_sns_topic_subscription.notification",
}
REQUIRED_BASELINE_STATE_ADDRESSES = {
    "aws_vpc.main",
    "aws_ecs_cluster.main",
    "aws_cognito_user_pool.main",
    "aws_rds_cluster.inventory",
    "aws_dynamodb_table.orders",
    "aws_dynamodb_table.products",
    "aws_s3_bucket.spa",
    "aws_cloudfront_distribution.main",
}


def evaluate_state_addresses(addresses: set[str]) -> list[str]:
    """Reject empty or wrong state lineages before a baseline plan is made."""
    return [
        f"required baseline state address is missing: {address}"
        for address in sorted(REQUIRED_BASELINE_STATE_ADDRESSES - addresses)
    ]


def evaluate_plan(plan: dict[str, Any]) -> list[str]:
    """Return one diagnostic for every unapproved Terraform delete action."""
    violations: list[str] = []
    for resource_change in plan.get("resource_changes", []):
        address = resource_change.get("address", "<unknown>")
        actions = resource_change.get("change", {}).get("actions", [])
        if "delete" not in actions:
            continue
        if address not in ALLOWED_REPLACEMENTS:
            violations.append(f"unapproved delete/replacement: {address}")
        elif "create" not in actions:
            violations.append(
                f"approved address is being destroyed without replacement: {address}"
            )
    return violations


def _load_plan(source: str) -> dict[str, Any]:
    stream: TextIO
    if source == "-":
        stream = sys.stdin
        return json.load(stream)
    with Path(source).open(encoding="utf-8") as stream:
        return json.load(stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce the SmartRetailX baseline Terraform deletion policy."
    )
    parser.add_argument("plan_json", nargs="?", help="Terraform plan JSON path, or - for stdin")
    parser.add_argument(
        "--state-list",
        help="Path containing one Terraform state address per line; validates baseline sentinels",
    )
    args = parser.parse_args(argv)

    if args.state_list:
        addresses = {
            line.strip()
            for line in Path(args.state_list).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        violations = evaluate_state_addresses(addresses)
        if violations:
            for violation in violations:
                print(f"FAIL: {violation}", file=sys.stderr)
            return 1
        print(
            "PASS: baseline state contains all "
            f"{len(REQUIRED_BASELINE_STATE_ADDRESSES)} required sentinels."
        )
        return 0

    if not args.plan_json:
        parser.error("provide plan_json or --state-list")

    plan = _load_plan(args.plan_json)
    violations = evaluate_plan(plan)
    if violations:
        for violation in violations:
            print(f"FAIL: {violation}", file=sys.stderr)
        return 1

    approved = [
        change["address"]
        for change in plan.get("resource_changes", [])
        if "delete" in change.get("change", {}).get("actions", [])
    ]
    print(
        "PASS: no unapproved delete actions; "
        f"{len(approved)} approved replacement(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
