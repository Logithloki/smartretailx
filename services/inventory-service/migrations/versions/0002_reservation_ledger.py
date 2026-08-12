"""Preserve per-order reservation evidence for exactly-once cancellation."""

from alembic import op
import sqlalchemy as sa

revision = "0002_reservation_ledger"
down_revision = "0001_inventory_inbox_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reservation_ledger",
        sa.Column("order_id", sa.String(length=100), nullable=False),
        sa.Column("product_id", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=12), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="reservation_quantity_positive"),
        sa.PrimaryKeyConstraint("order_id", "product_id"),
    )


def downgrade() -> None:
    op.drop_table("reservation_ledger")
