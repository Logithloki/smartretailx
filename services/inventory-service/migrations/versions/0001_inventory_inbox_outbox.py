"""Create stock, consumer inbox, and transactional outcome outbox."""

from alembic import op
import sqlalchemy as sa

revision = "0001_inventory_inbox_outbox"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock",
        sa.Column("product_id", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="stock_quantity_non_negative"),
        sa.PrimaryKeyConstraint("product_id"),
    )
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "inventory_outbox",
        sa.Column("event_id", sa.String(length=240), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_id", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_inventory_outbox_state_created",
        "inventory_outbox",
        ["state", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_outbox_state_created", table_name="inventory_outbox")
    op.drop_table("inventory_outbox")
    op.drop_table("processed_events")
    op.drop_table("stock")
