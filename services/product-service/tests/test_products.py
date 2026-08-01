from __future__ import annotations

import time

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
