from datetime import UTC, datetime
from decimal import Decimal

from srx_common.pricing import Promotion, effective_price


def test_active_percentage_promotion_uses_decimal_round_half_up():
    """A 10% active product offer changes £19.995 to the hand-checked £18.00."""
    quote = effective_price(
        base_price=Decimal("19.995"),
        product_id="prod-1",
        category="electronics",
        promotions=[
            Promotion(
                promotion_id="promo-10",
                discount_percent=Decimal("10"),
                scope="PRODUCT",
                product_ids=("prod-1",),
                category=None,
                enabled=True,
                starts_at=datetime(2026, 8, 11, 8, tzinfo=UTC),
                ends_at=datetime(2026, 8, 11, 10, tzinfo=UTC),
            )
        ],
        now=datetime(2026, 8, 11, 9, tzinfo=UTC),
    )

    assert quote.effective_unit_price == Decimal("18.00")
    assert quote.unit_discount == Decimal("2.00")
    assert quote.promotion_id == "promo-10"
