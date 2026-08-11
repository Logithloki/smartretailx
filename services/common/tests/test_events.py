from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from srx_common.events import EventEnvelope, new_event


def test_event_envelope_contains_required_contract_fields():
    event = new_event(
        event_type="order-created",
        event_id="order-created#ord-1",
        aggregate_id="ord-1",
        correlation_id="corr-1",
        payload={"orderId": "ord-1"},
    )
    body = event.model_dump(mode="json")

    assert body["eventType"] == "order-created"
    assert body["eventVersion"] == "1.0"
    assert body["eventId"] == "order-created#ord-1"
    assert body["aggregateId"] == "ord-1"
    assert body["correlationId"] == "corr-1"
    assert body["payload"] == {"orderId": "ord-1"}
    assert datetime.fromisoformat(body["occurredAt"]).tzinfo == UTC


def test_event_contract_rejects_missing_correlation_id():
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(
            {
                "eventType": "order-created",
                "eventVersion": "1.0",
                "eventId": "event-1",
                "occurredAt": datetime.now(UTC).isoformat(),
                "aggregateId": "ord-1",
                "payload": {},
            }
        )
