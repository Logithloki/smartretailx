from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

import handler as h

ORDERS_TABLE = "test-orders"


class Context:
    function_name = "smartretailx-stock-reconciliation"
    memory_limit_in_mb = 256
    invoked_function_arn = "arn:aws:lambda:eu-west-1:000000000000:function:recon"
    aws_request_id = "req-1"

    @staticmethod
    def get_remaining_time_in_millis() -> int:
        return 60_000


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "eu-west-1",
        "APP_REGION": "eu-west-1",
        "ORDERS_TABLE_NAME": ORDERS_TABLE,
        "STALE_PENDING_MINUTES": "30",
        "POWERTOOLS_TRACE_DISABLED": "true",
    }.items():
        monkeypatch.setenv(key, value)
    h._ddb = None
    h._sns = None
    yield
    h._ddb = None
    h._sns = None


@pytest.fixture
def aws():
    with mock_aws():
        yield


@pytest.fixture
def orders(aws):
    ddb = boto3.resource("dynamodb", region_name="eu-west-1")
    return ddb.create_table(
        TableName=ORDERS_TABLE,
        KeySchema=[{"AttributeName": "orderId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "orderId", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def alerts(aws, monkeypatch):
    sns = boto3.client("sns", region_name="eu-west-1")
    arn = sns.create_topic(Name="test-alerts")["TopicArn"]
    monkeypatch.setenv("ALERTS_TOPIC_ARN", arn)
    return arn


def ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def put(table, order_id: str, status: str, created: str) -> None:
    table.put_item(
        Item={"orderId": order_id, "userId": "u1", "status": status, "createdAt": created}
    )


# --------------------------------------------------------------------------
# staleness rule
# --------------------------------------------------------------------------

def test_settled_orders_are_never_stale():
    cutoff = h.stale_cutoff(30)
    for status in ("CONFIRMED", "REJECTED"):
        assert h.is_stale({"status": status, "createdAt": ago(600)}, cutoff) is False


def test_recent_pending_order_is_not_stale():
    """An order placed a minute ago is mid-saga, not stuck."""
    assert h.is_stale({"status": "PENDING", "createdAt": ago(1)}, h.stale_cutoff(30)) is False


def test_old_pending_order_is_stale():
    assert h.is_stale({"status": "PENDING", "createdAt": ago(120)}, h.stale_cutoff(30)) is True


def test_unparseable_timestamp_is_treated_as_an_anomaly():
    assert h.is_stale({"status": "PENDING", "createdAt": "not-a-date"}, h.stale_cutoff(30)) is True


def test_naive_timestamp_does_not_crash_the_comparison():
    """A stored timestamp without a timezone must not raise on compare."""
    naive = (datetime.now(timezone.utc) - timedelta(minutes=120)).replace(tzinfo=None).isoformat()
    assert h.is_stale({"status": "PENDING", "createdAt": naive}, h.stale_cutoff(30)) is True


def test_missing_timestamp_is_not_stale():
    assert h.is_stale({"status": "PENDING"}, h.stale_cutoff(30)) is False


# --------------------------------------------------------------------------
# scanning
# --------------------------------------------------------------------------

def test_finds_only_the_stuck_orders(orders):
    put(orders, "ord-fresh", "PENDING", ago(2))
    put(orders, "ord-stuck", "PENDING", ago(90))
    put(orders, "ord-done", "CONFIRMED", ago(90))

    found = h.find_stuck_orders(h.stale_cutoff(30))
    assert [o["orderId"] for o in found] == ["ord-stuck"]


def test_clean_run_finds_nothing(orders):
    put(orders, "ord-done", "CONFIRMED", ago(90))
    assert h.find_stuck_orders(h.stale_cutoff(30)) == []


# --------------------------------------------------------------------------
# handler
# --------------------------------------------------------------------------

def test_handler_reports_zero_when_healthy(orders, alerts):
    put(orders, "ord-done", "CONFIRMED", ago(90))
    assert h.lambda_handler({}, Context())["stuck"] == 0


def test_handler_alerts_when_orders_are_stuck(orders, alerts):
    put(orders, "ord-stuck", "PENDING", ago(90))
    result = h.lambda_handler({}, Context())
    assert result["stuck"] == 1
    assert result["orders"][0]["orderId"] == "ord-stuck"


def test_missing_alerts_topic_does_not_crash_the_run(orders, monkeypatch):
    """Losing the alert is bad; crashing the nightly job is worse."""
    monkeypatch.delenv("ALERTS_TOPIC_ARN", raising=False)
    put(orders, "ord-stuck", "PENDING", ago(90))
    assert h.lambda_handler({}, Context())["stuck"] == 1


def test_cutoff_is_configurable(orders, alerts, monkeypatch):
    monkeypatch.setenv("STALE_PENDING_MINUTES", "180")
    put(orders, "ord-stuck", "PENDING", ago(90))
    # 90 minutes old is not yet stale against a 180-minute cutoff.
    assert h.lambda_handler({}, Context())["stuck"] == 0
