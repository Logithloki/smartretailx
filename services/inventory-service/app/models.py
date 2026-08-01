"""Pydantic schemas for the inventory API and the saga messages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field


class StockLevel(BaseModel):
    productId: str
    quantity: int
    updatedAt: datetime | None = None


class StockListResponse(BaseModel):
    stock: list[StockLevel]
    count: int


class StockAdjustment(BaseModel):
    """Admin stock correction (backlog item 30).

    An absolute quantity rather than a delta: two concurrent operators each
    sending '+10' would race, whereas 'set to 40' is unambiguous.
    """

    quantity: int = Field(..., ge=0, le=1_000_000)


@dataclass(frozen=True)
class ReservationLine:
    productId: str
    quantity: int


@dataclass(frozen=True)
class ReservationResult:
    ok: bool
    reason: str | None = None

    @staticmethod
    def success() -> "ReservationResult":
        return ReservationResult(ok=True)

    @staticmethod
    def failure(reason: str) -> "ReservationResult":
        return ReservationResult(ok=False, reason=reason)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    env: str
