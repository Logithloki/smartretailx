from __future__ import annotations

import json
from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws

import handler as h

SENDER = "noreply@example.com"
CUSTOMER = "customer@example.com"
IDEMPOTENCY_TABLE = "test-idempotency"
FRONTEND_URL = "https://d1p906ifpq8jeg.cloudfront.net"


class Context:
    """Minimal stand-in for the real Lambda context.

    get_remaining_time_in_millis is not optional: Powertools Idempotency uses it
    to size the in-progress record's expiry window, so an in-progress record
    cannot outlive the invocation that created it and wedge later retries.
    """

    function_name = "smartretailx-notification"
    memory_limit_in_mb = 256
    invoked_function_arn = "arn:aws:lambda:eu-west-1:000000000000:function:smartretailx-notification"
    aws_request_id = "req-1"

    @staticmethod
    def get_remaining_time_in_millis() -> int:
        return 30_000


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "eu-west-1",
        "APP_REGION": "eu-west-1",
        "SES_SENDER_EMAIL": SENDER,
        "IDEMPOTENCY_TABLE_NAME": IDEMPOTENCY_TABLE,
        "FRONTEND_URL": FRONTEND_URL,
        "POWERTOOLS_TRACE_DISABLED": "true",
        "POWERTOOLS_SERVICE_NAME": "notification-lambda",
    }.items():
        monkeypatch.setenv(key, value)
    h._ses_client = None
    h.reset_processor()
    yield
    h._ses_client = None
    h.reset_processor()


@pytest.fixture
def aws():
    with mock_aws():
        yield


@pytest.fixture
def ses_verified(aws):
    client = boto3.client("ses", region_name="eu-west-1")
    client.verify_email_identity(EmailAddress=SENDER)
    client.verify_email_identity(EmailAddress=CUSTOMER)
    return client


@pytest.fixture
def idempotency_table(aws):
    ddb = boto3.resource("dynamodb", region_name="eu-west-1")
    return ddb.create_table(
        TableName=IDEMPOTENCY_TABLE,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def domain_event(event_type: str = "order-confirmed", **overrides) -> dict:
    payload = {
        "orderId": "ord-abc123",
        "userId": "user-1",
        "userEmail": CUSTOMER,
    }
    payload.update(overrides)
    order_id = payload["orderId"]
    return {
        "eventType": event_type,
        "eventVersion": "1.0",
        "eventId": f"inventory-outcome#{order_id}",
        "occurredAt": datetime.now(UTC).isoformat(),
        "correlationId": "corr-1",
        "aggregateId": order_id,
        "causationId": f"order-created#{order_id}",
        "traceId": None,
        "payload": payload,
    }


def sns_event(event: dict, message_id: str = "msg-1") -> dict:
    return {
        "Records": [
            {
                "EventSource": "aws:sns",
                "Sns": {"MessageId": message_id, "Message": json.dumps(event)},
            }
        ]
    }


def sent_count(client) -> int:
    return int(client.get_send_quota()["SentLast24Hours"])


# --------------------------------------------------------------------------
# email content - confirmed
# --------------------------------------------------------------------------

def test_confirmed_email_mentions_the_order():
    subject, text, html = h.build_email(domain_event())
    assert "ord-abc123" in subject
    assert "confirmed" in subject.lower()


def test_confirmed_email_text_body_has_order_id():
    _, text, _ = h.build_email(domain_event())
    assert "ord-abc123" in text
    assert "confirmed" in text.lower()


def test_confirmed_email_has_smartretailx_branding():
    subject, text, html = h.build_email(domain_event())
    assert "SmartRetailX" in subject
    assert "SmartRetailX" in text
    assert "SmartRetailX" in html


def test_confirmed_email_has_cta_link():
    _, text, html = h.build_email(domain_event())
    expected_url = f"{FRONTEND_URL}/orders/ord-abc123"
    assert expected_url in text
    assert expected_url in html


def test_confirmed_email_no_payment_claims():
    _, text, html = h.build_email(domain_event())
    for forbidden in ["payment successful", "payment completed", "paid", "payment confirmed",
                       "payment receipt", "payment transaction"]:
        assert forbidden not in text.lower(), f"text body contains forbidden phrase: {forbidden}"
        assert forbidden not in html.lower(), f"HTML body contains forbidden phrase: {forbidden}"


# --------------------------------------------------------------------------
# email content - rejected
# --------------------------------------------------------------------------

def test_rejected_email_carries_the_reason_and_reassures_about_charges():
    subject, text, html = h.build_email(
        domain_event("order-rejected", reason="insufficient stock for p1")
    )
    assert "insufficient stock for p1" in text
    assert "charged" in text.lower()


def test_rejected_email_has_a_reason_even_when_none_is_supplied():
    _, text, _ = h.build_email(domain_event("order-rejected", reason=None))
    assert "unavailable" in text.lower()


def test_rejected_email_no_payment_claims():
    _, text, html = h.build_email(domain_event("order-rejected", reason="out of stock"))
    for forbidden in ["payment successful", "payment completed", "payment receipt"]:
        assert forbidden not in text.lower()
        assert forbidden not in html.lower()


# --------------------------------------------------------------------------
# email content - cancelled
# --------------------------------------------------------------------------

def test_cancelled_email_mentions_order_and_cancellation():
    subject, text, html = h.build_email(domain_event("order-cancelled"))
    assert "ord-abc123" in subject
    assert "cancelled" in subject.lower()
    assert "cancelled" in text.lower()


def test_cancelled_email_confirms_no_charge():
    _, text, html = h.build_email(domain_event("order-cancelled"))
    assert "charged" in text.lower()


def test_cancelled_email_has_cta_link():
    _, text, html = h.build_email(domain_event("order-cancelled"))
    expected_url = f"{FRONTEND_URL}/orders/ord-abc123"
    assert expected_url in text


def test_cancelled_email_no_payment_claims():
    _, text, html = h.build_email(domain_event("order-cancelled"))
    for forbidden in ["payment successful", "payment completed", "paid ",
                       "payment confirmed", "payment receipt"]:
        assert forbidden not in text.lower()
        assert forbidden not in html.lower()


def test_cancelled_email_has_smartretailx_branding():
    subject, text, html = h.build_email(domain_event("order-cancelled"))
    assert "SmartRetailX" in subject
    assert "SmartRetailX" in text
    assert "SmartRetailX" in html


# --------------------------------------------------------------------------
# HTML structure
# --------------------------------------------------------------------------

def test_html_body_is_well_formed():
    _, _, html = h.build_email(domain_event())
    assert html.startswith("<div")
    assert "</div>" in html
    assert "View order" in html


def test_html_body_includes_order_reference():
    _, _, html = h.build_email(domain_event())
    assert "ord-abc123" in html


def test_html_body_escapes_special_characters():
    _, _, html = h.build_email(domain_event("order-rejected", reason='<script>alert("xss")</script>'))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# --------------------------------------------------------------------------
# CTA link when FRONTEND_URL is empty
# --------------------------------------------------------------------------

def test_no_cta_when_frontend_url_is_empty(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "")
    _, text, html = h.build_email(domain_event())
    assert "View order" not in html
    assert "/orders/" not in text


# --------------------------------------------------------------------------
# recipient resolution
# --------------------------------------------------------------------------

def test_recipient_comes_from_the_event():
    assert h.recipient_for(domain_event()) == CUSTOMER


def test_recipient_falls_back_to_configured_address(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_FALLBACK_EMAIL", "ops@example.com")
    assert h.recipient_for(domain_event(userEmail=None)) == "ops@example.com"


def test_no_recipient_is_reported_not_raised(ses_verified):
    """A missing address is a configuration problem; crashing would send the
    message to the DLQ and lose the notification entirely."""
    result = h.deliver(domain_event(userEmail=None))
    assert result == {"sent": False, "reason": "no recipient"}


# --------------------------------------------------------------------------
# delivery
# --------------------------------------------------------------------------

def test_confirmed_event_sends_an_email(ses_verified):
    result = h.deliver(domain_event())
    assert result["sent"] is True
    assert sent_count(ses_verified) == 1


def test_rejected_event_also_sends_an_email(ses_verified):
    """The guide filters the Lambda on order-confirmed; a customer whose order
    failed deserves to be told too."""
    assert h.deliver(domain_event("order-rejected", reason="out of stock"))["sent"] is True
    assert sent_count(ses_verified) == 1


def test_cancelled_event_sends_an_email(ses_verified):
    assert h.deliver(domain_event("order-cancelled"))["sent"] is True
    assert sent_count(ses_verified) == 1


def test_unrelated_event_types_are_ignored(ses_verified):
    result = h.deliver(domain_event("order-created"))
    assert result["sent"] is False
    assert sent_count(ses_verified) == 0


def test_fulfilment_event_is_ignored(ses_verified):
    result = h.deliver(domain_event("fulfilment-status-changed"))
    assert result["sent"] is False
    assert sent_count(ses_verified) == 0


# --------------------------------------------------------------------------
# handler + idempotency
# --------------------------------------------------------------------------

def test_handler_processes_an_sns_record(ses_verified, idempotency_table):
    result = h.lambda_handler(sns_event(domain_event()), Context())
    assert result["processed"] == 1
    assert sent_count(ses_verified) == 1


def test_redelivery_of_the_same_message_sends_only_one_email(ses_verified, idempotency_table):
    """SNS is at-least-once. Without Powertools Idempotency the customer gets
    a second confirmation for the same order."""
    event = sns_event(domain_event(), message_id="msg-dup")
    h.lambda_handler(event, Context())
    h.lambda_handler(event, Context())
    assert sent_count(ses_verified) == 1


def test_distinct_messages_each_send(ses_verified, idempotency_table):
    h.lambda_handler(sns_event(domain_event(), message_id="msg-a"), Context())
    h.lambda_handler(
        sns_event(domain_event(orderId="ord-two"), message_id="msg-b"), Context()
    )
    assert sent_count(ses_verified) == 2


def test_handler_handles_a_batch(ses_verified, idempotency_table):
    event = {
        "Records": [
            sns_event(domain_event(orderId="ord-1"), "m1")["Records"][0],
            sns_event(domain_event(orderId="ord-2"), "m2")["Records"][0],
        ]
    }
    assert h.lambda_handler(event, Context())["processed"] == 2
    assert sent_count(ses_verified) == 2


def test_cancelled_handler_idempotent(ses_verified, idempotency_table):
    event = sns_event(domain_event("order-cancelled"), message_id="msg-cancel-dup")
    h.lambda_handler(event, Context())
    h.lambda_handler(event, Context())
    assert sent_count(ses_verified) == 1


def test_unwrap_sns_reads_the_message_body():
    assert h.unwrap_sns(sns_event(domain_event())["Records"][0])["aggregateId"] == "ord-abc123"


# --------------------------------------------------------------------------
# milestone mapping completeness
# --------------------------------------------------------------------------

def test_all_handled_events_produce_emails(ses_verified):
    for event_type in ["order-confirmed", "order-rejected", "order-cancelled"]:
        h._ses_client = None
        result = h.deliver(domain_event(event_type))
        assert result["sent"] is True, f"{event_type} did not send"


def test_each_milestone_has_distinct_subject():
    subjects = set()
    for event_type in ["order-confirmed", "order-rejected", "order-cancelled"]:
        subject, _, _ = h.build_email(domain_event(event_type))
        subjects.add(subject)
    assert len(subjects) == 3, "each milestone should produce a distinct subject line"


# --------------------------------------------------------------------------
# email content - fulfilment dispatched
# --------------------------------------------------------------------------

def test_dispatched_email_mentions_order_and_dispatch():
    subject, text, html = h.build_email(
        domain_event("fulfilment-status-changed", fulfilmentStatus="DISPATCHED")
    )
    assert "ord-abc123" in subject
    assert "dispatched" in subject.lower()
    assert "dispatched" in text.lower()


def test_dispatched_email_has_smartretailx_branding():
    subject, text, html = h.build_email(
        domain_event("fulfilment-status-changed", fulfilmentStatus="DISPATCHED")
    )
    assert "SmartRetailX" in subject
    assert "SmartRetailX" in text
    assert "SmartRetailX" in html


def test_dispatched_email_has_cta_link():
    _, text, html = h.build_email(
        domain_event("fulfilment-status-changed", fulfilmentStatus="DISPATCHED")
    )
    expected_url = f"{FRONTEND_URL}/orders/ord-abc123"
    assert expected_url in text
    assert expected_url in html


def test_dispatched_email_no_payment_claims():
    _, text, html = h.build_email(
        domain_event("fulfilment-status-changed", fulfilmentStatus="DISPATCHED")
    )
    for forbidden in ["payment successful", "payment completed", "paid",
                       "payment confirmed", "payment receipt"]:
        assert forbidden not in text.lower()
        assert forbidden not in html.lower()


# --------------------------------------------------------------------------
# email content - fulfilment delivered
# --------------------------------------------------------------------------

def test_delivered_email_mentions_order_and_delivery():
    subject, text, html = h.build_email(
        domain_event("fulfilment-status-changed", fulfilmentStatus="DELIVERED")
    )
    assert "ord-abc123" in subject
    assert "delivered" in subject.lower()
    assert "delivered" in text.lower()


def test_delivered_email_has_smartretailx_branding():
    subject, text, html = h.build_email(
        domain_event("fulfilment-status-changed", fulfilmentStatus="DELIVERED")
    )
    assert "SmartRetailX" in subject
    assert "SmartRetailX" in text
    assert "SmartRetailX" in html


def test_delivered_email_has_cta_link():
    _, text, html = h.build_email(
        domain_event("fulfilment-status-changed", fulfilmentStatus="DELIVERED")
    )
    expected_url = f"{FRONTEND_URL}/orders/ord-abc123"
    assert expected_url in text


def test_delivered_email_no_payment_claims():
    _, text, html = h.build_email(
        domain_event("fulfilment-status-changed", fulfilmentStatus="DELIVERED")
    )
    for forbidden in ["payment successful", "payment completed", "paid",
                       "payment confirmed", "payment receipt"]:
        assert forbidden not in text.lower()
        assert forbidden not in html.lower()


# --------------------------------------------------------------------------
# fulfilment delivery filtering
# --------------------------------------------------------------------------

def test_dispatched_sends_email(ses_verified):
    result = h.deliver(domain_event("fulfilment-status-changed", fulfilmentStatus="DISPATCHED"))
    assert result["sent"] is True
    assert sent_count(ses_verified) == 1


def test_delivered_sends_email(ses_verified):
    result = h.deliver(domain_event("fulfilment-status-changed", fulfilmentStatus="DELIVERED"))
    assert result["sent"] is True


def test_packing_does_not_send_email(ses_verified):
    result = h.deliver(domain_event("fulfilment-status-changed", fulfilmentStatus="PACKING"))
    assert result["sent"] is False
    assert sent_count(ses_verified) == 0


def test_not_started_does_not_send_email(ses_verified):
    result = h.deliver(domain_event("fulfilment-status-changed", fulfilmentStatus="NOT_STARTED"))
    assert result["sent"] is False


# --------------------------------------------------------------------------
# EventBridge invocation format
# --------------------------------------------------------------------------

def _eventbridge_event(event: dict) -> dict:
    return {
        "version": "0",
        "id": "eb-test-1",
        "source": "smartretailx.orders",
        "detail-type": "fulfilment-status-changed",
        "detail": event,
    }


def test_eventbridge_invocation_dispatched(ses_verified, idempotency_table):
    eb_event = _eventbridge_event(
        domain_event("fulfilment-status-changed", fulfilmentStatus="DISPATCHED")
    )
    result = h.lambda_handler(eb_event, Context())
    assert result["processed"] == 1
    assert sent_count(ses_verified) == 1


def test_eventbridge_invocation_packing_skipped(ses_verified, idempotency_table):
    eb_event = _eventbridge_event(
        domain_event("fulfilment-status-changed", fulfilmentStatus="PACKING")
    )
    result = h.lambda_handler(eb_event, Context())
    assert result["processed"] == 1
    assert sent_count(ses_verified) == 0


def test_fulfilment_milestones_have_distinct_subjects():
    subjects = set()
    for status in ["DISPATCHED", "DELIVERED"]:
        subject, _, _ = h.build_email(
            domain_event("fulfilment-status-changed", fulfilmentStatus=status)
        )
        subjects.add(subject)
    assert len(subjects) == 2
