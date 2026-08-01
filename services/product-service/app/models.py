"""Product schemas. Prices are Decimal, serialised as strings - same rule as
orders: no float ever touches money."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer


class ProductBase(BaseModel):
    productName: str = Field(..., min_length=1, max_length=200)
    price: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    category: str = Field(..., min_length=1, max_length=60)
    description: str | None = Field(None, max_length=2000)

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

    @field_serializer("price")
    def _price(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"


class Product(ProductBase):
    productId: str


class ProductListResponse(BaseModel):
    products: list[Product]
    count: int


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    env: str
