"""DynamoDB persistence for orders.

Access patterns this table serves (the polyglot-persistence justification,
ADR-03): get one order by id (hash key) and list a user's orders (userId-index
GSI). Neither needs a join, which is why orders are key-value and inventory is
relational.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from .models import Order, OrderItem, OrderStatus, utcnow

logger = logging.getLogger(__name__)


class OrderNotFound(Exception):
    pass


def _to_item(order: Order) -> dict:
    return {
        "orderId": order.orderId,
        "userId": order.userId,
        "status": order.status.value,
        "items": [
            {
                "productId": item.productId,
                "quantity": item.quantity,
                # str() first: Decimal(float) would reintroduce binary error.
                "unitPrice": Decimal(str(item.unitPrice)),
            }
            for item in order.items
        ],
        "totalAmount": Decimal(str(order.totalAmount)),
        "createdAt": order.createdAt.isoformat(),
        "updatedAt": order.updatedAt.isoformat(),
        **({"statusReason": order.statusReason} if order.statusReason else {}),
    }


def _from_item(item: dict) -> Order:
    return Order(
        orderId=item["orderId"],
        userId=item["userId"],
        status=OrderStatus(item["status"]),
        items=[
            OrderItem(
                productId=raw["productId"],
                quantity=int(raw["quantity"]),
                unitPrice=Decimal(str(raw["unitPrice"])),
            )
            for raw in item.get("items", [])
        ],
        totalAmount=Decimal(str(item["totalAmount"])),
        createdAt=datetime.fromisoformat(item["createdAt"]),
        updatedAt=datetime.fromisoformat(item["updatedAt"]),
        statusReason=item.get("statusReason"),
    )


class OrderRepository:
    def __init__(self, settings):
        self._settings = settings
        self._table = None

    @property
    def table(self):
        if self._table is None:
            resource = boto3.resource("dynamodb", **self._settings.boto_kwargs())
            self._table = resource.Table(self._settings.orders_table_name)
        return self._table

    def put(self, order: Order) -> Order:
        self.table.put_item(Item=_to_item(order))
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

    def set_status(self, order_id: str, status: OrderStatus, reason: str | None = None) -> Order:
        """Used by the saga compensation consumer to flip PENDING -> REJECTED
        (or CONFIRMED). Conditional on the order existing so a lost/duplicated
        event cannot create a phantom record."""
        expression = "SET #s = :s, updatedAt = :u"
        names = {"#s": "status"}
        values = {":s": status.value, ":u": utcnow().isoformat()}
        if reason:
            expression += ", statusReason = :r"
            values[":r"] = reason

        try:
            response = self.table.update_item(
                Key={"orderId": order_id},
                UpdateExpression=expression,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ConditionExpression="attribute_exists(orderId)",
                ReturnValues="ALL_NEW",
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise OrderNotFound(order_id) from exc
        return _from_item(response["Attributes"])
