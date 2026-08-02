"""Nightly stock reconciliation.

What it actually checks: orders still PENDING well past the point where the
saga should have settled them. In a choreographed saga there is no orchestrator
watching for a step that never happened, so a lost SQS message or an outcome
event that never arrived leaves an order stuck silently. This job is the
backstop that turns "silently stuck" into an alert.

It deliberately only reads and reports. Letting a cron job rewrite order
status would mean an unattended process making financial decisions at midnight
with nobody watching - the IAM policy grants Scan and Query, not UpdateItem.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import boto3
from aws_lambda_powertools import Logger, Tracer

SERVICE = "stock-reconciliation"

logger = Logger(service=SERVICE)
tracer = Tracer(service=SERVICE)

PENDING = "PENDING"

_ddb = None
_sns = None


def table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb", region_name=os.environ.get("APP_REGION", "eu-west-1"))
    return _ddb.Table(os.environ["ORDERS_TABLE_NAME"])


def sns():
    global _sns
    if _sns is None:
        _sns = boto3.client("sns", region_name=os.environ.get("APP_REGION", "eu-west-1"))
    return _sns


def stale_cutoff(minutes: int, now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) - timedelta(minutes=minutes)


def is_stale(item: dict, cutoff: datetime) -> bool:
    if item.get("status") != PENDING:
        return False
    raw = item.get("createdAt")
    if not raw:
        return False
    try:
        created = datetime.fromisoformat(raw)
    except ValueError:
        # An unparseable timestamp is itself an anomaly worth surfacing.
        return True
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created < cutoff


@tracer.capture_method
def find_stuck_orders(cutoff: datetime) -> list[dict]:
    """Scan is acceptable here and nowhere else in the system: this runs once a
    day, off the request path, and there is no index on status."""
    stuck, kwargs = [], {}
    while True:
        response = table().scan(**kwargs)
        for item in response.get("Items", []):
            if is_stale(item, cutoff):
                stuck.append(
                    {
                        "orderId": item.get("orderId"),
                        "userId": item.get("userId"),
                        "createdAt": item.get("createdAt"),
                    }
                )
        token = response.get("LastEvaluatedKey")
        if not token:
            return stuck
        kwargs["ExclusiveStartKey"] = token


def raise_alert(stuck: list[dict]) -> None:
    topic = os.environ.get("ALERTS_TOPIC_ARN")
    if not topic:
        logger.warning("no alerts topic configured, not raising")
        return
    sns().publish(
        TopicArn=topic,
        Subject=f"SmartRetailX: {len(stuck)} order(s) stuck in PENDING",
        Message=json.dumps(
            {"stuckOrders": stuck, "count": len(stuck), "action": "inspect the DLQ and saga logs"},
            indent=2,
        ),
    )


@logger.inject_lambda_context(log_event=False)
@tracer.capture_lambda_handler
def lambda_handler(event, context) -> dict:
    minutes = int(os.environ.get("STALE_PENDING_MINUTES", "30"))
    cutoff = stale_cutoff(minutes)

    stuck = find_stuck_orders(cutoff)
    if stuck:
        logger.warning("stuck orders found", extra={"count": len(stuck)})
        raise_alert(stuck)
    else:
        logger.info("reconciliation clean", extra={"cutoffMinutes": minutes})

    return {"stuck": len(stuck), "cutoffMinutes": minutes, "orders": stuck}
