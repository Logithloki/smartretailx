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
            AttributeDefinitions=[
                {"AttributeName": "connectionId", "AttributeType": "S"},
                {"AttributeName": "userId", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "userId-index",
                    "KeySchema": [{"AttributeName": "userId", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "KEYS_ONLY"},
                }
            ],
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
                    "correlationId": {"S": "correlation-42"},
                }
            },
        },
    }


def price_refresh_event(product_ids: list[str] | None = None) -> dict:
    """Raw promotion-table stream record forwarded by the promotion Pipe."""
    return {
        "source": "smartretailx.promotions",
        "detail-type": "promotion.price-refresh",
        "detail": {
            "eventName": "MODIFY",
            "dynamodb": {
                "NewImage": {
                    "promotionId": {"S": "promo-10"},
                    "productIds": {"L": [{"S": product_id} for product_id in (["prod-1"] if product_ids is None else product_ids)]},
                    "lifecycleVersion": {"N": "1"},
                    "priceEventPending": {"S": "true"},
                }
            },
        },
    }


def product_price_refresh_event() -> dict:
    """Raw products-table stream record forwarded by the product Pipe."""
    return {
        "source": "smartretailx.products",
        "detail-type": "product.price-refresh",
        "detail": {
            "eventName": "MODIFY",
            "dynamodb": {
                "NewImage": {
                    "productId": {"S": "prod-9"},
                    "price": {"N": "999.99"},
                    "priceEventVersion": {"N": "4"},
                    "priceEventPending": {"S": "true"},
                }
            },
        },
    }


def fulfilment_event(user_id: str = "user-1", fulfilment_status: str = "PACKING") -> dict:
    return {
        "source": "smartretailx.orders",
        "detail-type": "fulfilment-status-changed",
        "detail": {
            "eventType": "fulfilment-status-changed",
            "eventId": "fulfilment-status-changed#ord-42#PACKING",
            "aggregateId": "ord-42",
            "correlationId": "correlation-42",
            "payload": {
                "orderId": "ord-42", "userId": user_id, "fulfilmentStatus": fulfilment_status,
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
        assert payload["correlationId"] == "correlation-42"


def test_connection_lookup_uses_user_index_not_scan(monkeypatch):
    class QueryOnlyTable:
        def __init__(self):
            self.query_calls: list[dict] = []

        def scan(self, **kwargs):
            raise AssertionError("connection lookup must not scan across customers")

        def query(self, **kwargs):
            self.query_calls.append(kwargs)
            return {"Items": [{"connectionId": "owned-connection"}]}

    table = QueryOnlyTable()
    monkeypatch.setattr(h, "_table", lambda: table)

    assert h._connections_for("user-1") == ["owned-connection"]
    assert table.query_calls[0]["IndexName"] == "userId-index"


def test_public_price_refresh_broadcasts_only_safe_fields_to_every_connection(connections_table, monkeypatch):
    connections_table.put_item(Item={"connectionId": "alice", "userId": "alice", "ttl": 999})
    connections_table.put_item(Item={"connectionId": "bob", "userId": "bob", "ttl": 999})
    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(price_refresh_event(["prod-1", "prod-2"]), None)

    assert result["pushed"] == 2
    assert {connection_id for connection_id, _ in api.sent} == {"alice", "bob"}
    for _, data in api.sent:
        assert json.loads(data) == {
            "type": "catalogue.price-refresh",
            "productIds": ["prod-1", "prod-2"],
            "revision": 1,
        }


def test_product_price_refresh_uses_the_same_safe_public_payload(connections_table, monkeypatch):
    connections_table.put_item(Item={"connectionId": "shopper", "userId": "alice", "ttl": 999})
    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(product_price_refresh_event(), None)

    assert result["public"] is True
    assert json.loads(api.sent[0][1]) == {
        "type": "catalogue.price-refresh",
        "productIds": ["prod-9"],
        "revision": 4,
    }
    assert "999.99" not in api.sent[0][1].decode("utf-8")


def test_product_price_refresh_rejects_private_fields(connections_table, monkeypatch):
    event = product_price_refresh_event()
    event["detail"]["dynamodb"]["NewImage"]["customerId"] = {"S": "private"}
    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(event, None)

    assert result["pushed"] == 0
    assert api.sent == []


def test_category_promotion_broadcasts_empty_ids_as_a_full_catalogue_refresh(connections_table, monkeypatch):
    connections_table.put_item(Item={"connectionId": "shopper", "userId": "alice", "ttl": 999})
    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(price_refresh_event([]), None)

    assert result["public"] is True
    assert json.loads(api.sent[0][1]) == {
        "type": "catalogue.price-refresh",
        "productIds": [],
        "revision": 1,
    }


def test_public_connection_scan_is_paginated(monkeypatch):
    class PagedTable:
        def __init__(self):
            self.calls = []

        def scan(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {"Items": [{"connectionId": "first"}], "LastEvaluatedKey": {"connectionId": "first"}}
            return {"Items": [{"connectionId": "second"}]}

    table = PagedTable()
    monkeypatch.setattr(h, "_table", lambda: table)
    assert h._all_connections() == ["first", "second"]
    assert table.calls[1]["ExclusiveStartKey"] == {"connectionId": "first"}


def test_public_event_rejects_private_fields_before_broadcast(connections_table, monkeypatch):
    event = price_refresh_event()
    event["detail"]["dynamodb"]["NewImage"]["userId"] = {"S": "alice"}
    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(event, None)
    assert result["pushed"] == 0
    assert api.sent == []


def test_zero_connections_is_not_an_error(connections_table, monkeypatch):
    """Common case: order confirmed while the customer is not on the site.
    The email path still fires; the WS path is best-effort."""
    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(status_change_event(user_id="ghost"), None)
    assert result["pushed"] == 0
    assert api.sent == []


def test_fulfilment_event_uses_the_same_private_user_index_branch(connections_table, monkeypatch):
    connections_table.put_item(Item={"connectionId": "owned", "userId": "user-1", "ttl": 999})
    connections_table.put_item(Item={"connectionId": "other", "userId": "other", "ttl": 999})
    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(fulfilment_event(), None)

    assert result["pushed"] == 1
    assert [connection_id for connection_id, _ in api.sent] == ["owned"]
    assert json.loads(api.sent[0][1]) == {
        "type": "order.fulfilment-status-changed", "orderId": "ord-42",
        "fulfilmentStatus": "PACKING", "correlationId": "correlation-42",
    }


def test_cancelled_status_is_pushed_only_to_the_owning_user(connections_table, monkeypatch):
    connections_table.put_item(Item={"connectionId": "owned", "userId": "user-1", "ttl": 999})
    connections_table.put_item(Item={"connectionId": "other", "userId": "other", "ttl": 999})
    api = FakeApiGw()
    monkeypatch.setattr(h, "_api_client", lambda: api)

    result = h.lambda_handler(status_change_event(status="CANCELLED"), None)

    assert result["pushed"] == 1
    assert [connection_id for connection_id, _ in api.sent] == ["owned"]
    assert json.loads(api.sent[0][1]) == {
        "type": "order.status-changed",
        "orderId": "ord-42",
        "status": "CANCELLED",
        "correlationId": "correlation-42",
    }


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
