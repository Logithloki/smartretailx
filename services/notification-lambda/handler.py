"""Order notification Lambda - SNS -> SES.

Powertools does three jobs here:

  Logger       structured JSON with the correlation id carried from the order,
               so one CloudWatch Logs Insights query spans API -> SQS -> SNS -> Lambda.
  Tracer       X-Ray segments, which is what makes the service map in the report
               show the notification hop rather than stopping at SNS.
  Idempotency  SNS is at-least-once. Without this, a redelivery sends the
               customer a second "order confirmed" email.

Recipient resolution is event-carried: the Order Service reads `email` from the
verified JWT and puts it on the command, Inventory passes it through to the
outcome event, and this Lambda uses it. The alternative - calling Cognito from
here to turn a `sub` into an address - would couple the notification path to the
user directory and add a network hop to every email.
"""

from __future__ import annotations

import json
import os

import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.idempotency import (
    DynamoDBPersistenceLayer,
    IdempotencyConfig,
    idempotent_function,
)

SERVICE = "notification-lambda"

logger = Logger(service=SERVICE)
tracer = Tracer(service=SERVICE)

ORDER_CONFIRMED = "order-confirmed"
ORDER_REJECTED = "order-rejected"

_ses_client = None


def ses():
    global _ses_client
    if _ses_client is None:
        _ses_client = boto3.client("ses", region_name=os.environ.get("APP_REGION", "eu-west-1"))
    return _ses_client


def unwrap_sns(record: dict) -> dict:
    """Pull the domain event out of the SNS record."""
    message = record.get("Sns", {}).get("Message", "{}")
    return json.loads(message) if isinstance(message, str) else message


def build_email(event: dict) -> tuple[str, str]:
    order_id = event.get("orderId", "unknown")
    if event.get("eventType") == ORDER_REJECTED:
        reason = event.get("reason") or "an item was unavailable"
        return (
            f"We couldn't complete order {order_id}",
            f"Unfortunately your order {order_id} could not be fulfilled: {reason}.\n"
            "Nothing has been charged.\n\nSmartRetailX",
        )
    return (
        f"Order {order_id} confirmed",
        f"Thanks - your order {order_id} is confirmed and being prepared.\n\nSmartRetailX",
    )


def recipient_for(event: dict) -> str | None:
    return event.get("userEmail") or os.environ.get("NOTIFICATION_FALLBACK_EMAIL") or None


@tracer.capture_method
def deliver(event: dict) -> dict:
    """Send one notification. Separated from the handler so it can be tested
    without constructing a Lambda event."""
    event_type = event.get("eventType")
    if event_type not in {ORDER_CONFIRMED, ORDER_REJECTED}:
        logger.info("ignoring event", extra={"eventType": event_type})
        return {"sent": False, "reason": "unhandled event type"}

    to_address = recipient_for(event)
    if not to_address:
        # SES sandbox only delivers to verified addresses, so a missing
        # recipient is a configuration problem worth surfacing, not a crash.
        logger.warning("no recipient for notification", extra={"orderId": event.get("orderId")})
        return {"sent": False, "reason": "no recipient"}

    subject, body = build_email(event)
    sender = os.environ["SES_SENDER_EMAIL"]

    response = ses().send_email(
        Source=sender,
        Destination={"ToAddresses": [to_address]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
        },
    )
    logger.info(
        "notification sent",
        extra={
            "orderId": event.get("orderId"),
            "eventType": event_type,
            "messageId": response.get("MessageId"),
        },
    )
    return {"sent": True, "messageId": response.get("MessageId")}


# Idempotency key is the SNS MessageId: unique per publish, repeated on redelivery.
_idempotency_config = IdempotencyConfig(event_key_jmespath="Sns.MessageId")

_processor = None


def get_processor():
    """Build the idempotent wrapper on first invocation, not at import.

    The persistence layer needs a table name and a boto3 client, and neither
    should be required merely to import this module - that would make the
    handler untestable and would turn a missing env var into an import crash
    rather than a clear runtime error.
    """
    global _processor
    if _processor is None:
        store = DynamoDBPersistenceLayer(table_name=os.environ["IDEMPOTENCY_TABLE_NAME"])

        @idempotent_function(
            data_keyword_argument="record",
            persistence_store=store,
            config=_idempotency_config,
        )
        def _process(record: dict) -> dict:
            return deliver(unwrap_sns(record))

        _processor = _process
    return _processor


def reset_processor() -> None:
    """Test hook - drops the cached wrapper so a fresh table can be bound."""
    global _processor
    _processor = None


@logger.inject_lambda_context(log_event=False)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context) -> dict:
    _idempotency_config.register_lambda_context(context)
    process = get_processor()

    results = []
    for record in event.get("Records", []):
        domain_event = unwrap_sns(record)
        correlation_id = domain_event.get("correlationId")
        if correlation_id:
            logger.set_correlation_id(correlation_id)
        results.append(process(record=record))

    return {"processed": len(results), "results": results}
