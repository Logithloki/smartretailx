from __future__ import annotations

from sqlalchemy import func, select

from app.database import InventoryOutboxEvent, ProcessedEvent, ReservationLedger
from app.models import ReservationLine


def test_duplicate_command_decrements_stock_once_and_creates_one_outcome(
    repository, session_factory
):
    lines = [ReservationLine(productId="prod-laptop-001", quantity=2)]

    first = repository.process_order(
        event_id="order-created#ord-1",
        order_id="ord-1",
        user_id="alice",
        lines=lines,
        passthrough={"correlationId": "corr-1"},
    )
    duplicate = repository.process_order(
        event_id="order-created#ord-1",
        order_id="ord-1",
        user_id="alice",
        lines=lines,
        passthrough={"correlationId": "corr-1"},
    )

    assert first.duplicate is False
    assert first.eventType == "order-confirmed"
    assert duplicate.duplicate is True
    assert repository.get("prod-laptop-001").quantity == 48
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ProcessedEvent)) == 1
        assert session.scalar(select(func.count()).select_from(InventoryOutboxEvent)) == 1


def test_rejection_and_inbox_are_committed_together(repository, session_factory):
    result = repository.process_order(
        event_id="order-created#ord-2",
        order_id="ord-2",
        user_id="alice",
        lines=[ReservationLine(productId="prod-mouse-002", quantity=99)],
        passthrough={"correlationId": "corr-2"},
    )

    assert result.eventType == "order-rejected"
    assert "insufficient stock" in result.reason
    assert repository.get("prod-mouse-002").quantity == 5
    with session_factory() as session:
        event = session.get(InventoryOutboxEvent, "inventory-outcome#order-created#ord-2")
        assert event.payload["eventType"] == "order-rejected"
        assert event.payload["payload"]["reason"].startswith("insufficient stock")


def test_pending_outbox_can_be_marked_published(repository):
    repository.process_order(
        event_id="order-created#ord-3",
        order_id="ord-3",
        user_id="alice",
        lines=[ReservationLine(productId="prod-laptop-001", quantity=1)],
        passthrough={"correlationId": "corr-3"},
    )

    pending = repository.pending_outbox(limit=10)
    assert [record.eventId for record in pending] == [
        "inventory-outcome#order-created#ord-3"
    ]
    repository.mark_outbox_published(pending[0].eventId, "sns-message-1")
    assert repository.pending_outbox(limit=10) == []


def test_reservation_ledger_releases_stock_exactly_once(repository, session_factory):
    repository.process_order(
        event_id="order-created#ord-cancel", order_id="ord-cancel", user_id="alice",
        lines=[ReservationLine(productId="prod-laptop-001", quantity=2)], passthrough={"correlationId": "corr-cancel"},
    )

    first = repository.release_reservation("ord-cancel", "corr-cancel")
    duplicate = repository.release_reservation("ord-cancel", "corr-cancel")

    assert first.eventType == "order-cancelled"
    assert duplicate.duplicate is True
    assert repository.get("prod-laptop-001").quantity == 50
    with session_factory() as session:
        rows = session.execute(select(ReservationLedger).where(ReservationLedger.order_id == "ord-cancel")).scalars().all()
        assert [(row.product_id, row.state) for row in rows] == [("prod-laptop-001", "RELEASED")]
