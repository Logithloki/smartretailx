from __future__ import annotations

import json
from decimal import Decimal

import boto3
import pytest

from app.models import Order, OrderItem, OrderStatus
from app.services import OrderNotFound

from conftest import auth_header


def _payload(quantity: int = 2, price: str = "19.99") -> dict:
    return {"items": [{"productId": "prod-laptop-001", "quantity": quantity, "unitPrice": price}]}


# --------------------------------------------------------------------------
# health + versioning
# --------------------------------------------------------------------------

def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_orders_live_under_v1(client):
    assert client.post("/orders", json=_payload(), headers=auth_header()).status_code == 404


# --------------------------------------------------------------------------
# order creation
# --------------------------------------------------------------------------

def test_create_order_returns_pending(client):
    response = client.post("/v1/orders", json=_payload(), headers=auth_header())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == OrderStatus.PENDING.value
    assert body["orderId"].startswith("ord-")


def test_total_is_computed_server_side_not_taken_from_client(client):
    """A client-supplied total is a tampering vector; the extra field is
    ignored and the total recomputed from the line items."""
    payload = _payload(quantity=3, price="19.99")
    payload["totalAmount"] = "0.01"
    body = client.post("/v1/orders", json=payload, headers=auth_header()).json()
    assert body["totalAmount"] == "59.97"


def test_money_keeps_exact_decimal_precision(client):
    """0.1 + 0.2 must be 0.30, not 0.30000000000000004."""
    payload = {
        "items": [
            {"productId": "a", "quantity": 1, "unitPrice": "0.10"},
            {"productId": "b", "quantity": 1, "unitPrice": "0.20"},
        ]
    }
    body = client.post("/v1/orders", json=payload, headers=auth_header()).json()
    assert body["totalAmount"] == "0.30"


def test_order_is_persisted_to_dynamodb(client, repository):
    order_id = client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]
    stored = repository.get(order_id)
    assert stored is not None
    assert stored.status is OrderStatus.PENDING
    assert stored.totalAmount == Decimal("39.98")


def test_order_is_owned_by_the_token_subject_not_a_request_field(client, repository):
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header(sub="alice")
    ).json()["orderId"]
    assert repository.get(order_id).userId == "alice"


# --------------------------------------------------------------------------
# Pydantic is the validation layer (ADR-02: HTTP API v2 has no validators)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [
        {"items": []},
        {"items": [{"productId": "p", "quantity": 0, "unitPrice": "1.00"}]},
        {"items": [{"productId": "p", "quantity": -1, "unitPrice": "1.00"}]},
        {"items": [{"productId": "p", "quantity": 1, "unitPrice": "-5.00"}]},
        {"items": [{"productId": "p", "quantity": 1, "unitPrice": "0"}]},
        {"items": [{"productId": "", "quantity": 1, "unitPrice": "1.00"}]},
        {"items": [{"productId": "p", "quantity": 101, "unitPrice": "1.00"}]},
        {"wrong": "shape"},
    ],
)
def test_invalid_payloads_are_rejected_with_422(client, payload):
    assert client.post("/v1/orders", json=payload, headers=auth_header()).status_code == 422


def test_more_than_twenty_line_items_is_rejected(client):
    payload = {
        "items": [
            {"productId": f"p{i}", "quantity": 1, "unitPrice": "1.00"} for i in range(21)
        ]
    }
    assert client.post("/v1/orders", json=payload, headers=auth_header()).status_code == 422


# --------------------------------------------------------------------------
# SQS command publication
# --------------------------------------------------------------------------

def test_order_creation_publishes_a_command_to_sqs(client, settings):
    order_id = client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]

    sqs = boto3.client("sqs", region_name="eu-west-1")
    messages = sqs.receive_message(
        QueueUrl=settings.orders_queue_url,
        MaxNumberOfMessages=10,
        MessageAttributeNames=["All"],
    ).get("Messages", [])

    assert len(messages) == 1
    body = json.loads(messages[0]["Body"])
    assert body["orderId"] == order_id
    assert body["eventType"] == "order-created"
    # The attribute is what lets SNS/SQS subscribers filter without parsing.
    assert messages[0]["MessageAttributes"]["eventType"]["StringValue"] == "order-created"


def test_published_amounts_are_strings_never_floats(client, settings):
    client.post("/v1/orders", json=_payload(price="0.10"), headers=auth_header())
    sqs = boto3.client("sqs", region_name="eu-west-1")
    body = sqs.receive_message(QueueUrl=settings.orders_queue_url)["Messages"][0]["Body"]
    assert '"unitPrice": "0.10"' in body


def test_publish_without_queue_url_configured_raises(settings, repository):
    from app.events import OrderCommandPublisher

    broken = settings.model_copy(update={"orders_queue_url": ""})
    order = Order(
        userId="u", items=[OrderItem(productId="p", quantity=1, unitPrice=Decimal("1.00"))],
        totalAmount=Decimal("1.00"),
    )
    with pytest.raises(RuntimeError):
        OrderCommandPublisher(broken).publish_order_created(order)


# --------------------------------------------------------------------------
# reads (backlog item 29)
# --------------------------------------------------------------------------

def test_list_returns_only_the_callers_own_orders(client):
    client.post("/v1/orders", json=_payload(), headers=auth_header(sub="alice"))
    client.post("/v1/orders", json=_payload(), headers=auth_header(sub="alice"))
    client.post("/v1/orders", json=_payload(), headers=auth_header(sub="bob"))

    alice = client.get("/v1/orders", headers=auth_header(sub="alice")).json()
    bob = client.get("/v1/orders", headers=auth_header(sub="bob")).json()

    assert alice["count"] == 2
    assert bob["count"] == 1
    assert all(o["userId"] == "alice" for o in alice["orders"])


def test_get_own_order(client):
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header(sub="alice")
    ).json()["orderId"]
    assert client.get(f"/v1/orders/{order_id}", headers=auth_header(sub="alice")).status_code == 200


def test_another_users_order_is_404_not_403(client):
    """403 would confirm the id exists. 404 leaks nothing."""
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header(sub="alice")
    ).json()["orderId"]
    response = client.get(f"/v1/orders/{order_id}", headers=auth_header(sub="bob"))
    assert response.status_code == 404


def test_admin_may_read_any_order(client):
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header(sub="alice")
    ).json()["orderId"]
    response = client.get(
        f"/v1/orders/{order_id}", headers=auth_header("bob", "customer", "admin")
    )
    assert response.status_code == 200


def test_unknown_order_is_404(client):
    assert client.get("/v1/orders/ord-doesnotexist", headers=auth_header()).status_code == 404


def test_list_limit_is_validated(client):
    assert client.get("/v1/orders?limit=0", headers=auth_header()).status_code == 422
    assert client.get("/v1/orders?limit=101", headers=auth_header()).status_code == 422


# --------------------------------------------------------------------------
# status transitions (used by the saga in Week 3)
# --------------------------------------------------------------------------

def test_set_status_updates_and_records_a_reason(client, repository):
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header()
    ).json()["orderId"]

    updated = repository.set_status(order_id, OrderStatus.REJECTED, reason="insufficient stock")
    assert updated.status is OrderStatus.REJECTED
    assert updated.statusReason == "insufficient stock"
    assert repository.get(order_id).status is OrderStatus.REJECTED


def test_set_status_on_a_missing_order_raises_rather_than_creating_one(repository):
    """update_item would upsert by default - the condition expression stops a
    stray event from conjuring an order that was never placed."""
    with pytest.raises(OrderNotFound):
        repository.set_status("ord-ghost", OrderStatus.CONFIRMED)
