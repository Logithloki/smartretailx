from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

import handler as h

TABLE = "test-ws-connections"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("APP_REGION", "eu-west-1")
    monkeypatch.setenv("WS_CONNECTIONS_TABLE", TABLE)
    h._reset()
    yield
    h._reset()


@pytest.fixture
def connections_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-west-1")
        table = ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "connectionId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "connectionId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield table


def connect_event(connection_id: str = "conn-1", user_id: str | None = "user-1") -> dict:
    ctx = {"connectionId": connection_id}
    if user_id is not None:
        ctx["authorizer"] = {"userId": user_id}
    return {"requestContext": ctx}


def test_connect_records_the_pair_in_the_table(connections_table):
    result = h.lambda_handler(connect_event(), None)
    assert result["statusCode"] == 200

    item = connections_table.get_item(Key={"connectionId": "conn-1"})["Item"]
    assert item["userId"] == "user-1"
    assert item["ttl"] > item["connectedAt"]


def test_missing_userid_is_rejected_401(connections_table):
    """Authorizer approving without a sub is a misconfiguration; refuse to
    record an unattributable connection or the push path breaks silently."""
    result = h.lambda_handler(connect_event(user_id=None), None)
    assert result["statusCode"] == 401


def test_missing_connection_id_returns_500(connections_table):
    """API Gateway always supplies connectionId - this is a should-never-happen
    that fails loudly rather than swallowing the fault."""
    result = h.lambda_handler({"requestContext": {"authorizer": {"userId": "u1"}}}, None)
    assert result["statusCode"] == 500


def test_ttl_is_a_full_day_ahead(connections_table):
    h.lambda_handler(connect_event(), None)
    item = connections_table.get_item(Key={"connectionId": "conn-1"})["Item"]
    assert (item["ttl"] - item["connectedAt"]) == 24 * 60 * 60
