from __future__ import annotations

import boto3
import pytest

from app.idempotency import (
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyStore,
    fingerprint,
)

from conftest import auth_header


def _payload(quantity: int = 2) -> dict:
    return {"items": [{"productId": "prod-laptop-001", "quantity": quantity}]}


def _key(value: str = "key-abc-123") -> dict:
    return {"Idempotency-Key": value}


def _count_orders(settings) -> int:
    table = boto3.resource("dynamodb", region_name="eu-west-1").Table(settings.orders_table_name)
    return table.scan()["Count"]


def _count_outbox_records(settings) -> int:
    table = boto3.resource("dynamodb", region_name="eu-west-1").Table(
        settings.order_outbox_table_name
    )
    return table.scan()["Count"]


# --------------------------------------------------------------------------
# the core guarantee
# --------------------------------------------------------------------------

def test_same_key_and_body_creates_exactly_one_order(client, settings):
    headers = {**auth_header(), **_key()}
    first = client.post("/v1/orders", json=_payload(), headers=headers)
    second = client.post("/v1/orders", json=_payload(), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers.get("Idempotent-Replay") == "true"
    assert first.json()["orderId"] == second.json()["orderId"]
    assert _count_orders(settings) == 1


def test_replay_creates_only_one_outbox_command(client, settings):
    """A duplicate must not reserve stock twice - the whole point."""
    headers = {**auth_header(), **_key()}
    client.post("/v1/orders", json=_payload(), headers=headers)
    client.post("/v1/orders", json=_payload(), headers=headers)

    assert _count_outbox_records(settings) == 1


def test_requests_without_a_key_are_not_deduplicated(client, settings):
    """Idempotency is opt-in; two genuine orders must both be created."""
    client.post("/v1/orders", json=_payload(), headers=auth_header())
    client.post("/v1/orders", json=_payload(), headers=auth_header())
    assert _count_orders(settings) == 2


def test_different_keys_create_different_orders(client, settings):
    client.post("/v1/orders", json=_payload(), headers={**auth_header(), **_key("k1")})
    client.post("/v1/orders", json=_payload(), headers={**auth_header(), **_key("k2")})
    assert _count_orders(settings) == 2


# --------------------------------------------------------------------------
# misuse
# --------------------------------------------------------------------------

def test_same_key_with_a_different_body_is_rejected(client, settings):
    """Returning the old order would silently discard the new request."""
    headers = {**auth_header(), **_key()}
    client.post("/v1/orders", json=_payload(quantity=1), headers=headers)
    response = client.post("/v1/orders", json=_payload(quantity=9), headers=headers)

    assert response.status_code == 422
    assert _count_orders(settings) == 1


def test_in_flight_duplicate_gets_409(client, settings, repository):
    """Simulates the concurrent case: the key is claimed but not completed."""
    store = IdempotencyStore(settings)
    store.claim("user-1", "key-inflight", fingerprint(_payload()))

    response = client.post(
        "/v1/orders", json=_payload(), headers={**auth_header(sub="user-1"), **_key("key-inflight")}
    )
    assert response.status_code == 409
    assert _count_orders(settings) == 0


# --------------------------------------------------------------------------
# per-user scoping (a security property, not just correctness)
# --------------------------------------------------------------------------

def test_keys_are_scoped_per_user(client, settings):
    """Two customers using the same key value must each get their own order,
    and neither may see the other's."""
    alice = client.post(
        "/v1/orders", json=_payload(), headers={**auth_header(sub="alice"), **_key("shared")}
    )
    bob = client.post(
        "/v1/orders", json=_payload(), headers={**auth_header(sub="bob"), **_key("shared")}
    )

    assert alice.status_code == 201
    assert bob.status_code == 201
    assert alice.json()["orderId"] != bob.json()["orderId"]
    assert _count_orders(settings) == 2


# --------------------------------------------------------------------------
# store-level behaviour
# --------------------------------------------------------------------------

def test_claim_returns_none_for_a_fresh_key(settings):
    store = IdempotencyStore(settings)
    assert store.claim("u1", "fresh", "hash-a") is None


def test_second_claim_with_same_hash_raises_in_progress(settings):
    store = IdempotencyStore(settings)
    store.claim("u1", "k", "hash-a")
    with pytest.raises(IdempotencyInProgress):
        store.claim("u1", "k", "hash-a")


def test_second_claim_with_different_hash_raises_conflict(settings):
    store = IdempotencyStore(settings)
    store.claim("u1", "k", "hash-a")
    with pytest.raises(IdempotencyConflict):
        store.claim("u1", "k", "hash-b")


def test_completed_claim_returns_replay(settings):
    store = IdempotencyStore(settings)
    store.claim("u1", "k", "hash-a")
    store.complete("u1", "k", "ord-123")
    replay = store.claim("u1", "k", "hash-a")
    assert replay is not None and replay.orderId == "ord-123"


def test_release_unwedges_a_failed_attempt(settings):
    store = IdempotencyStore(settings)
    store.claim("u1", "k", "hash-a")
    store.release("u1", "k")
    assert store.claim("u1", "k", "hash-a") is None


def test_records_carry_a_ttl_so_the_table_self_prunes(settings):
    """TTL is correct on this table (unlike orders, where it was removed):
    idempotency records are meant to expire."""
    store = IdempotencyStore(settings)
    store.claim("u1", "k", "hash-a")
    table = boto3.resource("dynamodb", region_name="eu-west-1").Table(
        settings.idempotency_table_name
    )
    item = table.get_item(Key={"id": "u1#k"})["Item"]
    assert int(item["expiration"]) > 0


def test_failed_transaction_releases_the_key(client, settings, repository, monkeypatch):
    """If the atomic write fails, the customer's retry with the same
    key must be allowed through rather than stuck at 409."""
    from app.main import create_app

    def fail_transaction(*_args, **_kwargs):
        raise RuntimeError("transaction unavailable")

    monkeypatch.setattr(repository, "put_with_command", fail_transaction)

    from fastapi.testclient import TestClient

    broken_client = TestClient(
        create_app(settings=settings, repository=repository),
        raise_server_exceptions=False,
    )
    headers = {**auth_header(), **_key("retry-me")}
    assert broken_client.post("/v1/orders", json=_payload(), headers=headers).status_code == 500

    store = IdempotencyStore(settings)
    assert store.claim("user-1", "retry-me", fingerprint(_payload())) is None


def test_fingerprint_is_stable_regardless_of_key_order():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


def test_fingerprint_changes_with_content():
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})
