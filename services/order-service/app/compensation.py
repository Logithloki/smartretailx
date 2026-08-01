"""Saga compensation receiver (ADR-06: choreography, not orchestration).

The Order Service publishes a command and then forgets about it. Inventory
decides the outcome and announces it on SNS; this consumer applies that outcome
to the order record. There is no central orchestrator - each service reacts to
what it hears, which is what makes this choreography.

Two events matter here:
  order-confirmed  -> PENDING becomes CONFIRMED
  order-rejected   -> PENDING becomes REJECTED  (the compensating action)

Note on the subscription filter: the guide's Week 2 text filters on
order-rejected alone, because at that point the publisher did not exist yet.
Nothing else in the design moves an order to CONFIRMED, so the queue subscribes
to both event types - otherwise the Week 3 Day 5 saga demo cannot complete.
"""

from __future__ import annotations

import json
import logging
import threading

import boto3

from .models import OrderStatus
from .services import OrderNotFound, OrderNotPending, OrderRepository

logger = logging.getLogger(__name__)

STATUS_FOR_EVENT = {
    "order-confirmed": OrderStatus.CONFIRMED,
    "order-rejected": OrderStatus.REJECTED,
}


def unwrap_sns_envelope(raw_body: str) -> dict:
    """SQS queues subscribed to SNS receive the notification envelope unless
    raw message delivery is enabled. Accept both shapes so the consumer does
    not depend on that setting."""
    payload = json.loads(raw_body)
    if isinstance(payload, dict) and payload.get("Type") == "Notification" and "Message" in payload:
        inner = payload["Message"]
        return json.loads(inner) if isinstance(inner, str) else inner
    return payload


class CompensationConsumer:
    def __init__(self, settings, repository: OrderRepository | None = None):
        self._settings = settings
        self._repo = repository or OrderRepository(settings)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("sqs", **self._settings.boto_kwargs())
        return self._client

    def handle(self, raw_body: str) -> bool:
        """Apply one event. Returns True if the message should be deleted.

        Returning True for events we cannot act on is deliberate: a malformed
        or unknown message that is never deleted would be redelivered until it
        reaches the DLQ, which is noise rather than signal.
        """
        try:
            event = unwrap_sns_envelope(raw_body)
        except (json.JSONDecodeError, TypeError):
            logger.warning("discarding unparseable message")
            return True

        event_type = event.get("eventType")
        order_id = event.get("orderId")

        if event_type not in STATUS_FOR_EVENT:
            logger.debug("ignoring event", extra={"eventType": event_type})
            return True
        if not order_id:
            logger.warning("event has no orderId", extra={"eventType": event_type})
            return True

        target = STATUS_FOR_EVENT[event_type]
        try:
            order = self._repo.set_status(
                order_id,
                target,
                reason=event.get("reason"),
                only_if_pending=True,
            )
        except OrderNotPending:
            # Duplicate or late delivery. SQS is at-least-once, so this is
            # expected traffic, not an error - ack it and move on.
            logger.info("order already terminal, ignoring", extra={"orderId": order_id})
            return True
        except OrderNotFound:
            # The order genuinely is not there. Do NOT delete: let it retry and
            # ultimately land on the DLQ where it can be inspected.
            logger.error("event for unknown order", extra={"orderId": order_id})
            return False

        logger.info(
            "saga outcome applied",
            extra={"orderId": order_id, "status": order.status.value, "eventType": event_type},
        )
        return True

    def poll_once(self, wait_seconds: int = 1, max_messages: int = 10) -> int:
        queue_url = self._settings.order_events_queue_url
        if not queue_url:
            return 0

        response = self.client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
            MessageAttributeNames=["All"],
        )
        messages = response.get("Messages", [])
        handled = 0
        for message in messages:
            if self.handle(message["Body"]):
                self.client.delete_message(
                    QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
                )
                handled += 1
        return handled

    def run_forever(self, stop: threading.Event, wait_seconds: int = 20) -> None:
        """Long-poll loop. 20s waits mean an idle consumer makes 3 calls a
        minute instead of hammering the queue."""
        logger.info("compensation consumer started")
        while not stop.is_set():
            try:
                self.poll_once(wait_seconds=wait_seconds)
            except Exception:
                # A consumer thread that dies silently is worse than a noisy
                # one; log and keep polling.
                logger.exception("compensation poll failed")
                stop.wait(5)
        logger.info("compensation consumer stopped")
