"""Pure, shared money and promotion rules for SmartRetailX.

The calculator deliberately has no AWS dependency. Product Service owns
promotion writes; Order Service consumes the same deterministic calculation
against its narrow read model so a browser or a delayed event can never decide
the amount charged for an order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP


_PENNY = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """Retail rounding policy: two decimal places, half up."""
    return value.quantize(_PENNY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Promotion:
    promotion_id: str
    discount_percent: Decimal
    scope: str
    product_ids: tuple[str, ...]
    category: str | None
    enabled: bool
    starts_at: datetime
    ends_at: datetime

    def applies_to(self, *, product_id: str, category: str, now: datetime) -> bool:
        if not self.enabled or not (self.starts_at <= now < self.ends_at):
            return False
        if self.scope == "PRODUCT":
            return product_id in self.product_ids
        return self.scope == "CATEGORY" and self.category == category


@dataclass(frozen=True)
class PriceQuote:
    base_unit_price: Decimal
    effective_unit_price: Decimal
    unit_discount: Decimal
    promotion_id: str | None


def effective_price(
    *,
    base_price: Decimal,
    product_id: str,
    category: str,
    promotions: list[Promotion],
    now: datetime,
) -> PriceQuote:
    """Return the best active percentage promotion, without stacking offers."""
    applicable = [
        promotion
        for promotion in promotions
        if promotion.applies_to(product_id=product_id, category=category, now=now)
    ]
    base = money(base_price)
    if not applicable:
        return PriceQuote(base, base, Decimal("0.00"), None)

    winner = max(applicable, key=lambda p: (p.discount_percent, p.promotion_id))
    effective = money(base * (Decimal("1") - winner.discount_percent / Decimal("100")))
    return PriceQuote(base, effective, money(base - effective), winner.promotion_id)
