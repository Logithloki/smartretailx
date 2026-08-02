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

from .events import SagaEventPublisher
from .models import ReservationLine

logger = logging.getLogger(__name__)


class InventoryConsumer:
    def __init__(self, settings, stock, publisher: SagaEventPublisher | None = None):
        self._settings = settings
        self._stock = stock
        self._publisher = publisher or SagaEventPublisher(settings)
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

    def handle(self, raw_body: str) -> bool:
        """Process one command. Returns True if the message should be deleted.

        Returning False leaves the message for redelivery and, after
        maxReceiveCount, the DLQ - which is where anything we could not decide
        belongs.
        """
        try:
            event = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.warning("discarding unparseable command")
            return True  # a poison message will never parse; do not loop on it

        if event.get("eventType") != "order-created":
            logger.debug("ignoring event", extra={"eventType": event.get("eventType")})
            return True

        order_id = event.get("orderId")
        if not order_id:
            logger.warning("command has no orderId")
            return True

        user_id = event.get("userId")
        # Carried through unchanged so the notification Lambda has a recipient.
        passthrough = {
            "userEmail": event.get("userEmail"),
            "correlationId": event.get("correlationId"),
        }
        lines = self._lines(event)
        if not lines:
            self._publisher.order_rejected(
                order_id, "order contained no items", user_id, **passthrough
            )
            return True

        try:
            result = self._stock.reserve(lines)
        except pybreaker.CircuitBreakerError:
            # The database is known-bad. Do not reject the order - that would
            # be a business decision made on an infrastructure fault. Leave the
            # message queued and let it retry once the breaker closes.
            logger.error("breaker open, leaving command queued", extra={"orderId": order_id})
            return False
        except Exception:
            logger.exception("reservation failed", extra={"orderId": order_id})
            return False

        if result.ok:
            self._publisher.order_confirmed(order_id, user_id, **passthrough)
        else:
            # Compensating event: stock was never taken, so nothing to undo
            # here - the Order Service marks the order REJECTED.
            self._publisher.order_rejected(
                order_id, result.reason or "rejected", user_id, **passthrough
            )

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
            if self.handle(message["Body"]):
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
