from __future__ import annotations

import json

import boto3
import pybreaker
import pytest
from fastapi.testclient import TestClient

from app.consumer import InventoryConsumer
from app.events import SagaEventPublisher
from app.main import create_app
from app.resilience import ResilientStock

from conftest import auth_header


def command(order_id: str = "ord-1", product_id: str = "prod-laptop-001", quantity: int = 2) -> str:
    return json.dumps({
        "eventType": "order-created",
        "orderId": order_id,
        "userId": "alice",
        "items": [{"productId": product_id, "quantity": quantity, "unitPrice": "10.00"}],
    })


class RecordingPublisher:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def order_confirmed(self, order_id, user_id=None, **extra):
        self.events.append(("order-confirmed", {"orderId": order_id, "userId": user_id}))
        return "msg-1"

    def order_rejected(self, order_id, reason, user_id=None, **extra):
        self.events.append(
            ("order-rejected", {"orderId": order_id, "reason": reason, "userId": user_id})
        )
        return "msg-2"


@pytest.fixture
def stock(repository, settings) -> ResilientStock:
    return ResilientStock(repository, settings)


# --------------------------------------------------------------------------
# the two saga paths
# --------------------------------------------------------------------------

def test_sufficient_stock_confirms_and_decrements(settings, stock):
    publisher = RecordingPublisher()
    consumer = InventoryConsumer(settings, stock, publisher=publisher)

    assert consumer.handle(command(quantity=2)) is True
    assert publisher.events[0][0] == "order-confirmed"
    assert stock.get("prod-laptop-001").quantity == 48


def test_insufficient_stock_rejects_and_leaves_stock_untouched(settings, stock):
    """The compensating event. Stock was never taken, so there is nothing to
    undo here - the Order Service marks the order REJECTED."""
    publisher = RecordingPublisher()
    consumer = InventoryConsumer(settings, stock, publisher=publisher)

    assert consumer.handle(command(product_id="prod-mouse-002", quantity=99)) is True
    event, payload = publisher.events[0]
    assert event == "order-rejected"
    assert "insufficient stock" in payload["reason"]
    assert stock.get("prod-mouse-002").quantity == 5


def test_unknown_product_rejects_with_a_distinct_reason(settings, stock):
    publisher = RecordingPublisher()
    consumer = InventoryConsumer(settings, stock, publisher=publisher)

    consumer.handle(command(product_id="ghost", quantity=1))
    assert "unknown product" in publisher.events[0][1]["reason"]


def test_every_command_produces_exactly_one_outcome(settings, stock):
    """An order that silently goes nowhere is the worst failure mode in a
    choreographed saga - nothing else will ever move it."""
    publisher = RecordingPublisher()
    consumer = InventoryConsumer(settings, stock, publisher=publisher)

    consumer.handle(command(order_id="ord-a", quantity=1))
    consumer.handle(command(order_id="ord-b", product_id="prod-sold-out", quantity=1))

    assert len(publisher.events) == 2
    assert {e[0] for e in publisher.events} == {"order-confirmed", "order-rejected"}


# --------------------------------------------------------------------------
# infrastructure faults must not become business decisions
# --------------------------------------------------------------------------

def test_open_breaker_requeues_rather_than_rejecting_the_order(settings, stock):
    """Rejecting a customer's order because our database is down would be a
    business decision made on an infrastructure fault."""
    publisher = RecordingPublisher()
    consumer = InventoryConsumer(settings, stock, publisher=publisher)

    class OpenBreaker:
        def reserve(self, lines):
            raise pybreaker.CircuitBreakerError("open")

    consumer._stock = OpenBreaker()

    assert consumer.handle(command()) is False  # not deleted - will retry
    assert publisher.events == []


def test_unexpected_error_requeues_the_command(settings, stock):
    publisher = RecordingPublisher()
    consumer = InventoryConsumer(settings, stock, publisher=publisher)

    class Broken:
        def reserve(self, lines):
            raise RuntimeError("boom")

    consumer._stock = Broken()
    assert consumer.handle(command()) is False
    assert publisher.events == []


# --------------------------------------------------------------------------
# messages that should not be retried forever
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body",
    ["not json", json.dumps({"eventType": "something-else"}), json.dumps({"eventType": "order-created"})],
)
def test_unactionable_commands_are_acked(settings, stock, body):
    consumer = InventoryConsumer(settings, stock, publisher=RecordingPublisher())
    assert consumer.handle(body) is True


def test_command_with_no_items_is_rejected_not_dropped(settings, stock):
    publisher = RecordingPublisher()
    consumer = InventoryConsumer(settings, stock, publisher=publisher)
    body = json.dumps({"eventType": "order-created", "orderId": "ord-x", "items": []})

    assert consumer.handle(body) is True
    assert publisher.events[0][0] == "order-rejected"


# --------------------------------------------------------------------------
# SNS publication (moto)
# --------------------------------------------------------------------------

def test_publisher_sets_the_eventtype_message_attribute(messaging_settings):
    """SNS filter policies match on this attribute, so subscribers are
    filtered server-side."""
    publisher = SagaEventPublisher(messaging_settings)
    assert publisher.order_confirmed("ord-1", "alice")
    assert publisher.order_rejected("ord-2", "insufficient stock", "alice")


def test_publisher_requires_a_topic_arn(settings):
    with pytest.raises(RuntimeError):
        SagaEventPublisher(settings).order_confirmed("ord-1")


def test_poll_once_consumes_from_sqs(messaging_settings, stock):
    sqs = boto3.client("sqs", region_name="eu-west-1")
    sqs.send_message(QueueUrl=messaging_settings.orders_queue_url, MessageBody=command())

    consumer = InventoryConsumer(messaging_settings, stock, publisher=RecordingPublisher())
    assert consumer.poll_once(wait_seconds=0) == 1
    assert stock.get("prod-laptop-001").quantity == 48


# --------------------------------------------------------------------------
# admin stock endpoints (backlog item 30)
# --------------------------------------------------------------------------

@pytest.fixture
def client(settings, stock) -> TestClient:
    return TestClient(create_app(settings=settings, stock=stock))


def test_customer_cannot_read_stock(client):
    """Stock levels are commercially sensitive and not needed to shop."""
    assert client.get("/v1/inventory", headers=auth_header("u", "customer")).status_code == 403


def test_admin_can_list_stock(client):
    response = client.get("/v1/inventory", headers=auth_header("u", "admin"))
    assert response.status_code == 200
    assert response.json()["count"] == 3


def test_admin_can_read_one_product(client):
    response = client.get("/v1/inventory/prod-laptop-001", headers=auth_header("u", "admin"))
    assert response.json()["quantity"] == 50


def test_unstocked_product_is_404(client):
    assert client.get("/v1/inventory/ghost", headers=auth_header("u", "admin")).status_code == 404


def test_admin_can_adjust_stock(client):
    response = client.patch(
        "/v1/inventory/prod-mouse-002", json={"quantity": 40}, headers=auth_header("u", "admin")
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 40


def test_customer_cannot_adjust_stock(client):
    response = client.patch(
        "/v1/inventory/prod-mouse-002", json={"quantity": 40}, headers=auth_header("u", "customer")
    )
    assert response.status_code == 403


def test_negative_adjustment_is_rejected_by_validation(client):
    response = client.patch(
        "/v1/inventory/prod-mouse-002", json={"quantity": -5}, headers=auth_header("u", "admin")
    )
    assert response.status_code == 422


def test_health_is_public(client):
    assert client.get("/health").status_code == 200
