"""DynamoDB persistence for orders.

Access patterns this table serves (the polyglot-persistence justification,
ADR-03): get one order by id (hash key) and list a user's orders (userId-index
GSI). Neither needs a join, which is why orders are key-value and inventory is
relational.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from decimal import Decimal
from functools import wraps

import boto3
from boto3.dynamodb.conditions import Key

from .events import fulfilment_status_changed, order_cancel_requested, order_created_command
from .models import FulfilmentStatus, Order, OrderItem, OrderStatus, utcnow

logger = logging.getLogger(__name__)
_TRANSITION_LOCK = threading.Lock()


def _serialize_transition(func):
    """Serialize local competing transitions; DynamoDB conditions remain authoritative."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        with _TRANSITION_LOCK:
            return func(*args, **kwargs)
    return wrapped


class OrderNotFound(Exception):
    pass


class OrderNotPending(Exception):
    """The order already reached a terminal state."""


def _to_item(order: Order) -> dict:
    return {
        "orderId": order.orderId,
        "userId": order.userId,
        "status": order.status.value,
        "fulfilmentStatus": order.fulfilmentStatus.value,
        "items": [
            {
                "productId": item.productId,
                "productName": item.productName,
                "quantity": item.quantity,
                "baseUnitPrice": Decimal(str(item.baseUnitPrice)),
                "effectiveUnitPrice": Decimal(str(item.effectiveUnitPrice)),
                "unitDiscount": Decimal(str(item.unitDiscount)),
                "lineDiscount": Decimal(str(item.lineDiscount)),
                "lineTotal": Decimal(str(item.lineTotal)),
                **({"promotionId": item.promotionId} if item.promotionId else {}),
            }
            for item in order.items
        ],
        "totalAmount": Decimal(str(order.totalAmount)),
        "subtotal": Decimal(str(order.subtotal)),
        "discountTotal": Decimal(str(order.discountTotal)),
        "createdAt": order.createdAt.isoformat(),
        "updatedAt": order.updatedAt.isoformat(),
        **({"statusReason": order.statusReason} if order.statusReason else {}),
    }


def _from_item(item: dict) -> Order:
    def snapshot(raw: dict) -> OrderItem:
        legacy_price = Decimal(str(raw.get("unitPrice", "0")))
        quantity = int(raw["quantity"])
        return OrderItem(
            productId=raw["productId"],
            productName=raw.get("productName", raw["productId"]),
            quantity=quantity,
            baseUnitPrice=Decimal(str(raw.get("baseUnitPrice", legacy_price))),
            effectiveUnitPrice=Decimal(str(raw.get("effectiveUnitPrice", legacy_price))),
            unitDiscount=Decimal(str(raw.get("unitDiscount", "0"))),
            lineDiscount=Decimal(str(raw.get("lineDiscount", "0"))),
            lineTotal=Decimal(str(raw.get("lineTotal", legacy_price * quantity))),
            promotionId=raw.get("promotionId"),
        )

    return Order(
        orderId=item["orderId"],
        userId=item["userId"],
        status=OrderStatus(item["status"]),
        fulfilmentStatus=FulfilmentStatus(item.get("fulfilmentStatus", "NOT_STARTED")),
        items=[snapshot(raw) for raw in item.get("items", [])],
        totalAmount=Decimal(str(item["totalAmount"])),
        subtotal=Decimal(str(item.get("subtotal", item["totalAmount"]))),
        discountTotal=Decimal(str(item.get("discountTotal", "0"))),
        createdAt=datetime.fromisoformat(item["createdAt"]),
        updatedAt=datetime.fromisoformat(item["updatedAt"]),
        statusReason=item.get("statusReason"),
    )


class OrderRepository:
    def __init__(self, settings):
        self._settings = settings
        self._resource = None
        self._table = None

    @property
    def resource(self):
        if self._resource is None:
            self._resource = boto3.resource("dynamodb", **self._settings.boto_kwargs())
        return self._resource

    @property
    def table(self):
        if self._table is None:
            self._table = self.resource.Table(self._settings.orders_table_name)
        return self._table

    def put(self, order: Order) -> Order:
        self.table.put_item(Item=_to_item(order))
        return order

    def put_with_command(
        self,
        order: Order,
        correlation_id: str,
        user_email: str | None = None,
        load_test: bool = False,
    ) -> Order:
        """Atomically persist the order and its stock-reservation command.

        The resource's underlying client retains native-Python marshalling for
        TransactWriteItems. A deterministic event id makes retries collide
        instead of creating a second command.
        """
        event_id = f"order-created#{order.orderId}"
        order_item = _to_item(order)
        order_item["correlationId"] = correlation_id
        if user_email:
            order_item["userEmail"] = user_email
        outbox_item = {
            "eventId": event_id,
            "eventType": "order-created",
            "aggregateId": order.orderId,
            "state": "PENDING",
            "createdAt": order.createdAt.isoformat(),
            "payload": order_created_command(order, correlation_id, user_email, load_test),
        }
        self.resource.meta.client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": self._settings.orders_table_name,
                        "Item": order_item,
                        "ConditionExpression": "attribute_not_exists(orderId)",
                    }
                },
                {
                    "Put": {
                        "TableName": self._settings.order_outbox_table_name,
                        "Item": outbox_item,
                        "ConditionExpression": "attribute_not_exists(eventId)",
                    }
                },
            ],
            ClientRequestToken=order.orderId,
        )
        return order

    def get(self, order_id: str) -> Order | None:
        response = self.table.get_item(Key={"orderId": order_id})
        item = response.get("Item")
        return _from_item(item) if item else None

    def list_for_user(self, user_id: str, limit: int = 25) -> list[Order]:
        """Backlog item 29 - served by the userId-index GSI, not a table scan.
        A Scan would cost the whole table on every My Orders page load."""
        response = self.table.query(
            IndexName="userId-index",
            KeyConditionExpression=Key("userId").eq(user_id),
            Limit=limit,
            ScanIndexForward=False,
        )
        orders = [_from_item(item) for item in response.get("Items", [])]
        # The GSI is not sorted by time (userId is the only key), so order here.
        orders.sort(key=lambda o: o.createdAt, reverse=True)
        return orders

    def list_operations(self, limit: int = 100) -> list[Order]:
        """Bounded admin-only operational queue; customer reads use the GSI."""
        response = self.table.scan(Limit=limit)
        orders = [_from_item(item) for item in response.get("Items", [])]
        orders.sort(key=lambda order: order.updatedAt, reverse=True)
        return orders

    def set_status(
        self,
        order_id: str,
        status: OrderStatus,
        reason: str | None = None,
        only_if_pending: bool = False,
        expected_status: OrderStatus | None = None,
    ) -> Order:
        """Flip an order's status.

        Conditional on the order existing so a lost or duplicated event cannot
        create a phantom record. With `only_if_pending` the transition is also
        once-only: a late or replayed saga event cannot drag an order that is
        already CONFIRMED back to REJECTED.
        """
        expression = "SET #s = :s, updatedAt = :u"
        names = {"#s": "status"}
        values = {":s": status.value, ":u": utcnow().isoformat()}
        if reason:
            expression += ", statusReason = :r"
            values[":r"] = reason

        condition = "attribute_exists(orderId)"
        if expected_status is not None:
            condition += " AND #s = :expected"
            values[":expected"] = expected_status.value
        elif only_if_pending:
            condition += " AND #s = :pending"
            values[":pending"] = OrderStatus.PENDING.value

        try:
            response = self.table.update_item(
                Key={"orderId": order_id},
                UpdateExpression=expression,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ConditionExpression=condition,
                ReturnValues="ALL_NEW",
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            # The condition covers two distinct causes; tell them apart so the
            # consumer can ack a duplicate but retry a genuinely missing order.
            if (only_if_pending or expected_status is not None) and self.get(order_id) is not None:
                raise OrderNotPending(order_id) from exc
            raise OrderNotFound(order_id) from exc
        return _from_item(response["Attributes"])

    @_serialize_transition
    def set_fulfilment(
        self,
        order_id: str,
        expected: FulfilmentStatus,
        target: FulfilmentStatus,
        correlation_id: str = "system",
    ) -> Order:
        """Atomically progress fulfilment and store its domain event.

        The event is an EventEnvelope written to the same outbox table as the
        stock-reservation command, so an accepted delivery state can never be
        missing its notification record.
        """
        raw = self.table.get_item(Key={"orderId": order_id}).get("Item")
        if raw is None:
            raise OrderNotFound(order_id)
        current = _from_item(raw)
        user_email = raw.get("userEmail")
        updated = current.model_copy(update={"fulfilmentStatus": target, "updatedAt": utcnow()})
        event_id = f"fulfilment-status-changed#{order_id}#{target.value}"
        outbox_item = {
            "eventId": event_id,
            "eventType": "fulfilment-status-changed",
            "aggregateId": order_id,
            "destination": "EVENTBRIDGE",
            "state": "PENDING",
            "createdAt": updated.updatedAt.isoformat(),
            "payload": fulfilment_status_changed(updated, correlation_id, user_email),
        }
        try:
            self.resource.meta.client.transact_write_items(
                TransactItems=[
                    {"Update": {
                        "TableName": self._settings.orders_table_name,
                        "Key": {"orderId": order_id},
                        "UpdateExpression": "SET fulfilmentStatus = :target, updatedAt = :updated",
                        "ExpressionAttributeValues": {
                            ":target": target.value, ":updated": updated.updatedAt.isoformat(),
                            ":confirmed": OrderStatus.CONFIRMED.value, ":expected": expected.value,
                        },
                        "ConditionExpression": "#status = :confirmed AND fulfilmentStatus = :expected",
                        "ExpressionAttributeNames": {"#status": "status"},
                    }},
                    {"Put": {
                        "TableName": self._settings.order_outbox_table_name,
                        "Item": outbox_item,
                        "ConditionExpression": "attribute_not_exists(eventId)",
                    }},
                ],
                ClientRequestToken=event_id,
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise OrderNotPending(order_id) from exc
        except self.table.meta.client.exceptions.TransactionCanceledException as exc:
            if self.get(order_id) is None:
                raise OrderNotFound(order_id) from exc
            raise OrderNotPending(order_id) from exc
        return updated

    @_serialize_transition
    def request_cancellation(self, order_id: str, user_id: str, correlation_id: str, user_email: str | None = None) -> Order:
        """Race-safe CONFIRMED/PACKING-or-earlier -> CANCEL_PENDING transition."""
        current = self.get(order_id)
        if current is None:
            raise OrderNotFound(order_id)
        updated = current.model_copy(update={"status": OrderStatus.CANCEL_PENDING, "updatedAt": utcnow()})
        event_id = f"order-cancel-requested#{order_id}"
        outbox = {
            "eventId": event_id, "eventType": "order-cancel-requested", "aggregateId": order_id,
            "destination": "SQS", "state": "PENDING", "createdAt": updated.updatedAt.isoformat(),
            "payload": order_cancel_requested(updated, correlation_id, user_email),
        }
        try:
            self.resource.meta.client.transact_write_items(
                TransactItems=[
                    {"Update": {"TableName": self._settings.orders_table_name, "Key": {"orderId": order_id},
                     "UpdateExpression": "SET #status = :cancel, updatedAt = :updated",
                     "ConditionExpression": "#status = :confirmed AND userId = :user AND fulfilmentStatus IN (:not_started, :packing)",
                     "ExpressionAttributeNames": {"#status": "status"},
                     "ExpressionAttributeValues": {":cancel": OrderStatus.CANCEL_PENDING.value, ":updated": updated.updatedAt.isoformat(),
                         ":confirmed": OrderStatus.CONFIRMED.value, ":user": user_id,
                         ":not_started": FulfilmentStatus.NOT_STARTED.value, ":packing": FulfilmentStatus.PACKING.value}}},
                    {"Put": {"TableName": self._settings.order_outbox_table_name, "Item": outbox,
                     "ConditionExpression": "attribute_not_exists(eventId)"}},
                ], ClientRequestToken=event_id,
            )
        except self.table.meta.client.exceptions.TransactionCanceledException as exc:
            if self.get(order_id) is None:
                raise OrderNotFound(order_id) from exc
            raise OrderNotPending(order_id) from exc
        return updated
