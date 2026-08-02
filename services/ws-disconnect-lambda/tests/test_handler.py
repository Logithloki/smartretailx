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
        table.put_item(Item={"connectionId": "conn-1", "userId": "u1", "ttl": 999})
        yield table


def disc_event(connection_id: str = "conn-1") -> dict:
    return {"requestContext": {"connectionId": connection_id}}


def test_disconnect_removes_the_row(connections_table):
    result = h.lambda_handler(disc_event(), None)
    assert result["statusCode"] == 200
    assert "Item" not in connections_table.get_item(Key={"connectionId": "conn-1"})


def test_disconnect_is_idempotent_on_missing_row(connections_table):
    """TTL might already have swept the row; duplicate disconnect events
    happen too. DeleteItem is idempotent - result is still 200."""
    result = h.lambda_handler(disc_event("never-existed"), None)
    assert result["statusCode"] == 200


def test_missing_connection_id_logs_and_returns_200(connections_table):
    """API Gateway doesn't read the disconnect response body; return 200 so
    the platform sees the invocation as clean and the fault appears in logs."""
    result = h.lambda_handler({"requestContext": {}}, None)
    assert result["statusCode"] == 200
