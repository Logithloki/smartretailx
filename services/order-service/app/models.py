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

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"


class FulfilmentStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PACKING = "PACKING"
    DISPATCHED = "DISPATCHED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrderLineRequest(BaseModel):
    """Untrusted customer input: identifiers and quantities only."""

    model_config = ConfigDict(extra="forbid")

    productId: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., gt=0, le=100)


class OrderItem(BaseModel):
    productId: str
    productName: str
    quantity: int
    baseUnitPrice: Decimal
    effectiveUnitPrice: Decimal
    unitDiscount: Decimal
    lineDiscount: Decimal
    lineTotal: Decimal
    promotionId: str | None = None

    @field_serializer("baseUnitPrice", "effectiveUnitPrice", "unitDiscount", "lineDiscount", "lineTotal")
    def _price(self, value: Decimal) -> str:
        # Serialise as a string so no float ever appears on the wire.
        return f"{value:.2f}"


class CreateOrderRequest(BaseModel):
    """The client sends items only. Totals are computed server-side - a
    client-supplied total is an obvious tampering vector."""

    model_config = ConfigDict(extra="forbid")

    items: list[OrderLineRequest] = Field(..., min_length=1, max_length=20)
    # Performance-only marker propagated to SNS attributes so SES is filtered.
    loadTest: bool = False

    @model_validator(mode="after")
    def aggregate_duplicate_products(self) -> "CreateOrderRequest":
        quantities: dict[str, int] = {}
        order: list[str] = []
        for line in self.items:
            if line.productId not in quantities:
                order.append(line.productId)
                quantities[line.productId] = 0
            quantities[line.productId] += line.quantity
            if quantities[line.productId] > 100:
                raise ValueError("combined quantity for a product must be at most 100")
        self.items = [OrderLineRequest(productId=product_id, quantity=quantities[product_id]) for product_id in order]
        return self


class Order(BaseModel):
    orderId: str = Field(default_factory=lambda: f"ord-{uuid4().hex[:12]}")
    userId: str
    status: OrderStatus = OrderStatus.PENDING
    fulfilmentStatus: FulfilmentStatus = FulfilmentStatus.NOT_STARTED
    items: list[OrderItem]
    subtotal: Decimal
    discountTotal: Decimal
    totalAmount: Decimal
    createdAt: datetime = Field(default_factory=utcnow)
    updatedAt: datetime = Field(default_factory=utcnow)
    # Set when the saga compensates, so the UI can explain a rejection.
    statusReason: str | None = None

    @field_serializer("subtotal", "discountTotal", "totalAmount")
    def _total(self, value: Decimal) -> str:
        return f"{value:.2f}"



class OrderListResponse(BaseModel):
    orders: list[Order]
    count: int


class OrderSummaryResponse(BaseModel):
    orderId: str
    url: str


class FulfilmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: FulfilmentStatus


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    env: str
