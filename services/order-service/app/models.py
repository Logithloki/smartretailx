"""Order schemas.

Money is Decimal end to end - never float. DynamoDB stores numbers as Decimal
natively, and binary floating point cannot represent 0.1 exactly, which is not
an acceptable property for a financial record.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrderItem(BaseModel):
    productId: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., gt=0, le=100)
    unitPrice: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)

    @field_serializer("unitPrice")
    def _price(self, value: Decimal) -> str:
        # Serialise as a string so no float ever appears on the wire.
        return f"{value:.2f}"


class CreateOrderRequest(BaseModel):
    """The client sends items only. Totals are computed server-side - a
    client-supplied total is an obvious tampering vector."""

    items: list[OrderItem] = Field(..., min_length=1, max_length=20)


class Order(BaseModel):
    orderId: str = Field(default_factory=lambda: f"ord-{uuid4().hex[:12]}")
    userId: str
    status: OrderStatus = OrderStatus.PENDING
    items: list[OrderItem]
    totalAmount: Decimal
    createdAt: datetime = Field(default_factory=utcnow)
    updatedAt: datetime = Field(default_factory=utcnow)
    # Set when the saga compensates, so the UI can explain a rejection.
    statusReason: str | None = None

    @field_serializer("totalAmount")
    def _total(self, value: Decimal) -> str:
        return f"{value:.2f}"

    @staticmethod
    def total_for(items: list[OrderItem]) -> Decimal:
        return sum((i.unitPrice * i.quantity for i in items), Decimal("0"))


class OrderListResponse(BaseModel):
    orders: list[Order]
    count: int


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    env: str
