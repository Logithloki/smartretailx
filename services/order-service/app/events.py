"""Order command contract stored in the transactional outbox.

Event routing rule (the viva answer): commands go to SQS, domain events go to
EventBridge, fan-out goes to SNS. "Reserve this stock" is an instruction aimed
at exactly one consumer, so it is a command on SQS - not an event.
"""

from __future__ import annotations

import json

import boto3
from srx_common import new_event

from .models import Order

def order_created_command(
    order: Order,
    correlation_id: str,
    user_email: str | None = None,
    load_test: bool = False,
) -> dict:
    payload = {
        "orderId": order.orderId,
        "userId": order.userId,
        # Event-carried state transfer avoids a downstream Cognito lookup.
        "userEmail": user_email,
        "loadTest": load_test,
        "totalAmount": order.totalAmount,
        "items": [
            {
                "productId": item.productId,
                "quantity": item.quantity,
                "effectiveUnitPrice": item.effectiveUnitPrice,
            }
            for item in order.items
        ],
    }
    return new_event(
        event_type="order-created",
        event_id=f"order-created#{order.orderId}",
        aggregate_id=order.orderId,
        correlation_id=correlation_id,
        payload=payload,
    ).model_dump(mode="json")


def fulfilment_status_changed(order: Order, correlation_id: str) -> dict:
    return new_event(
        event_type="fulfilment-status-changed",
        event_id=f"fulfilment-status-changed#{order.orderId}#{order.fulfilmentStatus.value}",
        aggregate_id=order.orderId,
        correlation_id=correlation_id,
        payload={
            "orderId": order.orderId,
            "userId": order.userId,
            "fulfilmentStatus": order.fulfilmentStatus.value,
        },
    ).model_dump(mode="json")


def order_cancel_requested(order: Order, correlation_id: str) -> dict:
    return new_event(
        event_type="order-cancel-requested", event_id=f"order-cancel-requested#{order.orderId}",
        aggregate_id=order.orderId, correlation_id=correlation_id,
        payload={"orderId": order.orderId, "userId": order.userId, "items": [
            {"productId": item.productId, "quantity": item.quantity} for item in order.items
        ]},
    ).model_dump(mode="json")


class LocalInlineOutboxPublisher:
    """LocalStack-only relay used because Community cannot run this Lambda seam."""

    def __init__(self, settings):
        self._settings = settings
        self._resource = boto3.resource("dynamodb", **settings.boto_kwargs())
        self._sqs = boto3.client("sqs", **settings.boto_kwargs())
        self._events = boto3.client("events", **settings.boto_kwargs())

    def publish(self, event_id: str) -> None:
        table = self._resource.Table(self._settings.order_outbox_table_name)
        record = table.get_item(Key={"eventId": event_id}, ConsistentRead=True).get("Item")
        if not record or record.get("state") != "PENDING":
            return
        if record.get("destination", "SQS") == "EVENTBRIDGE":
            result = self._events.put_events(Entries=[{
                "EventBusName": self._settings.event_bus_name,
                "Source": "smartretailx.orders",
                "DetailType": record["eventType"],
                "Detail": json.dumps(record["payload"]),
            }])
            if result.get("FailedEntryCount", 0):
                raise RuntimeError("EventBridge rejected the outbox event")
            message_id = result["Entries"][0].get("EventId", "eventbridge")
        else:
            result = self._sqs.send_message(
                QueueUrl=self._settings.orders_queue_url,
                MessageBody=json.dumps(record["payload"]),
                MessageAttributes={
                    "eventType": {"DataType": "String", "StringValue": record["eventType"]},
                    "eventId": {"DataType": "String", "StringValue": event_id},
                },
            )
            message_id = result["MessageId"]
        table.update_item(
            Key={"eventId": event_id},
            UpdateExpression="SET #state = :delivered, messageId = :message",
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues={
                ":delivered": "DELIVERED",
                ":message": message_id,
            },
        )
