"""Product schemas. Prices are Decimal, serialised as strings - same rule as
orders: no float ever touches money."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class ProductBase(BaseModel):
    productName: str = Field(..., min_length=1, max_length=200)
    price: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    category: str = Field(..., min_length=1, max_length=60)
    description: str | None = Field(None, max_length=2000)
    active: bool = True

    @field_serializer("price")
    def _price(self, value: Decimal) -> str:
        return f"{value:.2f}"


class ProductCreate(ProductBase):
    productId: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")


class ProductUpdate(BaseModel):
    """All fields optional - PUT here is a partial update by design, so the
    admin UI can change a price without resubmitting the whole record."""

    productName: str | None = Field(None, min_length=1, max_length=200)
    price: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    category: str | None = Field(None, min_length=1, max_length=60)
    description: str | None = Field(None, max_length=2000)
    active: bool | None = None

    @field_serializer("price")
    def _price(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"


class Product(ProductBase):
    productId: str
    basePrice: Decimal | None = None
    effectivePrice: Decimal | None = None
    promotion: dict | None = None

    @field_serializer("basePrice", "effectivePrice")
    def _effective_price(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"


class PromotionScope(StrEnum):
    PRODUCT = "PRODUCT"
    CATEGORY = "CATEGORY"


class PromotionLifecycleState(StrEnum):
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DISABLED = "DISABLED"


class PromotionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    discountPercent: Decimal = Field(..., gt=0, le=100, max_digits=5, decimal_places=2)
    scope: PromotionScope
    productIds: list[str] = Field(default_factory=list, max_length=100)
    category: str | None = Field(None, min_length=1, max_length=60)
    startsAt: datetime
    endsAt: datetime
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_scope_and_window(self) -> "PromotionBase":
        if self.startsAt.tzinfo is None or self.endsAt.tzinfo is None:
            raise ValueError("startsAt and endsAt must include a timezone")
        if self.endsAt <= self.startsAt:
            raise ValueError("endsAt must be after startsAt")
        if self.scope is PromotionScope.PRODUCT and not self.productIds:
            raise ValueError("PRODUCT promotions require productIds")
        if self.scope is PromotionScope.CATEGORY and not self.category:
            raise ValueError("CATEGORY promotions require category")
        return self

    @field_serializer("discountPercent")
    def _discount(self, value: Decimal) -> str:
        return f"{value:.2f}"


class PromotionCreate(PromotionBase):
    promotionId: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")


class PromotionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=120)
    discountPercent: Decimal | None = Field(None, gt=0, le=100, max_digits=5, decimal_places=2)
    scope: PromotionScope | None = None
    productIds: list[str] | None = Field(None, max_length=100)
    category: str | None = Field(None, min_length=1, max_length=60)
    startsAt: datetime | None = None
    endsAt: datetime | None = None
    enabled: bool | None = None

    @field_serializer("discountPercent")
    def _discount(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"


class Promotion(PromotionBase):
    promotionId: str
    lifecycleState: PromotionLifecycleState
    lifecycleVersion: int = 0


class PromotionListResponse(BaseModel):
    promotions: list[Promotion]
    count: int


class ProductListResponse(BaseModel):
    products: list[Product]
    count: int


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    env: str
