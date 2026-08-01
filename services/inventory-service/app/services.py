"""Stock repository - the transactional heart of the saga.

The reservation is all-or-nothing across every line of an order. A partial
reservation would leave stock consumed for an order that then gets rejected,
which is precisely the inconsistency the saga exists to avoid.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, text, update

from .database import StockItem, utcnow
from .models import ReservationLine, ReservationResult, StockLevel

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
                        session.rollback()
                        # Distinguish "no such product" from "not enough of it";
                        # the customer-facing reason differs.
                        exists = session.get(StockItem, line.productId) is not None
                        reason = (
                            f"insufficient stock for {line.productId}"
                            if exists
                            else f"unknown product {line.productId}"
                        )
                        logger.info("reservation refused", extra={"reason": reason})
                        return ReservationResult.failure(reason)
                session.commit()
            except Exception:
                session.rollback()
                raise

        logger.info("reservation committed", extra={"lines": len(lines)})
        return ReservationResult.success()

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
