from __future__ import annotations

import json
import os

import boto3
import pytest
from moto import mock_aws

import handler as h

SENDER = "noreply@example.com"
CUSTOMER = "customer@example.com"
IDEMPOTENCY_TABLE = "test-idempotency"


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
    event = {
        "eventType": event_type,
        "orderId": "ord-abc123",
        "userId": "user-1",
        "userEmail": CUSTOMER,
        "correlationId": "corr-1",
    }
    event.update(overrides)
    return event


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
# email content
# --------------------------------------------------------------------------

def test_confirmed_email_mentions_the_order():
    subject, body = h.build_email(domain_event())
    assert "ord-abc123" in subject
    assert "confirmed" in subject.lower()


def test_rejected_email_carries_the_reason_and_reassures_about_payment():
    subject, body = h.build_email(
        domain_event("order-rejected", reason="insufficient stock for p1")
    )
    assert "insufficient stock for p1" in body
    assert "charged" in body.lower()


def test_rejected_email_has_a_reason_even_when_none_is_supplied():
    _, body = h.build_email(domain_event("order-rejected", reason=None))
    assert "unavailable" in body.lower()


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


def test_unrelated_event_types_are_ignored(ses_verified):
    result = h.deliver(domain_event("order-created"))
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


def test_unwrap_sns_reads_the_message_body():
    assert h.unwrap_sns(sns_event(domain_event())["Records"][0])["orderId"] == "ord-abc123"
