"""Outbound messaging.

Event routing rule (the viva answer): commands go to SQS, domain events go to
EventBridge, fan-out goes to SNS. "Reserve this stock" is an instruction aimed
at exactly one consumer, so it is a command on SQS - not an event.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

import boto3

from .models import Order

logger = logging.getLogger(__name__)


def _json_default(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    raise TypeError(f"not JSON serialisable: {type(value)}")


class OrderCommandPublisher:
    def __init__(self, settings):
        self._settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("sqs", **self._settings.boto_kwargs())
        return self._client

    def publish_order_created(
        self,
        order: Order,
        correlation_id: str | None = None,
        user_email: str | None = None,
    ) -> str:
        if not self._settings.orders_queue_url:
            raise RuntimeError("ORDERS_QUEUE_URL is not configured")

        body = {
            "eventType": "order-created",
            "orderId": order.orderId,
            "userId": order.userId,
            # Event-carried state transfer: the address comes from the verified
            # JWT here and rides the saga, so the notification Lambda never has
            # to call Cognito to turn a sub into an email.
            "userEmail": user_email,
            "totalAmount": order.totalAmount,
            "items": [
                {
                    "productId": item.productId,
                    "quantity": item.quantity,
                    "unitPrice": item.unitPrice,
                }
                for item in order.items
            ],
        }
        if correlation_id:
            body["correlationId"] = correlation_id

        response = self.client.send_message(
            QueueUrl=self._settings.orders_queue_url,
            MessageBody=json.dumps(body, default=_json_default),
            MessageAttributes={
                "eventType": {"DataType": "String", "StringValue": "order-created"}
            },
        )
        logger.info(
            "order command published",
            extra={"orderId": order.orderId, "messageId": response["MessageId"]},
        )
        return response["MessageId"]
