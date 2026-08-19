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
from html import escape

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
ORDER_CANCELLED = "order-cancelled"

HANDLED_EVENTS = {ORDER_CONFIRMED, ORDER_REJECTED, ORDER_CANCELLED}

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


def event_payload(event: dict) -> dict:
    """Validate and flatten the versioned envelope for notification logic."""
    if event.get("eventVersion") is None:
        return event  # compatibility for notifications already queued before the rollout
    required = {
        "eventType",
        "eventVersion",
        "eventId",
        "occurredAt",
        "correlationId",
        "aggregateId",
        "payload",
    }
    missing = required.difference(event)
    if missing or not isinstance(event.get("payload"), dict):
        raise ValueError(f"invalid event envelope; missing={sorted(missing)}")
    return {
        **event["payload"],
        "eventType": event["eventType"],
        "eventId": event["eventId"],
        "correlationId": event["correlationId"],
        "orderId": event["aggregateId"],
    }


def _order_url(order_id: str) -> str | None:
    base = os.environ.get("FRONTEND_URL", "").rstrip("/")
    if not base:
        return None
    return f"{base}/orders/{order_id}"


def build_email(event: dict) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for the given event."""
    event = event_payload(event)
    order_id = event.get("orderId", "unknown")
    order_url = _order_url(order_id)
    event_type = event.get("eventType")

    if event_type == ORDER_REJECTED:
        reason = event.get("reason") or "an item was unavailable"
        subject = f"SmartRetailX - Order {order_id} could not be fulfilled"
        text_body = (
            f"Unfortunately your order {order_id} could not be fulfilled: {reason}.\n"
            "Nothing has been charged.\n\n"
        )
        heading = "Order could not be fulfilled"
        status_text = f"We were unable to complete your order: {reason}."
        status_note = "Nothing has been charged."
        accent = "#dc2626"

    elif event_type == ORDER_CANCELLED:
        subject = f"SmartRetailX - Order {order_id} has been cancelled"
        text_body = (
            f"Your order {order_id} has been cancelled as requested.\n"
            "Any reserved stock has been released. Nothing has been charged.\n\n"
        )
        heading = "Order cancelled"
        status_text = "Your order has been cancelled as requested."
        status_note = "Any reserved stock has been released. Nothing has been charged."
        accent = "#6b7280"

    else:
        subject = f"SmartRetailX - Order {order_id} confirmed"
        text_body = (
            f"Your order {order_id} is confirmed and being prepared.\n\n"
        )
        heading = "Order confirmed"
        status_text = "Your order is confirmed and being prepared."
        status_note = None
        accent = "#059669"

    if order_url:
        text_body += f"Track your order: {order_url}\n\n"
    text_body += "SmartRetailX"

    cta_html = ""
    if order_url:
        cta_html = (
            f'<p style="margin:24px 0 0"><a href="{escape(order_url)}" '
            f'style="display:inline-block;padding:12px 24px;background:{accent};'
            f'color:#ffffff;text-decoration:none;border-radius:6px;font-weight:600">'
            f'View order</a></p>'
        )

    note_html = f'<p style="color:#6b7280;font-size:14px;margin:8px 0 0">{escape(status_note)}</p>' if status_note else ""

    html_body = f"""\
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px">
  <div style="border-bottom:3px solid {accent};padding-bottom:16px;margin-bottom:24px">
    <h2 style="margin:0;color:#111827;font-size:20px">SmartRetailX</h2>
  </div>
  <h1 style="color:#111827;font-size:24px;margin:0 0 16px">{escape(heading)}</h1>
  <p style="color:#374151;font-size:16px;line-height:1.5;margin:0 0 8px">
    <strong>Order:</strong> {escape(order_id)}
  </p>
  <p style="color:#374151;font-size:16px;line-height:1.5;margin:0">{escape(status_text)}</p>
  {note_html}
  {cta_html}
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:32px 0 16px">
  <p style="color:#9ca3af;font-size:12px;margin:0">SmartRetailX &mdash; Enterprise Cloud Application</p>
</div>"""

    return subject, text_body, html_body


def recipient_for(event: dict) -> str | None:
    event = event_payload(event)
    return event.get("userEmail") or os.environ.get("NOTIFICATION_FALLBACK_EMAIL") or None


def _send_email(sender: str, to_address: str, subject: str, text_body: str, html_body: str) -> dict:
    """Send a multipart text+HTML email via SES."""
    return ses().send_email(
        Source=sender,
        Destination={"ToAddresses": [to_address]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": text_body, "Charset": "UTF-8"},
                "Html": {"Data": html_body, "Charset": "UTF-8"},
            },
        },
    )


@tracer.capture_method
def deliver(event: dict) -> dict:
    """Send one notification. Separated from the handler so it can be tested
    without constructing a Lambda event."""
    event = event_payload(event)
    event_type = event.get("eventType")
    if event_type not in HANDLED_EVENTS:
        logger.info("ignoring event", extra={"eventType": event_type})
        return {"sent": False, "reason": "unhandled event type"}

    to_address = recipient_for(event)
    if not to_address:
        logger.warning("no recipient for notification", extra={"orderId": event.get("orderId")})
        return {"sent": False, "reason": "no recipient"}

    subject, text_body, html_body = build_email(event)
    sender = os.environ["SES_SENDER_EMAIL"]

    try:
        response = _send_email(sender, to_address, subject, text_body, html_body)
    except Exception as e:
        if hasattr(e, "response") and e.response.get("Error", {}).get("Code") == "MessageRejected":
            fallback = os.environ.get("NOTIFICATION_FALLBACK_EMAIL")
            if fallback and fallback != to_address:
                logger.warning(
                    "SES Sandbox restriction: original recipient unverified, rerouting to fallback",
                    extra={"originalTo": to_address, "fallbackTo": fallback, "orderId": event.get("orderId")}
                )
                sandbox_prefix = f"[SES SANDBOX NOTE: This email was originally intended for {to_address}]\n\n"
                response = _send_email(sender, fallback, subject, sandbox_prefix + text_body, html_body)
            else:
                logger.error("SES Sandbox restriction and no valid fallback", exc_info=True)
                return {"sent": False, "reason": "unverified recipient in sandbox"}
        else:
            raise

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
