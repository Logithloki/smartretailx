"""Retry and circuit breaker around the database (backlog item 13).

The distinction that matters, and the one to defend in the viva:

    "insufficient stock" is a BUSINESS outcome, not a failure.

It is returned as a value, never raised, so it never counts towards the
breaker and is never retried. Retrying it would be pointless (stock will not
reappear) and letting it trip the breaker would take the service down because
customers ordered too much of something.

Only infrastructure faults - a dropped connection, a paused Aurora cluster, a
timeout - are retried and counted. Aurora at min-0 capacity is the concrete
motivation: the first query after an idle period can fail or take ~15 s while
the cluster wakes, and one transient error should not fail an order.
"""

from __future__ import annotations

import logging

import pybreaker
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError as SATimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .models import ProcessingOutcome, ReservationLine, ReservationResult, StockLevel

logger = logging.getLogger(__name__)

# Faults worth retrying: connectivity and timeouts, not programming errors.
TRANSIENT_ERRORS = (OperationalError, SATimeoutError, DBAPIError, ConnectionError, TimeoutError)


class _BreakerLogger(pybreaker.CircuitBreakerListener):
    def state_change(self, breaker, old, new):
        logger.warning(
            "circuit breaker state change",
            extra={"from": getattr(old, "name", str(old)), "to": getattr(new, "name", str(new))},
        )


def build_breaker(settings) -> pybreaker.CircuitBreaker:
    return pybreaker.CircuitBreaker(
        fail_max=settings.breaker_fail_max,
        reset_timeout=settings.breaker_reset_timeout,
        listeners=[_BreakerLogger()],
        name="inventory-db",
    )


class ResilientStock:
    """Wraps StockRepository with tenacity retry inside a pybreaker circuit.

    Order matters: retry sits *inside* the breaker, so one logical call - all
    its attempts included - counts as a single failure. Wiring it the other way
    would let a single slow outage burn through the breaker's budget in one
    request.
    """

    def __init__(self, repository, settings, breaker: pybreaker.CircuitBreaker | None = None):
        self._repo = repository
        self._settings = settings
        self.breaker = breaker or build_breaker(settings)

        self._retry = retry(
            stop=stop_after_attempt(settings.retry_attempts),
            wait=wait_exponential(multiplier=0.2, max=2),
            retry=retry_if_exception_type(TRANSIENT_ERRORS),
            reraise=True,
        )

    def _call(self, func, *args, **kwargs):
        return self.breaker.call(self._retry(func), *args, **kwargs)

    def reserve(self, lines: list[ReservationLine]) -> ReservationResult:
        return self._call(self._repo.reserve, lines)

    def process_order(
        self,
        event_id: str,
        order_id: str,
        user_id: str | None,
        lines: list[ReservationLine],
        passthrough: dict,
    ) -> ProcessingOutcome:
        return self._call(
            self._repo.process_order, event_id, order_id, user_id, lines, passthrough
        )

    def pending_outbox(self, limit: int = 25):
        return self._call(self._repo.pending_outbox, limit)

    def mark_outbox_published(self, event_id: str, message_id: str) -> None:
        return self._call(self._repo.mark_outbox_published, event_id, message_id)

    def release(self, lines: list[ReservationLine]) -> None:
        return self._call(self._repo.release, lines)

    def get(self, product_id: str) -> StockLevel | None:
        return self._call(self._repo.get, product_id)

    def list_all(self, limit: int = 100) -> list[StockLevel]:
        return self._call(self._repo.list_all, limit)

    def upsert(self, product_id: str, quantity: int) -> StockLevel:
        return self._call(self._repo.upsert, product_id, quantity)

    def ping(self) -> bool:
        return self._call(self._repo.ping)
