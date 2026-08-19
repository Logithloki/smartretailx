"""Order command consumer - the middle of the saga.

Receives "order-created" from SQS, tries to reserve the stock, and announces
the outcome. Both outcomes are terminal and both are published; an order that
silently goes nowhere is the worst possible failure mode in a choreographed
saga because nothing else will ever move it.
"""

from __future__ import annotations

import json
import logging
import threading

import boto3
import pybreaker
from pydantic import ValidationError
from srx_common import EventEnvelope, set_correlation_id

from .events import InventoryOutboxPublisher, SagaEventPublisher
from .models import ReservationLine

logger = logging.getLogger(__name__)


class InventoryConsumer:
    def __init__(self, settings, stock, publisher: SagaEventPublisher | None = None):
        self._settings = settings
        self._stock = stock
        self._publisher = publisher or SagaEventPublisher(settings)
        self._outbox = InventoryOutboxPublisher(stock, self._publisher)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("sqs", **self._settings.boto_kwargs())
        return self._client

    @staticmethod
    def _lines(event: dict) -> list[ReservationLine]:
        return [
            ReservationLine(productId=item["productId"], quantity=int(item["quantity"]))
            for item in event.get("items", [])
            if item.get("productId")
        ]

    def handle(self, raw_body: str, event_id: str | None = None) -> bool:
        """Process one command. Returns True if the message should be deleted.

        Returning False leaves the message for redelivery and, after
        maxReceiveCount, the DLQ - which is where anything we could not decide
        belongs.
        """
        try:
            event = EventEnvelope.model_validate_json(raw_body)
        except (json.JSONDecodeError, ValidationError):
            logger.warning("invalid command contract; leaving for DLQ")
            return False

        if event.eventType == "order-cancel-requested":
            cancel_email = event.payload.get("userEmail") if event.payload else None
            try:
                result = self._stock.release_reservation(event.aggregateId, event.correlationId, user_email=cancel_email)
            except pybreaker.CircuitBreakerError:
                return False
            except Exception:
                logger.exception("cancellation release failed", extra={"orderId": event.aggregateId})
                return False
            self._outbox.publish_once()
            logger.info("cancellation release handled", extra={"orderId": event.aggregateId, "duplicate": result.duplicate})
            return True

        if event.eventType != "order-created":
            logger.debug("ignoring event", extra={"eventType": event.eventType})
            return True

        payload = event.payload
        order_id = event.aggregateId
        set_correlation_id(event.correlationId)

        user_id = payload.get("userId")
        # Carried through unchanged so the notification Lambda has a recipient.
        passthrough = {
            "userEmail": payload.get("userEmail"),
            "correlationId": event.correlationId,
            "traceId": event.traceId,
            "loadTest": bool(payload.get("loadTest", False)),
        }
        lines = self._lines(payload)
        event_id = event_id or event.eventId

        try:
            result = self._stock.process_order(
                event_id, order_id, user_id, lines, passthrough
            )
        except pybreaker.CircuitBreakerError:
            # The database is known-bad. Do not reject the order - that would
            # be a business decision made on an infrastructure fault. Leave the
            # message queued and let it retry once the breaker closes.
            logger.error("breaker open, leaving command queued", extra={"orderId": order_id})
            return False
        except Exception:
            logger.exception("reservation failed", extra={"orderId": order_id})
            return False

        if result.duplicate:
            logger.info("duplicate order command acknowledged", extra={"eventId": event_id})

        # Low-latency best effort. A failure is intentionally not returned to
        # SQS because Aurora already contains the durable outcome; the outbox
        # thread retries it independently.
        self._outbox.publish_once()

        return True

    def poll_once(self, wait_seconds: int = 1, max_messages: int = 10) -> int:
        queue_url = self._settings.orders_queue_url
        if not queue_url:
            return 0

        messages = self.client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
            MessageAttributeNames=["All"],
        ).get("Messages", [])

        handled = 0
        for message in messages:
            event_id = (
                message.get("MessageAttributes", {})
                .get("eventId", {})
                .get("StringValue")
            )
            if self.handle(message["Body"], event_id=event_id):
                self.client.delete_message(
                    QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
                )
                handled += 1
        return handled

    def run_forever(self, stop: threading.Event, wait_seconds: int = 20) -> None:
        logger.info("inventory consumer started")
        while not stop.is_set():
            try:
                self.poll_once(wait_seconds=wait_seconds)
            except Exception:
                logger.exception("inventory poll failed")
                stop.wait(5)
        logger.info("inventory consumer stopped")
