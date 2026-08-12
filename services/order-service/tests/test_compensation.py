from __future__ import annotations

import json
import threading

import boto3
import pytest

from app.compensation import CompensationConsumer, unwrap_sns_envelope
from app.models import FulfilmentStatus, OrderStatus

from conftest import auth_header


def _payload() -> dict:
    return {"items": [{"productId": "prod-laptop-001", "quantity": 1}]}


def _place_order(client) -> str:
    return client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]


def _sns_envelope(inner: dict) -> str:
    """What SQS actually receives from SNS without raw message delivery."""
    return json.dumps({
        "Type": "Notification",
        "TopicArn": "arn:aws:sns:eu-west-1:000000000000:smartretailx-order-confirmed",
        "Message": json.dumps(inner),
    })


# --------------------------------------------------------------------------
# envelope handling
# --------------------------------------------------------------------------

def test_unwraps_the_sns_notification_envelope():
    inner = {"eventType": "order-rejected", "orderId": "ord-1"}
    assert unwrap_sns_envelope(_sns_envelope(inner)) == inner


def test_accepts_raw_message_delivery_too():
    """Raw delivery is a subscription setting; the consumer must not depend
    on which way it is configured."""
    inner = {"eventType": "order-rejected", "orderId": "ord-1"}
    assert unwrap_sns_envelope(json.dumps(inner)) == inner


# --------------------------------------------------------------------------
# the two saga outcomes
# --------------------------------------------------------------------------

def test_order_rejected_compensates_the_order(client, settings, repository):
    order_id = _place_order(client)
    consumer = CompensationConsumer(settings, repository=repository)

    handled = consumer.handle(_sns_envelope({
        "eventType": "order-rejected",
        "orderId": order_id,
        "reason": "insufficient stock for prod-laptop-001",
    }))

    assert handled is True
    order = repository.get(order_id)
    assert order.status is OrderStatus.REJECTED
    assert order.statusReason == "insufficient stock for prod-laptop-001"


def test_order_confirmed_completes_the_order(client, settings, repository):
    order_id = _place_order(client)
    consumer = CompensationConsumer(settings, repository=repository)

    consumer.handle(_sns_envelope({"eventType": "order-confirmed", "orderId": order_id}))

    assert repository.get(order_id).status is OrderStatus.CONFIRMED


def test_cancel_pending_completion_transitions_to_cancelled_once(client, settings, repository):
    order_id = _place_order(client)
    repository.set_status(order_id, OrderStatus.CONFIRMED, only_if_pending=True)
    repository.request_cancellation(order_id, "user-1", "corr-cancel")
    consumer = CompensationConsumer(settings, repository=repository)

    assert consumer.handle(_sns_envelope({"eventType": "order-cancelled", "orderId": order_id})) is True
    assert repository.get(order_id).status is OrderStatus.CANCELLED
    assert consumer.handle(_sns_envelope({"eventType": "order-cancelled", "orderId": order_id})) is True
    assert repository.get(order_id).status is OrderStatus.CANCELLED


@pytest.mark.parametrize("stale_status", [
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.REJECTED,
])
def test_late_cancel_completion_cannot_overwrite_stale_order(client, settings, repository, stale_status):
    order_id = _place_order(client)
    if stale_status is not OrderStatus.PENDING:
        repository.set_status(order_id, stale_status, only_if_pending=True)
    consumer = CompensationConsumer(settings, repository=repository)

    assert consumer.handle(_sns_envelope({"eventType": "order-cancelled", "orderId": order_id})) is True
    assert repository.get(order_id).status is stale_status


def test_late_cancel_completion_cannot_overwrite_dispatched_order(client, settings, repository):
    order_id = _place_order(client)
    repository.set_status(order_id, OrderStatus.CONFIRMED, only_if_pending=True)
    repository.set_fulfilment(order_id, FulfilmentStatus.NOT_STARTED, FulfilmentStatus.PACKING)
    repository.set_fulfilment(order_id, FulfilmentStatus.PACKING, FulfilmentStatus.DISPATCHED)
    consumer = CompensationConsumer(settings, repository=repository)

    assert consumer.handle(_sns_envelope({"eventType": "order-cancelled", "orderId": order_id})) is True
    order = repository.get(order_id)
    assert order.status is OrderStatus.CONFIRMED
    assert order.fulfilmentStatus is FulfilmentStatus.DISPATCHED


# --------------------------------------------------------------------------
# at-least-once delivery
# --------------------------------------------------------------------------

def test_duplicate_delivery_is_acked_not_reprocessed(client, settings, repository):
    """SQS is at-least-once, so duplicates are normal traffic."""
    order_id = _place_order(client)
    consumer = CompensationConsumer(settings, repository=repository)
    event = _sns_envelope({"eventType": "order-confirmed", "orderId": order_id})

    assert consumer.handle(event) is True
    assert consumer.handle(event) is True
    assert repository.get(order_id).status is OrderStatus.CONFIRMED


def test_a_late_rejection_cannot_undo_a_confirmed_order(client, settings, repository):
    """Out-of-order delivery must not drag a terminal order backwards."""
    order_id = _place_order(client)
    consumer = CompensationConsumer(settings, repository=repository)

    consumer.handle(_sns_envelope({"eventType": "order-confirmed", "orderId": order_id}))
    consumer.handle(_sns_envelope({"eventType": "order-rejected", "orderId": order_id}))

    assert repository.get(order_id).status is OrderStatus.CONFIRMED


# --------------------------------------------------------------------------
# messages the consumer should not retry forever
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body",
    [
        "not json at all",
        json.dumps({"eventType": "something-else", "orderId": "ord-1"}),
        json.dumps({"eventType": "order-rejected"}),  # no orderId
    ],
)
def test_unactionable_messages_are_acked(settings, repository, body):
    """Redelivering these until they hit the DLQ is noise, not signal."""
    assert CompensationConsumer(settings, repository=repository).handle(body) is True


def test_event_for_an_unknown_order_is_retried_not_acked(settings, repository):
    """This one IS a real anomaly - leave it for redelivery and the DLQ."""
    consumer = CompensationConsumer(settings, repository=repository)
    event = _sns_envelope({"eventType": "order-confirmed", "orderId": "ord-ghost"})
    assert consumer.handle(event) is False


# --------------------------------------------------------------------------
# polling loop
# --------------------------------------------------------------------------

def test_poll_once_consumes_and_deletes(client, settings, repository):
    order_id = _place_order(client)
    sqs = boto3.client("sqs", region_name="eu-west-1")
    sqs.send_message(
        QueueUrl=settings.order_events_queue_url,
        MessageBody=_sns_envelope({"eventType": "order-confirmed", "orderId": order_id}),
    )

    consumer = CompensationConsumer(settings, repository=repository)
    assert consumer.poll_once(wait_seconds=0) == 1
    assert repository.get(order_id).status is OrderStatus.CONFIRMED

    remaining = sqs.get_queue_attributes(
        QueueUrl=settings.order_events_queue_url,
        AttributeNames=["ApproximateNumberOfMessages"],
    )["Attributes"]["ApproximateNumberOfMessages"]
    assert remaining == "0"


def test_poll_once_is_a_noop_without_a_queue_url(settings, repository):
    broken = settings.model_copy(update={"order_events_queue_url": ""})
    assert CompensationConsumer(broken, repository=repository).poll_once(wait_seconds=0) == 0


def test_run_forever_exits_when_stopped(settings, repository):
    consumer = CompensationConsumer(settings, repository=repository)
    stop = threading.Event()
    thread = threading.Thread(target=consumer.run_forever, args=(stop,), kwargs={"wait_seconds": 0})
    thread.start()
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
