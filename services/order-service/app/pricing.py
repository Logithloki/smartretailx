"""Read-only Product/Promotion pricing read model for Order Service."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from srx_common import Promotion, effective_price, money

from .models import OrderItem, OrderLineRequest


class ProductUnavailable(Exception):
    pass


class PricingUnavailable(Exception):
    """The authoritative product/promotion read could not complete."""


@dataclass(frozen=True)
class PricedOrder:
    items: list[OrderItem]
    subtotal: Decimal
    discount_total: Decimal
    total_amount: Decimal


class PricingCatalog:
    """Read only, narrowly authorised query boundary for Order pricing."""

    def __init__(self, settings):
        self._settings = settings
        self._resource = None

    @property
    def resource(self):
        if self._resource is None:
            self._resource = boto3.resource("dynamodb", **self._settings.boto_kwargs())
        return self._resource

    def _active_promotions(self, now: datetime) -> list[Promotion]:
        table = self.resource.Table(self._settings.promotions_table_name)
        kwargs = {
            "IndexName": "enabled-startsAt-index",
            "KeyConditionExpression": Key("enabled").eq("true") & Key("startsAt").lte(now.isoformat()),
        }
        items: list[dict] = []
        while True:
            try:
                response = table.query(**kwargs)
            except Exception as exc:
                raise PricingUnavailable("promotion query failed") from exc
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key

        return [
            Promotion(
                promotion_id=item["promotionId"],
                discount_percent=Decimal(str(item["discountPercent"])),
                scope=item["scope"],
                product_ids=tuple(item.get("productIds", [])),
                category=item.get("category"),
                enabled=item.get("enabled") == "true",
                starts_at=datetime.fromisoformat(item["startsAt"]),
                ends_at=datetime.fromisoformat(item["endsAt"]),
            )
            for item in items
            if datetime.fromisoformat(item["endsAt"]) > now
        ]

    def _batch_get_products(self, product_ids: list[str]) -> dict[str, dict]:
        request_items = {
            self._settings.products_table_name: {
                "Keys": [{"productId": product_id} for product_id in product_ids]
            }
        }
        products: dict[str, dict] = {}
        for attempt in range(4):
            try:
                response = self.resource.meta.client.batch_get_item(RequestItems=request_items)
            except Exception as exc:
                raise PricingUnavailable("product lookup failed") from exc
            products.update({
                item["productId"]: item
                for item in response.get("Responses", {}).get(self._settings.products_table_name, [])
            })
            unprocessed = response.get("UnprocessedKeys") or {}
            if not unprocessed:
                return products
            request_items = unprocessed
            if attempt < 3:
                time.sleep(0.05 * (2**attempt))
        raise PricingUnavailable("product lookup remained incomplete after retries")

    def quote(self, lines: list[OrderLineRequest], now: datetime | None = None) -> PricedOrder:
        now = now or datetime.now(UTC)
        requested_ids = list(dict.fromkeys(line.productId for line in lines))
        products = self._batch_get_products(requested_ids)
        promotions = self._active_promotions(now)
        snapshots: list[OrderItem] = []
        for line in lines:
            product = products.get(line.productId)
            if product is None or product.get("active", True) is False:
                raise ProductUnavailable(line.productId)
            quote = effective_price(
                base_price=Decimal(str(product["price"])),
                product_id=line.productId,
                category=product.get("category", "uncategorised"),
                promotions=promotions,
                now=now,
            )
            line_discount = money(quote.unit_discount * line.quantity)
            snapshots.append(
                OrderItem(
                    productId=line.productId,
                    productName=product.get("productName", line.productId),
                    quantity=line.quantity,
                    baseUnitPrice=quote.base_unit_price,
                    effectiveUnitPrice=quote.effective_unit_price,
                    unitDiscount=quote.unit_discount,
                    lineDiscount=line_discount,
                    lineTotal=money(quote.effective_unit_price * line.quantity),
                    promotionId=quote.promotion_id,
                )
            )
        subtotal = money(sum((item.baseUnitPrice * item.quantity for item in snapshots), Decimal("0")))
        discount_total = money(sum((item.lineDiscount for item in snapshots), Decimal("0")))
        return PricedOrder(snapshots, subtotal, discount_total, money(subtotal - discount_total))
