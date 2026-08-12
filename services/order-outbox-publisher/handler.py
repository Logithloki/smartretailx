"""Publish transactional order outbox inserts to the reservation queue."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_ddb = None
_sqs = None
_events = None
_deserializer = TypeDeserializer()


def _resource():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb", region_name=os.environ.get("APP_REGION", "eu-west-1"))
    return _ddb


def _table():
    return _resource().Table(os.environ["ORDER_OUTBOX_TABLE_NAME"])


def _sqs_client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs", region_name=os.environ.get("APP_REGION", "eu-west-1"))
    return _sqs


def _events_client():
    global _events
    if _events is None:
        _events = boto3.client("events", region_name=os.environ.get("APP_REGION", "eu-west-1"))
    return _events


def _json_default(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"not JSON serialisable: {type(value)}")


def _new_image(record: dict) -> dict:
    image = (record.get("dynamodb") or {}).get("NewImage") or {}
    return {name: _deserializer.deserialize(value) for name, value in image.items()}


def _process_record(record: dict) -> None:
    if record.get("eventName") != "INSERT":
        return

    outbox = _new_image(record)
    if outbox.get("state") != "PENDING" or not outbox.get("eventId"):
        return

    # A replay of the original stream record after the state update must not
    # republish an already delivered command.
    current = _table().get_item(
        Key={"eventId": outbox["eventId"]},
        ConsistentRead=True,
        ProjectionExpression="#state",
        ExpressionAttributeNames={"#state": "state"},
    ).get("Item")
    if not current or current.get("state") != "PENDING":
        return

    event_type = outbox["eventType"]
    if outbox.get("destination", "SQS") == "EVENTBRIDGE":
        response = _events_client().put_events(Entries=[{
            "EventBusName": os.environ["EVENT_BUS_NAME"],
            "Source": "smartretailx.orders",
            "DetailType": event_type,
            "Detail": json.dumps(outbox["payload"], default=_json_default),
        }])
        if response.get("FailedEntryCount", 0):
            raise RuntimeError("EventBridge rejected order outbox event")
        message_id = response["Entries"][0].get("EventId", "eventbridge")
    else:
        response = _sqs_client().send_message(
            QueueUrl=os.environ["ORDERS_QUEUE_URL"],
            MessageBody=json.dumps(outbox["payload"], default=_json_default),
            MessageAttributes={
                "eventType": {"DataType": "String", "StringValue": event_type},
                "eventId": {"DataType": "String", "StringValue": outbox["eventId"]},
            },
        )
        message_id = response["MessageId"]
    _table().update_item(
        Key={"eventId": outbox["eventId"]},
        UpdateExpression="SET #state = :delivered, deliveredAt = :at, messageId = :message",
        ConditionExpression="#state = :pending",
        ExpressionAttributeNames={"#state": "state"},
        ExpressionAttributeValues={
            ":pending": "PENDING",
            ":delivered": "DELIVERED",
            ":at": datetime.now(UTC).isoformat(),
            ":message": message_id,
        },
    )
    logger.info(
        "order command delivered",
        extra={"eventId": outbox["eventId"], "messageId": message_id},
    )


def lambda_handler(event, _context):
    failures = []
    for record in event.get("Records", []):
        try:
            _process_record(record)
        except Exception:
            logger.exception("order outbox delivery failed", extra={"eventId": record.get("eventID")})
            failures.append({"itemIdentifier": record["eventID"]})
    return {"batchItemFailures": failures}
