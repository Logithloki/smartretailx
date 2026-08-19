from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json

import boto3
import jwt
import pytest

from app.events import LocalInlineOutboxPublisher
from app.models import FulfilmentStatus, Order, OrderItem, OrderLineRequest, OrderStatus
from app.pricing import PricingCatalog
from app.services import OrderNotFound

from conftest import OUTBOX_TABLE, auth_header


def _payload(quantity: int = 2, product_id: str = "prod-laptop-001") -> dict:
    return {"items": [{"productId": product_id, "quantity": quantity}]}


# --------------------------------------------------------------------------
# health + versioning
# --------------------------------------------------------------------------

def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_http_correlation_id_is_accepted_and_returned(client):
    response = client.get("/health", headers={"X-Correlation-ID": "corr-http-42"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-http-42"


def test_orders_live_under_v1(client):
    assert client.post("/orders", json=_payload(), headers=auth_header()).status_code == 404


def test_openapi_contract_exposes_canonical_order_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/orders" in paths
    assert "/v1/orders/{order_id}" in paths
    assert all(not path.startswith("/api/") for path in paths)


# --------------------------------------------------------------------------
# order creation
# --------------------------------------------------------------------------

def test_client_supplied_unit_price_is_rejected_fail_closed(client):
    """Changing the browser request must never become a price override."""
    response = client.post(
        "/v1/orders",
        json={"items": [{"productId": "prod-laptop-001", "quantity": 1, "unitPrice": "0.01"}]},
        headers=auth_header(),
    )

    assert response.status_code == 422

def test_create_order_returns_pending(client):
    response = client.post("/v1/orders", json=_payload(), headers=auth_header())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == OrderStatus.PENDING.value
    assert body["orderId"].startswith("ord-")


def test_server_prices_order_from_catalogue_snapshot(client):
    body = client.post("/v1/orders", json=_payload(quantity=3), headers=auth_header()).json()
    assert body["subtotal"] == "59.97"
    assert body["discountTotal"] == "0.00"
    assert body["totalAmount"] == "59.97"
    assert body["items"][0]["effectiveUnitPrice"] == "19.99"


def test_stale_browser_price_cannot_override_the_authoritative_product_record(client, pricing_tables):
    """The customer may have seen A, but checkout snapshots the current B."""
    products, _ = pricing_tables
    observed = products.get_item(Key={"productId": "prod-laptop-001"})["Item"]["price"]
    assert observed == Decimal("19.99")
    products.update_item(
        Key={"productId": "prod-laptop-001"},
        UpdateExpression="SET price = :price",
        ExpressionAttributeValues={":price": Decimal("24.99")},
    )

    response = client.post("/v1/orders", json=_payload(quantity=1), headers=auth_header())
    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["baseUnitPrice"] == "24.99"
    assert item["effectiveUnitPrice"] == "24.99"


def test_authoritative_promotion_price_is_snapshotted_after_the_product_changes(client, pricing_tables):
    products, promotions = pricing_tables
    now = datetime.now(UTC)
    products.update_item(
        Key={"productId": "prod-laptop-001"},
        UpdateExpression="SET price = :price",
        ExpressionAttributeValues={":price": Decimal("30.00")},
    )
    promotions.put_item(Item={
        "promotionId": "promo-authoritative", "discountPercent": Decimal("10"),
        "scope": "PRODUCT", "productIds": ["prod-laptop-001"], "enabled": "true",
        "startsAt": (now - timedelta(minutes=1)).isoformat(),
        "endsAt": (now + timedelta(minutes=1)).isoformat(),
    })

    item = client.post("/v1/orders", json=_payload(quantity=1), headers=auth_header()).json()["items"][0]
    assert item == {
        "productId": "prod-laptop-001", "productName": "Laptop", "quantity": 1,
        "baseUnitPrice": "30.00", "effectiveUnitPrice": "27.00", "unitDiscount": "3.00",
        "lineDiscount": "3.00", "lineTotal": "27.00", "promotionId": "promo-authoritative",
    }


def test_promotion_window_is_authoritative_even_if_no_websocket_event_arrived(settings, pricing_tables):
    _, promotions = pricing_tables
    starts_at = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
    promotions.put_item(Item={
        "promotionId": "promo-boundary", "discountPercent": Decimal("10"), "scope": "PRODUCT",
        "productIds": ["prod-laptop-001"], "enabled": "true", "lifecycleState": "SCHEDULED",
        "startsAt": starts_at.isoformat(), "endsAt": (starts_at + timedelta(minutes=10)).isoformat(),
    })
    catalog = PricingCatalog(settings)
    request = [OrderLineRequest(productId="prod-laptop-001", quantity=1)]

    before = catalog.quote(request, now=starts_at - timedelta(microseconds=1))
    at_start = catalog.quote(request, now=starts_at)
    at_end = catalog.quote(request, now=starts_at + timedelta(minutes=10))
    assert before.items[0].effectiveUnitPrice == Decimal("19.99")
    assert at_start.items[0].effectiveUnitPrice == Decimal("17.99")
    assert at_end.items[0].effectiveUnitPrice == Decimal("19.99")


def test_money_keeps_exact_decimal_precision(client):
    """0.1 + 0.2 must be 0.30, not 0.30000000000000004."""
    payload = {
        "items": [
            {"productId": "a", "quantity": 1},
            {"productId": "b", "quantity": 1},
        ]
    }
    body = client.post("/v1/orders", json=payload, headers=auth_header()).json()
    assert body["totalAmount"] == "0.30"


def test_order_is_persisted_to_dynamodb(client, repository):
    order_id = client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]
    stored = repository.get(order_id)
    assert stored is not None
    assert stored.status is OrderStatus.PENDING
    assert stored.totalAmount == Decimal("39.98")


def test_order_is_owned_by_the_token_subject_not_a_request_field(client, repository):
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header(sub="alice")
    ).json()["orderId"]
    assert repository.get(order_id).userId == "alice"


# --------------------------------------------------------------------------
# Pydantic is the validation layer (ADR-02: HTTP API v2 has no validators)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [
        {"items": []},
        {"items": [{"productId": "p", "quantity": 0}]},
        {"items": [{"productId": "p", "quantity": -1}]},
        {"items": [{"productId": "", "quantity": 1}]},
        {"items": [{"productId": "p", "quantity": 101}]},
        {"wrong": "shape"},
    ],
)
def test_invalid_payloads_are_rejected_with_422(client, payload):
    assert client.post("/v1/orders", json=payload, headers=auth_header()).status_code == 422


def test_more_than_twenty_line_items_is_rejected(client):
    payload = {
        "items": [
            {"productId": f"p{i}", "quantity": 1} for i in range(21)
        ]
    }
    assert client.post("/v1/orders", json=payload, headers=auth_header()).status_code == 422


# --------------------------------------------------------------------------
# transactional outbox
# --------------------------------------------------------------------------

def test_order_creation_persists_command_in_outbox(client):
    order_id = client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]

    outbox = boto3.resource("dynamodb", region_name="eu-west-1").Table(OUTBOX_TABLE)
    record = outbox.get_item(Key={"eventId": f"order-created#{order_id}"})["Item"]
    assert record["eventType"] == "order-created"
    assert record["state"] == "PENDING"
    assert record["payload"]["aggregateId"] == order_id
    assert record["payload"]["payload"]["orderId"] == order_id


def test_outbox_amounts_are_exact_decimals(client):
    order_id = client.post(
        "/v1/orders", json=_payload(product_id="a"), headers=auth_header()
    ).json()["orderId"]
    outbox = boto3.resource("dynamodb", region_name="eu-west-1").Table(OUTBOX_TABLE)
    envelope = outbox.get_item(Key={"eventId": f"order-created#{order_id}"})["Item"]["payload"]
    assert envelope["payload"]["items"][0]["effectiveUnitPrice"] == "0.10"


def test_local_outbox_relay_serializes_dynamodb_decimals_before_sqs_delivery(settings, client):
    """A DynamoDB-read order command remains valid JSON at the SQS boundary."""
    order_id = client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]

    LocalInlineOutboxPublisher(settings).publish(f"order-created#{order_id}")

    message = boto3.client("sqs", region_name="eu-west-1").receive_message(
        QueueUrl=settings.orders_queue_url,
    )["Messages"][0]
    envelope = json.loads(message["Body"])
    assert envelope["eventType"] == "order-created"
    assert envelope["payload"] == {
        "orderId": order_id,
        "userId": "user-1",
        "userEmail": None,
        "loadTest": False,
        "totalAmount": "39.98",
        "items": [{
            "productId": "prod-laptop-001",
            "quantity": "2",
            "effectiveUnitPrice": "19.99",
        }],
    }


def test_order_and_outbox_write_are_atomic(settings, repository):
    order = Order(
        userId="u", items=[OrderItem(
            productId="p", productName="P", quantity=1,
            baseUnitPrice=Decimal("1.00"), effectiveUnitPrice=Decimal("1.00"),
            unitDiscount=Decimal("0"), lineDiscount=Decimal("0"), lineTotal=Decimal("1.00"),
        )],
        subtotal=Decimal("1.00"), discountTotal=Decimal("0"),
        totalAmount=Decimal("1.00"),
    )
    outbox = boto3.resource("dynamodb", region_name="eu-west-1").Table(OUTBOX_TABLE)
    outbox.put_item(Item={"eventId": f"order-created#{order.orderId}", "state": "BLOCKING"})

    with pytest.raises(repository.table.meta.client.exceptions.TransactionCanceledException):
        repository.put_with_command(order, correlation_id="correlation-1")

    assert repository.get(order.orderId) is None


# --------------------------------------------------------------------------
# reads (backlog item 29)
# --------------------------------------------------------------------------

def test_list_returns_only_the_callers_own_orders(client):
    client.post("/v1/orders", json=_payload(), headers=auth_header(sub="alice"))
    client.post("/v1/orders", json=_payload(), headers=auth_header(sub="alice"))
    client.post("/v1/orders", json=_payload(), headers=auth_header(sub="bob"))

    alice = client.get("/v1/orders", headers=auth_header(sub="alice")).json()
    bob = client.get("/v1/orders", headers=auth_header(sub="bob")).json()

    assert alice["count"] == 2
    assert bob["count"] == 1
    assert all(o["userId"] == "alice" for o in alice["orders"])


def test_get_own_order(client):
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header(sub="alice")
    ).json()["orderId"]
    assert client.get(f"/v1/orders/{order_id}", headers=auth_header(sub="alice")).status_code == 200


def test_another_users_order_is_404_not_403(client):
    """403 would confirm the id exists. 404 leaks nothing."""
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header(sub="alice")
    ).json()["orderId"]
    response = client.get(f"/v1/orders/{order_id}", headers=auth_header(sub="bob"))
    assert response.status_code == 404


def test_admin_may_read_any_order(client):
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header(sub="alice")
    ).json()["orderId"]
    response = client.get(
        f"/v1/orders/{order_id}", headers=auth_header("bob", "customer", "admin")
    )
    assert response.status_code == 200


def test_only_admin_can_view_bounded_operations_queue(client):
    client.post("/v1/orders", json=_payload(), headers=auth_header(sub="alice"))
    assert client.get("/v1/orders/operations", headers=auth_header()).status_code == 403
    response = client.get("/v1/orders/operations", headers=auth_header("ops", "admin"))
    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_unknown_order_is_404(client):
    assert client.get("/v1/orders/ord-doesnotexist", headers=auth_header()).status_code == 404


def test_list_limit_is_validated(client):
    assert client.get("/v1/orders?limit=0", headers=auth_header()).status_code == 422
    assert client.get("/v1/orders?limit=101", headers=auth_header()).status_code == 422


# --------------------------------------------------------------------------
# status transitions (used by the saga in Week 3)
# --------------------------------------------------------------------------

def test_set_status_updates_and_records_a_reason(client, repository):
    order_id = client.post(
        "/v1/orders", json=_payload(), headers=auth_header()
    ).json()["orderId"]

    updated = repository.set_status(order_id, OrderStatus.REJECTED, reason="insufficient stock")
    assert updated.status is OrderStatus.REJECTED
    assert updated.statusReason == "insufficient stock"
    assert repository.get(order_id).status is OrderStatus.REJECTED


def test_set_status_on_a_missing_order_raises_rather_than_creating_one(repository):
    """update_item would upsert by default - the condition expression stops a
    stray event from conjuring an order that was never placed."""
    with pytest.raises(OrderNotFound):
        repository.set_status("ord-ghost", OrderStatus.CONFIRMED)


def test_only_admin_can_progress_confirmed_order_fulfilment(client, repository):
    order_id = client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]
    repository.set_status(order_id, OrderStatus.CONFIRMED, only_if_pending=True)

    customer = client.patch(
        f"/v1/orders/{order_id}/fulfilment", json={"status": "PACKING"}, headers=auth_header()
    )
    admin = client.patch(
        f"/v1/orders/{order_id}/fulfilment", json={"status": "PACKING"},
        headers=auth_header("admin-1", "admin"),
    )

    assert customer.status_code == 403
    assert admin.status_code == 200
    assert admin.json()["fulfilmentStatus"] == FulfilmentStatus.PACKING.value
    outbox = boto3.resource("dynamodb", region_name="eu-west-1").Table(OUTBOX_TABLE)
    event = outbox.get_item(Key={"eventId": f"fulfilment-status-changed#{order_id}#PACKING"})["Item"]
    assert event["destination"] == "EVENTBRIDGE"
    assert event["payload"]["eventType"] == "fulfilment-status-changed"
    assert event["payload"]["payload"] == {
        "orderId": order_id, "userId": "user-1", "fulfilmentStatus": "PACKING", "userEmail": None,
    }


def test_unknown_fulfilment_order_returns_404_instead_of_500(client):
    response = client.patch(
        "/v1/orders/ord-ghost/fulfilment",
        json={"status": "PACKING"},
        headers=auth_header("admin-1", "admin"),
    )
    assert response.status_code == 404


def test_unknown_cancellation_order_returns_404_instead_of_500(client):
    response = client.post("/v1/orders/ord-ghost/cancel", headers=auth_header())
    assert response.status_code == 404


def test_wrong_state_fulfilment_returns_409(client):
    order_id = client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]
    response = client.patch(
        f"/v1/orders/{order_id}/fulfilment",
        json={"status": "PACKING"},
        headers=auth_header("admin-1", "admin"),
    )
    assert response.status_code == 409


def test_pending_cancellation_returns_409(client):
    order_id = client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]
    response = client.post(f"/v1/orders/{order_id}/cancel", headers=auth_header())
    assert response.status_code == 409


def test_duplicate_product_lines_are_aggregated_once(client):
    response = client.post(
        "/v1/orders",
        json={"items": [
            {"productId": "prod-laptop-001", "quantity": 1},
            {"productId": "prod-laptop-001", "quantity": 2},
        ]},
        headers=auth_header(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["items"] == [{
        "productId": "prod-laptop-001",
        "productName": "Laptop",
        "quantity": 3,
        "baseUnitPrice": "19.99",
        "effectiveUnitPrice": "19.99",
        "unitDiscount": "0.00",
        "lineDiscount": "0.00",
        "lineTotal": "59.97",
        "promotionId": None,
    }]


def test_cancellation_and_dispatch_race_allows_exactly_one_transition(client, repository):
    order_id = client.post("/v1/orders", json=_payload(), headers=auth_header()).json()["orderId"]
    repository.set_status(order_id, OrderStatus.CONFIRMED, only_if_pending=True)
    repository.set_fulfilment(order_id, FulfilmentStatus.NOT_STARTED, FulfilmentStatus.PACKING)

    from concurrent.futures import ThreadPoolExecutor

    def cancel() -> str:
        try:
            repository.request_cancellation(order_id, "user-1", "cancel-race")
            return "cancelled"
        except Exception:
            return "blocked"

    def dispatch() -> str:
        try:
            repository.set_fulfilment(order_id, FulfilmentStatus.PACKING, FulfilmentStatus.DISPATCHED)
            return "dispatched"
        except Exception:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = set(pool.map(lambda action: action(), (cancel, dispatch)))

    final = repository.get(order_id)
    assert results in ({"cancelled", "blocked"}, {"dispatched", "blocked"})
    assert not (final.status is OrderStatus.CANCEL_PENDING and final.fulfilmentStatus is FulfilmentStatus.DISPATCHED)


def test_user_email_stored_on_order_item_and_threaded_through_fulfilment(client, repository):
    """userEmail is event-carried state for fulfilment notifications."""
    token = jwt.encode(
        {"sub": "user-email-test", "cognito:username": "user-email-test",
         "cognito:groups": ["customer"], "email": "buyer@example.com"},
        "unused", algorithm="HS256",
    )
    order_id = client.post(
        "/v1/orders", json=_payload(), headers={"Authorization": f"Bearer {token}"}
    ).json()["orderId"]

    raw = repository.table.get_item(Key={"orderId": order_id})["Item"]
    assert raw["userEmail"] == "buyer@example.com"

    repository.set_status(order_id, OrderStatus.CONFIRMED, only_if_pending=True)
    repository.set_fulfilment(order_id, FulfilmentStatus.NOT_STARTED, FulfilmentStatus.PACKING)

    outbox = boto3.resource("dynamodb", region_name="eu-west-1").Table(OUTBOX_TABLE)
    event = outbox.get_item(Key={"eventId": f"fulfilment-status-changed#{order_id}#PACKING"})["Item"]
    assert event["payload"]["payload"]["userEmail"] == "buyer@example.com"
