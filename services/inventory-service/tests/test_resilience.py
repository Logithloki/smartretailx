from __future__ import annotations

import pybreaker
import pytest
from sqlalchemy.exc import OperationalError

from app.models import ReservationLine, ReservationResult
from app.resilience import ResilientStock


def line(product_id: str = "p1", quantity: int = 1) -> ReservationLine:
    return ReservationLine(productId=product_id, quantity=quantity)


class FlakyRepo:
    """Fails `failures` times with a transient error, then succeeds."""

    def __init__(self, failures: int, result=None):
        self.failures = failures
        self.calls = 0
        self._result = result or ReservationResult.success()

    def reserve(self, lines):
        self.calls += 1
        if self.calls <= self.failures:
            raise OperationalError("SELECT 1", {}, Exception("connection reset"))
        return self._result


class BusinessRefusalRepo:
    def __init__(self):
        self.calls = 0

    def reserve(self, lines):
        self.calls += 1
        return ReservationResult.failure("insufficient stock for p1")


class ControllableRepo:
    """Fails until `fail` is switched off."""

    def __init__(self):
        self.fail = True
        self.calls = 0

    def reserve(self, lines):
        self.calls += 1
        if self.fail:
            raise OperationalError("SELECT 1", {}, Exception("connection reset"))
        return ReservationResult.success()


def trip_breaker(stock) -> None:
    """Drive the breaker open.

    pybreaker raises CircuitBreakerError from the very call that crosses the
    threshold, rather than re-raising the underlying error, so both types have
    to be tolerated while tripping it.
    """
    for _ in range(20):
        try:
            stock.reserve([line()])
        except (OperationalError, pybreaker.CircuitBreakerError):
            pass
        if stock.breaker.current_state == "open":
            return
    raise AssertionError("breaker never opened")


# --------------------------------------------------------------------------
# retry
# --------------------------------------------------------------------------

def test_transient_failure_is_retried_and_then_succeeds(settings):
    """Aurora at min-0 can drop the first query while it wakes; one blip must
    not fail the order."""
    repo = FlakyRepo(failures=2)
    stock = ResilientStock(repo, settings)

    assert stock.reserve([line()]).ok is True
    assert repo.calls == 3


def test_retry_gives_up_after_the_configured_attempts(settings):
    repo = FlakyRepo(failures=99)
    stock = ResilientStock(repo, settings)

    with pytest.raises(OperationalError):
        stock.reserve([line()])
    assert repo.calls == settings.retry_attempts


# --------------------------------------------------------------------------
# the key distinction: business outcome vs infrastructure failure
# --------------------------------------------------------------------------

def test_insufficient_stock_is_not_retried(settings):
    """Stock will not reappear on a second attempt."""
    repo = BusinessRefusalRepo()
    stock = ResilientStock(repo, settings)

    result = stock.reserve([line()])
    assert result.ok is False
    assert repo.calls == 1


def test_insufficient_stock_never_trips_the_breaker(settings):
    """Otherwise a run of out-of-stock orders would take the service down."""
    repo = BusinessRefusalRepo()
    stock = ResilientStock(repo, settings)

    for _ in range(settings.breaker_fail_max * 3):
        assert stock.reserve([line()]).ok is False

    assert stock.breaker.current_state == "closed"


# --------------------------------------------------------------------------
# breaker
# --------------------------------------------------------------------------

def test_breaker_opens_after_repeated_infrastructure_failures(settings):
    stock = ResilientStock(ControllableRepo(), settings)
    trip_breaker(stock)
    assert stock.breaker.current_state == "open"


def test_open_breaker_fails_fast_without_touching_the_database(settings):
    """Fail-fast is the point: stop queuing work against a dead dependency."""
    repo = ControllableRepo()
    stock = ResilientStock(repo, settings)
    trip_breaker(stock)

    calls_before = repo.calls
    with pytest.raises(pybreaker.CircuitBreakerError):
        stock.reserve([line()])
    assert repo.calls == calls_before


def test_one_logical_call_counts_as_one_breaker_failure(settings):
    """Retry sits inside the breaker, so three attempts are one failure - not
    three. Otherwise a single outage would exhaust the budget instantly."""
    repo = FlakyRepo(failures=99)
    stock = ResilientStock(repo, settings)

    with pytest.raises(OperationalError):
        stock.reserve([line()])

    assert repo.calls == settings.retry_attempts
    assert stock.breaker.fail_counter == 1
    assert stock.breaker.current_state == "closed"


def test_breaker_recovers_after_the_reset_timeout(settings):
    """Half-open lets one probe through; success closes the circuit again."""
    fast = settings.model_copy(update={"breaker_reset_timeout": 0})
    repo = ControllableRepo()
    stock = ResilientStock(repo, fast)

    trip_breaker(stock)
    assert stock.breaker.current_state == "open"

    # Dependency comes back. With a 0s reset timeout the next call is the
    # half-open probe, and a successful probe closes the circuit.
    repo.fail = False
    assert stock.reserve([line()]).ok is True
    assert stock.breaker.current_state == "closed"


def test_real_repository_works_through_the_wrapper(repository, settings):
    stock = ResilientStock(repository, settings)
    assert stock.reserve([ReservationLine(productId="prod-laptop-001", quantity=2)]).ok is True
    assert stock.get("prod-laptop-001").quantity == 48
