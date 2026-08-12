from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import ReservationLine
from conftest import auth_header


def line(product_id: str, quantity: int) -> ReservationLine:
    return ReservationLine(productId=product_id, quantity=quantity)


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------

def test_get_returns_current_level(repository):
    assert repository.get("prod-laptop-001").quantity == 50


def test_get_unknown_product_is_none(repository):
    assert repository.get("nope") is None


def test_list_all(repository):
    assert len(repository.list_all()) == 3


def test_customer_availability_is_a_bounded_read_only_projection(settings, repository):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.resilience import ResilientStock

    client = TestClient(create_app(settings=settings, stock=ResilientStock(repository, settings)))
    body = client.get(
        "/v1/availability?productIds=prod-laptop-001&productIds=prod-sold-out&productIds=ghost",
        headers=auth_header(),
    ).json()
    assert body == {
        "availability": [
            {"productId": "prod-laptop-001", "quantity": 50, "available": True},
            {"productId": "prod-sold-out", "quantity": 0, "available": False},
            {"productId": "ghost", "quantity": 0, "available": False},
        ],
        "count": 3,
    }


# --------------------------------------------------------------------------
# the reservation transaction
# --------------------------------------------------------------------------

def test_reserve_decrements_stock(repository):
    assert repository.reserve([line("prod-laptop-001", 2)]).ok is True
    assert repository.get("prod-laptop-001").quantity == 48


def test_reserve_exact_remaining_quantity_succeeds(repository):
    assert repository.reserve([line("prod-mouse-002", 5)]).ok is True
    assert repository.get("prod-mouse-002").quantity == 0


def test_reserve_more_than_available_is_refused(repository):
    result = repository.reserve([line("prod-mouse-002", 6)])
    assert result.ok is False
    assert "insufficient stock" in result.reason
    assert repository.get("prod-mouse-002").quantity == 5  # untouched


def test_reserve_from_zero_stock_is_refused(repository):
    assert repository.reserve([line("prod-sold-out", 1)]).ok is False


def test_unknown_product_is_reported_differently_from_insufficient(repository):
    """The customer-facing reason differs, so the codes must not be conflated."""
    result = repository.reserve([line("ghost-product", 1)])
    assert result.ok is False
    assert "unknown product" in result.reason


def test_multi_line_reservation_is_all_or_nothing(repository):
    """The second line cannot be satisfied, so the first must not be consumed."""
    result = repository.reserve([line("prod-laptop-001", 1), line("prod-mouse-002", 99)])

    assert result.ok is False
    assert repository.get("prod-laptop-001").quantity == 50
    assert repository.get("prod-mouse-002").quantity == 5


def test_multi_line_reservation_commits_every_line_on_success(repository):
    assert repository.reserve([line("prod-laptop-001", 3), line("prod-mouse-002", 2)]).ok is True
    assert repository.get("prod-laptop-001").quantity == 47
    assert repository.get("prod-mouse-002").quantity == 3


def test_empty_reservation_is_refused(repository):
    assert repository.reserve([]).ok is False


def test_repeated_reservations_drain_to_zero_and_then_refuse(repository):
    for _ in range(5):
        assert repository.reserve([line("prod-mouse-002", 1)]).ok is True
    assert repository.get("prod-mouse-002").quantity == 0
    assert repository.reserve([line("prod-mouse-002", 1)]).ok is False


# --------------------------------------------------------------------------
# compensation helper
# --------------------------------------------------------------------------

def test_release_returns_stock(repository):
    repository.reserve([line("prod-laptop-001", 10)])
    repository.release([line("prod-laptop-001", 10)])
    assert repository.get("prod-laptop-001").quantity == 50


# --------------------------------------------------------------------------
# admin writes + the database-level guard
# --------------------------------------------------------------------------

def test_upsert_creates_then_updates(repository):
    repository.upsert("prod-new", 12)
    assert repository.get("prod-new").quantity == 12
    repository.upsert("prod-new", 3)
    assert repository.get("prod-new").quantity == 3


def test_database_rejects_negative_stock_even_if_logic_fails(session_factory):
    """Defence in depth: the CHECK constraint is the last line."""
    from app.database import StockItem

    with session_factory() as session:
        session.add(StockItem(product_id="bad", quantity=-1))
        with pytest.raises(IntegrityError):
            session.commit()


def test_ping(repository):
    assert repository.ping() is True
