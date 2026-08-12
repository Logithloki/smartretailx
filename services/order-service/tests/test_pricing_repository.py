from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import OrderLineRequest
from app.pricing import PricingCatalog


NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class FakePromotionsTable:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.pages)


class FakeDynamoClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def batch_get_item(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


def _product(product_id: str, price: str = "10.00") -> dict:
    return {"productId": product_id, "productName": product_id, "price": Decimal(price), "category": "general", "active": True}


def _promotion(promotion_id: str) -> dict:
    return {
        "promotionId": promotion_id,
        "discountPercent": Decimal("10"),
        "scope": "PRODUCT",
        "productIds": ["p1"],
        "enabled": "true",
        "startsAt": "2026-08-01T00:00:00+00:00",
        "endsAt": "2026-09-01T00:00:00+00:00",
    }


def _catalog(promotions, product_responses):
    catalog = PricingCatalog(SimpleNamespace(
        products_table_name="products",
        promotions_table_name="promotions",
        boto_kwargs=lambda: {},
    ))
    client = FakeDynamoClient(product_responses)
    catalog._resource = SimpleNamespace(
        Table=lambda _: promotions,
        meta=SimpleNamespace(client=client),
    )
    return catalog, client


def test_active_promotions_are_read_across_all_query_pages():
    promotions = FakePromotionsTable([
        {"Items": [_promotion("promo-1")], "LastEvaluatedKey": {"promotionId": "promo-1"}},
        {"Items": [_promotion("promo-2")]},
    ])
    catalog, _ = _catalog(promotions, [{"Responses": {"products": [_product("p1")]}}])

    priced = catalog.quote([OrderLineRequest(productId="p1", quantity=1)], now=NOW)

    assert len(promotions.calls) == 2
    assert priced.items[0].promotionId == "promo-2"


def test_batch_get_retries_unprocessed_keys_and_preserves_all_products():
    promotions = FakePromotionsTable([{"Items": []}])
    catalog, client = _catalog(promotions, [
        {"Responses": {"products": [_product("p1")]}, "UnprocessedKeys": {"products": {"Keys": [{"productId": "p2"}]} }},
        {"Responses": {"products": [_product("p2", "20.00")]}},
    ])

    priced = catalog.quote([
        OrderLineRequest(productId="p1", quantity=1),
        OrderLineRequest(productId="p2", quantity=1),
    ], now=NOW)

    assert len(client.calls) == 2
    assert [item.productId for item in priced.items] == ["p1", "p2"]


def test_batch_get_fails_closed_when_keys_remain_unprocessed():
    promotions = FakePromotionsTable([{"Items": []}])
    catalog, _ = _catalog(promotions, [
        {"Responses": {}, "UnprocessedKeys": {"products": {"Keys": [{"productId": "p1"}]} }},
    ] * 5)

    with pytest.raises(Exception) as raised:
        catalog.quote([OrderLineRequest(productId="p1", quantity=1)], now=NOW)
    assert raised.value.__class__.__name__ == "PricingUnavailable"
