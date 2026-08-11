"""Stock repository - the transactional heart of the saga.

The reservation is all-or-nothing across every line of an order. A partial
reservation would leave stock consumed for an order that then gets rejected,
which is precisely the inconsistency the saga exists to avoid.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, text, update
from srx_common import new_event

from .database import InventoryOutboxEvent, ProcessedEvent, ReservationLedger, StockItem, utcnow
from .models import ProcessingOutcome, ReservationLine, ReservationResult, StockLevel

logger = logging.getLogger(__name__)


class StockRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    # ---- reads ----------------------------------------------------------

    def list_all(self, limit: int = 100) -> list[StockLevel]:
        with self._session_factory() as session:
            rows = session.execute(select(StockItem).limit(limit)).scalars().all()
            return [
                StockLevel(productId=r.product_id, quantity=r.quantity, updatedAt=r.updated_at)
                for r in rows
            ]

    def get(self, product_id: str) -> StockLevel | None:
        with self._session_factory() as session:
            row = session.get(StockItem, product_id)
            if row is None:
                return None
            return StockLevel(
                productId=row.product_id, quantity=row.quantity, updatedAt=row.updated_at
            )

    # ---- writes ---------------------------------------------------------

    def upsert(self, product_id: str, quantity: int) -> StockLevel:
        with self._session_factory() as session:
            row = session.get(StockItem, product_id)
            if row is None:
                row = StockItem(product_id=product_id, quantity=quantity)
                session.add(row)
            else:
                row.quantity = quantity
                row.updated_at = utcnow()
            session.commit()
            return StockLevel(
                productId=row.product_id, quantity=row.quantity, updatedAt=row.updated_at
            )

    def reserve(self, lines: list[ReservationLine]) -> ReservationResult:
        """Decrement every line atomically, or nothing at all.

        The conditional UPDATE (`WHERE quantity >= :qty`) does the check and
        the write in a single statement, so two concurrent orders for the last
        unit cannot both succeed. A SELECT-then-UPDATE would have a race window
        between the two, and reading the row first would need explicit locking
        to be safe.
        """
        if not lines:
            return ReservationResult.failure("order contained no items")

        with self._session_factory() as session:
            try:
                result = self._reserve_in_session(session, lines)
                if result.ok:
                    session.commit()
                else:
                    session.rollback()
                return result
            except Exception:
                session.rollback()
                raise

        logger.info("reservation committed", extra={"lines": len(lines)})
        return result

    @staticmethod
    def _reserve_in_session(session, lines: list[ReservationLine]) -> ReservationResult:
        if not lines:
            return ReservationResult.failure("order contained no items")
        for line in lines:
            result = session.execute(
                update(StockItem)
                .where(
                    StockItem.product_id == line.productId,
                    StockItem.quantity >= line.quantity,
                )
                .values(quantity=StockItem.quantity - line.quantity, updated_at=utcnow())
            )
            if result.rowcount == 0:
                exists = session.get(StockItem, line.productId) is not None
                reason = (
                    f"insufficient stock for {line.productId}"
                    if exists
                    else f"unknown product {line.productId}"
                )
                return ReservationResult.failure(reason)
        return ReservationResult.success()

    def process_order(
        self,
        event_id: str,
        order_id: str,
        user_id: str | None,
        lines: list[ReservationLine],
        passthrough: dict,
    ) -> ProcessingOutcome:
        """Commit stock, inbox receipt, and outcome outbox in one transaction."""
        outcome_id = f"inventory-outcome#{event_id}"
        with self._session_factory() as session:
            existing = session.get(ProcessedEvent, event_id)
            if existing is not None:
                outbox = session.get(InventoryOutboxEvent, outcome_id)
                return ProcessingOutcome(
                    eventType=outbox.event_type if outbox else "duplicate",
                    duplicate=True,
                    reason=(outbox.payload.get("reason") if outbox else None),
                )

            result = self._reserve_in_session(session, lines)
            event_type = "order-confirmed" if result.ok else "order-rejected"
            business_payload = {
                "orderId": order_id,
                "userId": user_id,
                "userEmail": passthrough.get("userEmail"),
                "loadTest": bool(passthrough.get("loadTest", False)),
            }
            if result.reason:
                business_payload["reason"] = result.reason
            payload = new_event(
                event_type=event_type,
                event_id=outcome_id,
                aggregate_id=order_id,
                correlation_id=passthrough["correlationId"],
                causation_id=event_id,
                trace_id=passthrough.get("traceId"),
                payload=business_payload,
            ).model_dump(mode="json")

            if result.ok:
                for line in lines:
                    session.add(ReservationLedger(
                        order_id=order_id, product_id=line.productId, quantity=line.quantity, state="RESERVED"
                    ))
            session.add(ProcessedEvent(event_id=event_id))
            session.add(
                InventoryOutboxEvent(
                    event_id=outcome_id,
                    event_type=event_type,
                    aggregate_id=order_id,
                    payload=payload,
                )
            )
            session.commit()
            return ProcessingOutcome(eventType=event_type, reason=result.reason)

    def release_reservation(self, order_id: str, correlation_id: str) -> ProcessingOutcome:
        """Release only persisted RESERVED rows, retaining RELEASED evidence."""
        outcome_id = f"inventory-cancelled#{order_id}"
        with self._session_factory() as session:
            rows = session.execute(
                select(ReservationLedger).where(ReservationLedger.order_id == order_id).with_for_update()
            ).scalars().all()
            if not rows or all(row.state == "RELEASED" for row in rows):
                return ProcessingOutcome(eventType="order-cancelled", duplicate=True)
            reserved = [row for row in rows if row.state == "RESERVED"]
            for row in reserved:
                session.execute(
                    update(StockItem).where(StockItem.product_id == row.product_id).values(
                        quantity=StockItem.quantity + row.quantity, updated_at=utcnow()
                    )
                )
                row.state = "RELEASED"
                row.released_at = utcnow()
            payload = new_event(
                event_type="order-cancelled", event_id=outcome_id, aggregate_id=order_id,
                correlation_id=correlation_id, payload={"orderId": order_id},
            ).model_dump(mode="json")
            session.merge(InventoryOutboxEvent(
                event_id=outcome_id, event_type="order-cancelled", aggregate_id=order_id, payload=payload
            ))
            session.commit()
            return ProcessingOutcome(eventType="order-cancelled")

    def pending_outbox(self, limit: int = 25) -> list[InventoryOutboxEvent]:
        with self._session_factory() as session:
            return list(
                session.execute(
                    select(InventoryOutboxEvent)
                    .where(InventoryOutboxEvent.state == "PENDING")
                    .order_by(InventoryOutboxEvent.created_at)
                    .limit(limit)
                )
                .scalars()
                .all()
            )

    def mark_outbox_published(self, event_id: str, message_id: str) -> None:
        with self._session_factory() as session:
            session.execute(
                update(InventoryOutboxEvent)
                .where(
                    InventoryOutboxEvent.event_id == event_id,
                    InventoryOutboxEvent.state == "PENDING",
                )
                .values(state="PUBLISHED", published_at=utcnow(), message_id=message_id)
            )
            session.commit()

    def release(self, lines: list[ReservationLine]) -> None:
        """Put stock back - used if a later step of the saga fails after the
        reservation succeeded."""
        with self._session_factory() as session:
            for line in lines:
                session.execute(
                    update(StockItem)
                    .where(StockItem.product_id == line.productId)
                    .values(quantity=StockItem.quantity + line.quantity, updated_at=utcnow())
                )
            session.commit()

    def ping(self) -> bool:
        with self._session_factory() as session:
            session.execute(text("SELECT 1"))
        return True
