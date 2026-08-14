"""Strict Legacy Baseline Reconciliation and Alembic Migration Entrypoint.

Handles:
1. Already versioned DB (alembic_version present): runs `alembic upgrade head`.
2. Empty/Fresh DB (no user tables): runs `alembic upgrade head` from 0001.
3. Legacy Untracked DB (tables exist, no alembic_version):
   Validates exact schema matching revision 0002. If valid, stamps 0002_reservation_ledger
   and runs `alembic upgrade head`.
4. Partial or Incompatible DB: Fails closed with non-zero exit code without altering schema.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
import sqlalchemy as sa

from app.config import get_settings
from app.database import build_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.migrate")

LEGACY_TABLES = ("stock", "processed_events", "inventory_outbox", "reservation_ledger")


def get_alembic_config(engine: sa.Engine, connection: sa.Connection | None = None) -> Config:
    base_dir = Path(__file__).resolve().parent.parent
    ini_path = base_dir / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(base_dir / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url).replace("%", "%%"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def validate_legacy_schema(engine: sa.Engine) -> tuple[bool, str]:
    """Strict validation of legacy database schema matching revisions 0001 and 0002.

    Returns (is_valid, reason).
    """
    inspector = sa.inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # 1. Verify all 4 legacy tables exist
    for tbl in LEGACY_TABLES:
        if tbl not in existing_tables:
            return False, f"Missing required legacy table: '{tbl}'"

    # 2. Validate 'stock'
    cols = {c["name"]: c for c in inspector.get_columns("stock")}
    for required in ("product_id", "quantity", "updated_at"):
        if required not in cols:
            return False, f"Table 'stock' is missing required column: '{required}'"
    if cols["product_id"]["nullable"]:
        return False, "Table 'stock' column 'product_id' must be NOT NULL"
    if cols["quantity"]["nullable"]:
        return False, "Table 'stock' column 'quantity' must be NOT NULL"
    if cols["updated_at"]["nullable"]:
        return False, "Table 'stock' column 'updated_at' must be NOT NULL"

    pk = inspector.get_pk_constraint("stock")
    if pk.get("constrained_columns") != ["product_id"]:
        return False, f"Table 'stock' primary key mismatch: expected ['product_id'], got {pk.get('constrained_columns')}"

    check_constraints = [c["name"] for c in inspector.get_check_constraints("stock")]
    if "stock_quantity_non_negative" not in check_constraints and engine.dialect.name == "postgresql":
        return False, "Table 'stock' missing check constraint 'stock_quantity_non_negative'"

    # 3. Validate 'processed_events'
    cols = {c["name"]: c for c in inspector.get_columns("processed_events")}
    for required in ("event_id", "processed_at"):
        if required not in cols:
            return False, f"Table 'processed_events' is missing required column: '{required}'"
    pk = inspector.get_pk_constraint("processed_events")
    if pk.get("constrained_columns") != ["event_id"]:
        return False, f"Table 'processed_events' primary key mismatch: expected ['event_id'], got {pk.get('constrained_columns')}"

    # 4. Validate 'inventory_outbox'
    cols = {c["name"]: c for c in inspector.get_columns("inventory_outbox")}
    for required in ("event_id", "event_type", "aggregate_id", "payload", "state", "created_at"):
        if required not in cols:
            return False, f"Table 'inventory_outbox' is missing required column: '{required}'"
    pk = inspector.get_pk_constraint("inventory_outbox")
    if pk.get("constrained_columns") != ["event_id"]:
        return False, f"Table 'inventory_outbox' primary key mismatch: expected ['event_id'], got {pk.get('constrained_columns')}"

    indexes = {idx["name"]: idx for idx in inspector.get_indexes("inventory_outbox")}
    if "ix_inventory_outbox_state_created" not in indexes:
        return False, "Table 'inventory_outbox' is missing index 'ix_inventory_outbox_state_created'"
    idx_cols = indexes["ix_inventory_outbox_state_created"].get("column_names")
    if idx_cols != ["state", "created_at"]:
        return False, f"Index 'ix_inventory_outbox_state_created' columns mismatch: expected ['state', 'created_at'], got {idx_cols}"

    # 5. Validate 'reservation_ledger'
    cols = {c["name"]: c for c in inspector.get_columns("reservation_ledger")}
    for required in ("order_id", "product_id", "quantity", "state", "reserved_at"):
        if required not in cols:
            return False, f"Table 'reservation_ledger' is missing required column: '{required}'"
    pk = inspector.get_pk_constraint("reservation_ledger")
    if sorted(pk.get("constrained_columns") or []) != ["order_id", "product_id"]:
        return False, f"Table 'reservation_ledger' primary key mismatch: expected ['order_id', 'product_id'], got {pk.get('constrained_columns')}"

    check_constraints = [c["name"] for c in inspector.get_check_constraints("reservation_ledger")]
    if "reservation_quantity_positive" not in check_constraints and engine.dialect.name == "postgresql":
        return False, "Table 'reservation_ledger' missing check constraint 'reservation_quantity_positive'"

    return True, "Exact legacy schema matched through revision 0002"


def run_migration() -> None:
    settings = get_settings()
    engine = build_engine(settings)

    with engine.begin() as connection:
        alembic_cfg = get_alembic_config(engine, connection=connection)
        context = MigrationContext.configure(connection)
        current_rev = context.get_current_revision()

        if current_rev is not None:
            logger.info(f"Database already versioned at revision: '{current_rev}'. Running standard upgrade head.")
            command.upgrade(alembic_cfg, "head")
            return

        inspector = sa.inspect(connection)
        tables = set(inspector.get_table_names())
        legacy_intersect = set(LEGACY_TABLES).intersection(tables)

        if not legacy_intersect:
            logger.info("Database is empty/unversioned. Executing full migration chain to head...")
            command.upgrade(alembic_cfg, "head")
            return

        logger.info("Untracked legacy schema detected. Performing strict schema validation...")
        is_valid, reason = validate_legacy_schema(engine)

        if not is_valid:
            logger.error(f"SCHEMA RECONCILIATION FAILED CLOSED: {reason}")
            logger.error("Database schema is partial or incompatible. Aborting rollout without mutating database.")
            sys.exit(1)

        logger.info(f"Schema validation successful: {reason}")
        logger.info("Stamping baseline revision '0002_reservation_ledger'...")
        command.stamp(alembic_cfg, "0002_reservation_ledger")
        logger.info("Baseline stamp successful. Running upgrade head...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Inventory database migration and baseline reconciliation completed successfully.")


if __name__ == "__main__":
    run_migration()
