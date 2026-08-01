"""Saga outcome publisher - the half the old guide never built.

Inventory is the service that decides. It announces the outcome on SNS as a
domain event and does not care who listens: the Order Service applies it to
the order, and from Week 4 a Lambda turns order-confirmed into an email. That
indifference is what makes this choreography (ADR-06) rather than orchestration.

The `eventType` message attribute is what SNS filter policies match on, so
subscribers are filtered server-side and never pay to receive events they
would discard.
"""

from __future__ import annotations

import json
import logging

import boto3

logger = logging.getLogger(__name__)

ORDER_CONFIRMED = "order-confirmed"
ORDER_REJECTED = "order-rejected"


class SagaEventPublisher:
    def __init__(self, settings):
        self._settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("sns", **self._settings.boto_kwargs())
        return self._client

    def _publish(self, event_type: str, payload: dict, load_test: bool = False) -> str:
        if not self._settings.sns_topic_arn:
            raise RuntimeError("SNS_TOPIC_ARN is not configured")

        body = {"eventType": event_type, **payload}
        attributes = {"eventType": {"DataType": "String", "StringValue": event_type}}
        if load_test:
            # Week 7: k6 order-path runs set this so the SNS -> Lambda -> SES
            # subscription can filter them out and not flood the inbox
            # (amendment 21).
            attributes["loadTest"] = {"DataType": "String", "StringValue": "true"}

        response = self.client.publish(
            TopicArn=self._settings.sns_topic_arn,
            Message=json.dumps(body),
            MessageAttributes=attributes,
        )
        logger.info(
            "saga event published",
            extra={"eventType": event_type, "orderId": payload.get("orderId")},
        )
        return response["MessageId"]

    def order_confirmed(self, order_id: str, user_id: str | None = None, **extra) -> str:
        return self._publish(
            ORDER_CONFIRMED, {"orderId": order_id, "userId": user_id, **extra}
        )

    def order_rejected(self, order_id: str, reason: str, user_id: str | None = None, **extra) -> str:
        """The compensating event: the Order Service moves the order to
        REJECTED when it receives this."""
        return self._publish(
            ORDER_REJECTED,
            {"orderId": order_id, "userId": user_id, "reason": reason, **extra},
        )
