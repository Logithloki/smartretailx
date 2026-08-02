from __future__ import annotations

import json

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

import handler as h

TABLE = "test-ws-connections"
CALLBACK = "https://abc.execute-api.eu-west-1.amazonaws.com/prod"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("APP_REGION", "eu-west-1")
    monkeypatch.setenv("WS_CONNECTIONS_TABLE", TABLE)
    monkeypatch.setenv("WS_CALLBACK_ENDPOINT", CALLBACK)
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


class FakeApiGw:
    """Stand-in for apigatewaymanagementapi - moto has no coverage for the
    ManageConnections surface. The tests configure per-connection responses:
    either a delivered ok, or an exception."""

    def __init__(self):
        self.responses: dict[str, object] = {}
        self.sent: list[tuple[str, bytes]] = []

    def post_to_connection(self, ConnectionId: str, Data: bytes):
        setup = self.responses.get(ConnectionId, "ok")
        if isinstance(setup, Exception):
            raise setup
        self.sent.append((ConnectionId, Data))
        return {}


def gone(connection_id: str) -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": "GoneException", "Message": "connection is gone"},
            "ResponseMetadata": {"HTTPStatusCode": 410},
        },
        operation_name="PostToConnection",
    )


def server_error(connection_id: str) -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": "InternalServerError", "Message": "boom"},
            "ResponseMetadata": {"HTTPStatusCode": 500},
        },
        operation_name="PostToConnection",
    )


def bad_request(connection_id: str) -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": "BadRequestException", "Message": "malformed"},
            "ResponseMetadata": {"HTTPStatusCode": 400},
        },
        operation_name="PostToConnection",
    )


def status_change_event(user_id: str = "user-1", status: str = "CONFIRMED") -> dict:
    """Shape of an EventBridge event whose detail is a DDB stream record."""
    return {
        "source": "smartretailx.orders",
        "detail-type": "order.status-changed",
        "detail": {
            "eventName": "MODIFY",
            "dynamodb": {
                "NewImage": {
                    "orderId": {"S": "ord-42"},
                    "userId": {"S": user_id},
                    "status": {"S": status},
                }
            },
        },
    }


# --------------------------------------------------------------------------
# happy path
# --------------------------------------------------------------------------


def test_pushes_to_all_of_the_users_connections(connections_table, monkeypatch):
    connections_table.put_item(Item={"connectionId": "c1", "userId": "user-1", "ttl": 999})
    connections_table.put_item(Item={"connectionId": "c2", "userId": "user-1", "ttl": 999})
    connections_table.put_item(Item={"connectionId": "c3", "userId": "other", "ttl": 999})

    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(status_change_event(), None)

    assert result["pushed"] == 2
    sent_ids = {cid for cid, _ in api.sent}
    assert sent_ids == {"c1", "c2"}
    for _, data in api.sent:
        payload = json.loads(data)
        assert payload["orderId"] == "ord-42"
        assert payload["status"] == "CONFIRMED"
        assert payload["type"] == "order.status-changed"


def test_zero_connections_is_not_an_error(connections_table, monkeypatch):
    """Common case: order confirmed while the customer is not on the site.
    The email path still fires; the WS path is best-effort."""
    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(status_change_event(user_id="ghost"), None)
    assert result["pushed"] == 0
    assert api.sent == []


# --------------------------------------------------------------------------
# error handling
# --------------------------------------------------------------------------


def test_stale_connection_is_pruned_inline(connections_table, monkeypatch):
    """A GoneException (410) means the client is already disconnected.
    Delete the row inline so it does not accumulate."""
    connections_table.put_item(Item={"connectionId": "stale", "userId": "user-1", "ttl": 999})

    api = FakeApiGw()
    api.responses["stale"] = gone("stale")
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(status_change_event(), None)

    assert result["counts"]["stale"] == 1
    assert "Item" not in connections_table.get_item(Key={"connectionId": "stale"})


def test_partial_failure_still_delivers_to_healthy_connections(connections_table, monkeypatch):
    """One bad connection must not block the fan-out to the rest."""
    connections_table.put_item(Item={"connectionId": "good", "userId": "user-1", "ttl": 999})
    connections_table.put_item(Item={"connectionId": "stale", "userId": "user-1", "ttl": 999})

    api = FakeApiGw()
    api.responses["stale"] = gone("stale")
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(status_change_event(), None)

    assert result["counts"] == {"delivered": 1, "stale": 1, "skipped": 0}


def test_5xx_reraises_so_eventbridge_retries(connections_table, monkeypatch):
    """Transient server errors should NOT be swallowed - EventBridge's
    retry policy is the safety net."""
    connections_table.put_item(Item={"connectionId": "c1", "userId": "user-1", "ttl": 999})

    api = FakeApiGw()
    api.responses["c1"] = server_error("c1")
    monkeypatch.setattr(h, "_api_client", lambda: api)

    with pytest.raises(ClientError):
        h.lambda_handler(status_change_event(), None)


def test_4xx_other_than_410_is_logged_and_skipped(connections_table, monkeypatch):
    """A malformed payload complaint is a bug in this Lambda, not a stale
    connection. Log and move on."""
    connections_table.put_item(Item={"connectionId": "c1", "userId": "user-1", "ttl": 999})
    connections_table.put_item(Item={"connectionId": "c2", "userId": "user-1", "ttl": 999})

    api = FakeApiGw()
    api.responses["c1"] = bad_request("c1")
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(status_change_event(), None)
    assert result["counts"]["skipped"] == 1
    assert result["counts"]["delivered"] == 1


# --------------------------------------------------------------------------
# event parsing
# --------------------------------------------------------------------------


def test_event_without_a_new_image_is_ignored(connections_table, monkeypatch):
    monkeypatch.setattr(h, "_api_client", lambda: FakeApiGw())
    result = h.lambda_handler({"detail": {}}, None)
    assert result["pushed"] == 0


def test_extract_returns_none_when_status_missing():
    event = status_change_event()
    del event["detail"]["dynamodb"]["NewImage"]["status"]
    assert h._extract_status_change(event) is None
