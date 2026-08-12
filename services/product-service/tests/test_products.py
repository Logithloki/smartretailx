from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.cache import ProductCache

from conftest import auth_header

CUSTOMER = auth_header("alice", "customer")
ADMIN = auth_header("root", "customer", "admin")


def new_product(product_id: str = "prod-new-009") -> dict:
    return {
        "productId": product_id,
        "productName": "Desk Lamp",
        "price": "24.50",
        "category": "Home",
    }


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------

def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_openapi_contract_exposes_canonical_product_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/products" in paths
    assert "/v1/products/{product_id}" in paths
    assert all(not path.startswith("/api/") for path in paths)


def test_list_products(client):
    response = client.get("/v1/products", headers=CUSTOMER)
    assert response.status_code == 200
    assert response.json()["count"] == 3


def test_list_by_category_uses_the_gsi(client):
    response = client.get("/v1/products?category=Electronics", headers=CUSTOMER)
    assert response.json()["count"] == 2


def test_get_one_product(client):
    response = client.get("/v1/products/prod-laptop-001", headers=CUSTOMER)
    assert response.status_code == 200
    assert response.json()["price"] == "1299.99"


def test_active_product_promotion_returns_effective_price(client, promotions_table):
    now = datetime.now(UTC)
    promotions_table.put_item(Item={
        "promotionId": "promo-laptop-10",
        "name": "Laptop launch offer",
        "discountPercent": Decimal("10"),
        "scope": "PRODUCT",
        "productIds": ["prod-laptop-001"],
        "enabled": "true",
        "startsAt": (now - timedelta(minutes=1)).isoformat(),
        "endsAt": (now + timedelta(minutes=1)).isoformat(),
    })

    body = client.get("/v1/products/prod-laptop-001", headers=CUSTOMER).json()
    assert body["basePrice"] == "1299.99"
    assert body["effectivePrice"] == "1169.99"
    assert body["promotion"]["promotionId"] == "promo-laptop-10"


# --------------------------------------------------------------------------
# promotions: Product Service owns writes; request-time pricing remains truth
# --------------------------------------------------------------------------

def new_promotion(promotion_id: str = "promo-home-10", **overrides) -> dict:
    now = datetime.now(UTC)
    payload = {
        "promotionId": promotion_id,
        "name": "Home launch offer",
        "discountPercent": "10",
        "scope": "PRODUCT",
        "productIds": ["prod-laptop-001"],
        "startsAt": (now + timedelta(minutes=5)).isoformat(),
        "endsAt": (now + timedelta(hours=1)).isoformat(),
        "enabled": True,
    }
    return payload | overrides


def test_only_admin_can_create_a_promotion(client):
    assert client.post("/v1/promotions", json=new_promotion(), headers=CUSTOMER).status_code == 403
    response = client.post("/v1/promotions", json=new_promotion(), headers=ADMIN)
    assert response.status_code == 201
    assert response.json()["lifecycleState"] == "SCHEDULED"


def test_promotion_crud_is_validated_and_admin_only(client):
    created = client.post("/v1/promotions", json=new_promotion(), headers=ADMIN)
    assert created.status_code == 201

    read = client.get("/v1/promotions", headers=ADMIN)
    assert read.status_code == 200
    assert read.json()["count"] == 1

    assert client.put(
        "/v1/promotions/promo-home-10", json={"discountPercent": "15"}, headers=CUSTOMER
    ).status_code == 403
    updated = client.put(
        "/v1/promotions/promo-home-10", json={"discountPercent": "15"}, headers=ADMIN
    )
    assert updated.status_code == 200
    assert updated.json()["discountPercent"] == "15.00"


def test_lifecycle_reconcile_is_multi_task_safe(repository):
    now = datetime.now(UTC)
    repository.create_promotion_from_payload(new_promotion(
        "promo-race", startsAt=(now - timedelta(seconds=1)).isoformat(),
        endsAt=(now + timedelta(hours=1)).isoformat(),
    ), now=now - timedelta(minutes=1))

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: repository.reconcile_promotions(now), range(4)))

    assert sum(result.transitions for result in results) == 1
    promotion = repository.get_promotion("promo-race")
    assert promotion["lifecycleState"] == "ACTIVE"
    assert promotion["lifecycleVersion"] == 1


def test_authoritative_price_respects_the_half_open_time_boundary(client, promotions_table):
    now = datetime.now(UTC)
    promotions_table.put_item(Item={
        "promotionId": "promo-boundary", "name": "Boundary", "discountPercent": Decimal("10"),
        "scope": "PRODUCT", "productIds": ["prod-laptop-001"], "enabled": "true",
        "lifecycleState": "SCHEDULED", "startsAt": (now + timedelta(minutes=5)).isoformat(),
        "endsAt": (now + timedelta(hours=1)).isoformat(),
    })

    product = client.get("/v1/products/prod-laptop-001", headers=CUSTOMER).json()
    assert product["effectivePrice"] == "1299.99"


def test_unknown_product_is_404(client):
    assert client.get("/v1/products/ghost", headers=CUSTOMER).status_code == 404


def test_reads_require_authentication(client):
    """ENV=local falls back to the stub principal, so assert the dependency is
    wired by checking a production-mode app rejects an anonymous read."""
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    prod = TestClient(create_app(settings=Settings(env="production", _env_file=None)))
    assert prod.get("/v1/products").status_code == 401


# --------------------------------------------------------------------------
# the X-Cache header
# --------------------------------------------------------------------------

def test_first_read_is_a_miss_and_the_second_is_a_hit(client):
    first = client.get("/v1/products/prod-laptop-001", headers=CUSTOMER)
    second = client.get("/v1/products/prod-laptop-001", headers=CUSTOMER)
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"


def test_list_is_cached_per_category_and_limit(client):
    assert client.get("/v1/products", headers=CUSTOMER).headers["X-Cache"] == "MISS"
    assert client.get("/v1/products", headers=CUSTOMER).headers["X-Cache"] == "HIT"
    # A different query is a different key, so it must miss.
    assert (
        client.get("/v1/products?category=Home", headers=CUSTOMER).headers["X-Cache"] == "MISS"
    )


def test_cache_serves_reads_without_touching_dynamodb(client, repository):
    client.get("/v1/products/prod-laptop-001", headers=CUSTOMER)
    calls = {"n": 0}
    original = repository.get

    def counting_get(product_id):
        calls["n"] += 1
        return original(product_id)

    repository.get = counting_get
    assert client.get("/v1/products/prod-laptop-001", headers=CUSTOMER).headers["X-Cache"] == "HIT"
    assert calls["n"] == 0


def test_404s_are_not_cached(client, repository):
    """A product created moments after a 404 must not stay invisible for the
    whole TTL."""
    assert client.get("/v1/products/prod-new-009", headers=CUSTOMER).status_code == 404
    client.post("/v1/products", json=new_product(), headers=ADMIN)
    assert client.get("/v1/products/prod-new-009", headers=CUSTOMER).status_code == 200


# --------------------------------------------------------------------------
# staleness and invalidation
# --------------------------------------------------------------------------

def test_write_invalidates_this_tasks_cache_immediately(client):
    """The admin who made the change must see it at once."""
    client.get("/v1/products/prod-mouse-002", headers=CUSTOMER)  # warm
    client.put("/v1/products/prod-mouse-002", json={"price": "59.99"}, headers=ADMIN)

    response = client.get("/v1/products/prod-mouse-002", headers=CUSTOMER)
    assert response.headers["X-Cache"] == "MISS"
    assert response.json()["price"] == "59.99"


def test_price_update_marks_one_public_refresh_then_clears_it(repository):
    calls: list[dict] = []
    original = repository.table.update_item

    def recording_update(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    repository.table.update_item = recording_update

    updated = repository.update("prod-mouse-002", {"price": "58.00"})

    assert updated.price == Decimal("58.00")
    assert len(calls) == 2
    assert ":pending" in calls[0]["ExpressionAttributeValues"]
    assert calls[0]["ExpressionAttributeValues"][":pending"] == "true"
    assert "priceEventVersion" in calls[0]["UpdateExpression"]
    assert calls[1]["ExpressionAttributeValues"][":cleared"] == "false"
    stored = repository.table.get_item(Key={"productId": "prod-mouse-002"})["Item"]
    assert stored["priceEventPending"] == "false"
    assert stored["priceEventVersion"] == 1


def test_non_price_update_does_not_create_a_price_refresh_marker(repository):
    calls: list[dict] = []
    original = repository.table.update_item

    def recording_update(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    repository.table.update_item = recording_update

    repository.update("prod-mouse-002", {"description": "Quiet wireless mouse"})

    assert len(calls) == 1
    assert "priceEventPending" not in calls[0]["UpdateExpression"]
    stored = repository.table.get_item(Key={"productId": "prod-mouse-002"})["Item"]
    assert "priceEventVersion" not in stored


def test_delete_invalidates_the_cache(client):
    client.get("/v1/products/prod-mouse-002", headers=CUSTOMER)
    client.delete("/v1/products/prod-mouse-002", headers=ADMIN)
    assert client.get("/v1/products/prod-mouse-002", headers=CUSTOMER).status_code == 404


def test_entries_expire_after_the_ttl():
    """Bounded staleness: another task's write becomes visible within the TTL."""
    cache = ProductCache(maxsize=10, ttl=1)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    time.sleep(1.1)
    assert cache.get("k") is None


def test_cache_evicts_when_full():
    cache = ProductCache(maxsize=2, ttl=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.size == 2


def test_cache_counts_hits_and_misses():
    cache = ProductCache(maxsize=10, ttl=60)
    cache.get("absent")
    cache.set("present", 1)
    cache.get("present")
    assert (cache.hits, cache.misses) == (1, 1)


# --------------------------------------------------------------------------
# admin CRUD + RBAC (backlog item 28)
# --------------------------------------------------------------------------

def test_admin_can_create(client):
    response = client.post("/v1/products", json=new_product(), headers=ADMIN)
    assert response.status_code == 201
    assert response.json()["productId"] == "prod-new-009"


def test_customer_cannot_create(client):
    assert client.post("/v1/products", json=new_product(), headers=CUSTOMER).status_code == 403


def test_customer_cannot_update(client):
    response = client.put("/v1/products/prod-mouse-002", json={"price": "1.00"}, headers=CUSTOMER)
    assert response.status_code == 403


def test_customer_cannot_delete(client):
    assert client.delete("/v1/products/prod-mouse-002", headers=CUSTOMER).status_code == 403


def test_duplicate_create_is_409(client):
    client.post("/v1/products", json=new_product(), headers=ADMIN)
    assert client.post("/v1/products", json=new_product(), headers=ADMIN).status_code == 409


def test_update_is_partial(client):
    client.put("/v1/products/prod-mouse-002", json={"price": "60.00"}, headers=ADMIN)
    body = client.get("/v1/products/prod-mouse-002", headers=CUSTOMER).json()
    assert body["price"] == "60.00"
    assert body["productName"] == "Magic Mouse"  # untouched


def test_update_missing_product_is_404(client):
    assert client.put("/v1/products/ghost", json={"price": "1.00"}, headers=ADMIN).status_code == 404


def test_delete_missing_product_is_404(client):
    assert client.delete("/v1/products/ghost", headers=ADMIN).status_code == 404


def test_admin_delete_returns_204(client):
    assert client.delete("/v1/products/prod-monitor-003", headers=ADMIN).status_code == 204


@pytest.mark.parametrize(
    "payload",
    [
        {"productId": "p", "productName": "", "price": "1.00", "category": "c"},
        {"productId": "p", "productName": "n", "price": "-1.00", "category": "c"},
        {"productId": "p", "productName": "n", "price": "0", "category": "c"},
        {"productId": "bad id!", "productName": "n", "price": "1.00", "category": "c"},
        {"productName": "n", "price": "1.00", "category": "c"},
    ],
)
def test_invalid_create_payloads_are_422(client, payload):
    assert client.post("/v1/products", json=payload, headers=ADMIN).status_code == 422
