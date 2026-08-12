from __future__ import annotations

import handler as h


def _record(event_name: str = "INSERT", state: str = "PENDING") -> dict:
    return {
        "eventID": "stream-record-1",
        "eventName": event_name,
        "dynamodb": {
            "NewImage": {
                "eventId": {"S": "order-created#ord-1"},
                "eventType": {"S": "order-created"},
                "state": {"S": state},
                "payload": {
                    "M": {
                        "eventType": {"S": "order-created"},
                        "orderId": {"S": "ord-1"},
                        "totalAmount": {"N": "19.99"},
                    }
                },
            }
        },
    }


def _domain_event_record() -> dict:
    record = _record()
    image = record["dynamodb"]["NewImage"]
    image["eventId"] = {"S": "fulfilment-status-changed#ord-1#PACKING"}
    image["eventType"] = {"S": "fulfilment-status-changed"}
    image["destination"] = {"S": "EVENTBRIDGE"}
    image["payload"] = {"M": {
        "eventType": {"S": "fulfilment-status-changed"},
        "eventId": {"S": "fulfilment-status-changed#ord-1#PACKING"},
        "aggregateId": {"S": "ord-1"},
        "correlationId": {"S": "corr-1"},
        "payload": {"M": {
            "orderId": {"S": "ord-1"}, "userId": {"S": "user-1"}, "fulfilmentStatus": {"S": "PACKING"},
        }},
    }}
    return record


class FakeTable:
    def __init__(self, state: str = "PENDING"):
        self.state = state
        self.updates: list[dict] = []

    def get_item(self, **kwargs):
        return {"Item": {"eventId": kwargs["Key"]["eventId"], "state": self.state}}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)


class FakeSqs:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.messages: list[dict] = []

    def send_message(self, **kwargs):
        if self.fail:
            raise RuntimeError("queue unavailable")
        self.messages.append(kwargs)
        return {"MessageId": "message-1"}


class FakeEvents:
    def __init__(self):
        self.entries: list[dict] = []

    def put_events(self, **kwargs):
        self.entries.extend(kwargs["Entries"])
        return {"FailedEntryCount": 0, "Entries": [{"EventId": "event-1"}]}


def test_pending_insert_is_published_then_marked_delivered(monkeypatch):
    table = FakeTable()
    sqs = FakeSqs()
    monkeypatch.setattr(h, "_table", lambda: table)
    monkeypatch.setattr(h, "_sqs_client", lambda: sqs)
    monkeypatch.setenv("ORDERS_QUEUE_URL", "https://sqs.example/orders")

    assert h.lambda_handler({"Records": [_record()]}, None) == {"batchItemFailures": []}
    assert len(sqs.messages) == 1
    assert '"totalAmount": "19.99"' in sqs.messages[0]["MessageBody"]
    assert sqs.messages[0]["MessageAttributes"]["eventType"]["StringValue"] == "order-created"
    assert table.updates[0]["Key"] == {"eventId": "order-created#ord-1"}


def test_already_delivered_record_is_not_sent_again(monkeypatch):
    table = FakeTable(state="DELIVERED")
    sqs = FakeSqs()
    monkeypatch.setattr(h, "_table", lambda: table)
    monkeypatch.setattr(h, "_sqs_client", lambda: sqs)

    assert h.lambda_handler({"Records": [_record()]}, None) == {"batchItemFailures": []}
    assert sqs.messages == []


def test_publish_failure_returns_partial_batch_identifier(monkeypatch):
    monkeypatch.setattr(h, "_table", lambda: FakeTable())
    monkeypatch.setattr(h, "_sqs_client", lambda: FakeSqs(fail=True))
    monkeypatch.setenv("ORDERS_QUEUE_URL", "https://sqs.example/orders")

    result = h.lambda_handler({"Records": [_record()]}, None)
    assert result == {"batchItemFailures": [{"itemIdentifier": "stream-record-1"}]}


def test_non_insert_stream_records_are_ignored(monkeypatch):
    sqs = FakeSqs()
    monkeypatch.setattr(h, "_sqs_client", lambda: sqs)
    assert h.lambda_handler({"Records": [_record(event_name="MODIFY")]}, None) == {
        "batchItemFailures": []
    }
    assert sqs.messages == []


def test_domain_event_is_published_to_eventbridge_then_marked_delivered(monkeypatch):
    table = FakeTable()
    events = FakeEvents()
    monkeypatch.setattr(h, "_table", lambda: table)
    monkeypatch.setattr(h, "_events_client", lambda: events)
    monkeypatch.setenv("EVENT_BUS_NAME", "smartretailx-events")

    assert h.lambda_handler({"Records": [_domain_event_record()]}, None) == {"batchItemFailures": []}
    assert events.entries[0]["Source"] == "smartretailx.orders"
    assert events.entries[0]["DetailType"] == "fulfilment-status-changed"
    assert '"fulfilmentStatus": "PACKING"' in events.entries[0]["Detail"]
    assert table.updates[0]["Key"] == {"eventId": "fulfilment-status-changed#ord-1#PACKING"}
