"""Strict Legacy Baseline Reconciliation and Alembic Migration Entrypoint.

Handles:
1. Already versioned DB (alembic_version present): runs `alembic upgrade head`.
2. Empty/Fresh DB (no user tables): runs `alembic upgrade head` from 0001.
3. Legacy Untracked DB (tables exist, no alembic_version):
   classifies the complete baseline, creates only missing compatible objects,
   validates again, stamps 0002_reservation_ledger, and runs `alembic upgrade head`.
4. Incompatible existing objects: fails closed with non-zero exit code without altering schema.
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
from app.database import Base, build_engine

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("app.migrate")

LEGACY_TABLES = ("stock", "processed_events", "inventory_outbox", "reservation_ledger")
LEGACY_INDEX = "ix_inventory_outbox_state_created"
EXPECTED_OBJECTS = LEGACY_TABLES + (LEGACY_INDEX,)

_EXPECTED_CHECKS = {
    "stock": ("stock_quantity_non_negative", "quantity >= 0"),
    "reservation_ledger": ("reservation_quantity_positive", "quantity > 0"),
}


def _inspector(bind: sa.Engine | sa.Connection) -> sa.Inspector:
    return sa.inspect(bind)


def _current_revision(bind: sa.Engine | sa.Connection) -> str | None:
    if isinstance(bind, sa.Engine):
        with bind.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    return MigrationContext.configure(bind).get_current_revision()


def _normalise_sql(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _type_matches(
    actual: sa.types.TypeEngine, expected: sa.types.TypeEngine, dialect: str
) -> bool:
    """Compare the portable schema properties that the historical migrations own."""
    if isinstance(expected, sa.String):
        return isinstance(actual, sa.String) and actual.length == expected.length
    if isinstance(expected, sa.Integer):
        return isinstance(actual, sa.Integer)
    if isinstance(expected, sa.DateTime):
        if not isinstance(actual, sa.DateTime):
            return False
        # SQLite has no timezone-aware timestamp type; PostgreSQL does.
        return dialect != "postgresql" or actual.timezone is expected.timezone
    if isinstance(expected, sa.JSON):
        return isinstance(actual, sa.JSON)
    return actual.__class__ is expected.__class__


def _validate_table(
    inspector: sa.Inspector, table_name: str, dialect: str
) -> str | None:
    expected_table = Base.metadata.tables[table_name]
    actual_columns = {
        column["name"]: column for column in inspector.get_columns(table_name)
    }
    expected_columns = {column.name: column for column in expected_table.columns}

    extra = sorted(set(actual_columns) - set(expected_columns))
    missing = sorted(set(expected_columns) - set(actual_columns))
    if missing:
        return f"Table '{table_name}' is missing required column(s): {missing}"
    if extra:
        return f"Table '{table_name}' has unexpected column(s): {extra}"

    for column_name, expected_column in expected_columns.items():
        actual_column = actual_columns[column_name]
        if not _type_matches(actual_column["type"], expected_column.type, dialect):
            return (
                f"Table '{table_name}' column '{column_name}' type mismatch: "
                f"expected {expected_column.type}, got {actual_column['type']}"
            )
        if bool(actual_column["nullable"]) != bool(expected_column.nullable):
            expected_nullable = "NULL" if expected_column.nullable else "NOT NULL"
            return (
                f"Table '{table_name}' column '{column_name}' nullability mismatch: "
                f"expected {expected_nullable}"
            )

    primary_key = (
        inspector.get_pk_constraint(table_name).get("constrained_columns") or []
    )
    expected_primary_key = [
        column.name for column in expected_table.primary_key.columns
    ]
    if primary_key != expected_primary_key:
        return (
            f"Table '{table_name}' primary key mismatch: "
            f"expected {expected_primary_key}, got {primary_key}"
        )

    expected_check = _EXPECTED_CHECKS.get(table_name)
    if expected_check and dialect in {"postgresql", "sqlite"}:
        checks = {
            check.get("name"): _normalise_sql(check.get("sqltext"))
            for check in inspector.get_check_constraints(table_name)
        }
        name, expression = expected_check
        if name not in checks:
            return f"Table '{table_name}' missing check constraint '{name}'"
        if expression not in checks[name]:
            return (
                f"Table '{table_name}' check constraint '{name}' mismatch: "
                f"expected expression containing '{expression}'"
            )
    return None


def classify_legacy_schema(bind: sa.Engine | sa.Connection) -> dict[str, str]:
    """Classify every expected baseline object without reading business rows."""
    inspector = _inspector(bind)
    dialect = inspector.dialect.name
    existing_tables = set(inspector.get_table_names())
    report: dict[str, str] = {}

    for table_name in LEGACY_TABLES:
        if table_name not in existing_tables:
            report[table_name] = "MISSING"
            continue
        mismatch = _validate_table(inspector, table_name, dialect)
        report[table_name] = (
            "MATCH" if mismatch is None else f"INCOMPATIBLE: {mismatch}"
        )

    if "inventory_outbox" not in existing_tables:
        report[LEGACY_INDEX] = "MISSING"
    else:
        indexes = {
            index["name"]: index for index in inspector.get_indexes("inventory_outbox")
        }
        index = indexes.get(LEGACY_INDEX)
        if index is None:
            report[LEGACY_INDEX] = "MISSING"
        elif index.get("column_names") != ["state", "created_at"] or index.get(
            "unique"
        ):
            report[LEGACY_INDEX] = (
                "INCOMPATIBLE: Index 'ix_inventory_outbox_state_created' must be "
                "non-unique on ['state', 'created_at']"
            )
        else:
            report[LEGACY_INDEX] = "MATCH"
    return report


def classify_database_state(bind: sa.Engine | sa.Connection) -> str:
    """Return the migration state machine category without changing the database."""
    if _current_revision(bind) is not None:
        return "ALREADY_VERSIONED"
    existing_tables = set(_inspector(bind).get_table_names())
    if not set(LEGACY_TABLES).intersection(existing_tables):
        return "EMPTY"
    report = classify_legacy_schema(bind)
    if any(status.startswith("INCOMPATIBLE:") for status in report.values()):
        return "INCOMPATIBLE_LEGACY"
    if all(status == "MATCH" for status in report.values()):
        return "FULL_LEGACY_MATCH"
    return "COMPATIBLE_PARTIAL_LEGACY"


def _format_report(report: dict[str, str]) -> str:
    return "; ".join(f"{name}: {report[name]}" for name in EXPECTED_OBJECTS)


def _create_missing_legacy_objects(
    connection: sa.Connection, report: dict[str, str]
) -> None:
    """Create only objects classified MISSING; never alter an existing object."""
    for table_name in LEGACY_TABLES:
        if report[table_name] == "MISSING":
            Base.metadata.tables[table_name].create(connection, checkfirst=False)
    if report[LEGACY_INDEX] == "MISSING":
        table = Base.metadata.tables["inventory_outbox"]
        index = sa.Index(LEGACY_INDEX, table.c.state, table.c.created_at)
        try:
            index.create(connection, checkfirst=False)
        finally:
            # Do not mutate application metadata just by running the repair.
            table.indexes.discard(index)


def get_alembic_config(
    engine: sa.Engine, connection: sa.Connection | None = None
) -> Config:
    base_dir = Path(__file__).resolve().parent.parent
    ini_path = base_dir / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(base_dir / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url).replace("%", "%%"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def validate_legacy_schema(bind: sa.Engine | sa.Connection) -> tuple[bool, str]:
    """Strictly validate every baseline object after reconciliation."""
    report = classify_legacy_schema(bind)
    if all(status == "MATCH" for status in report.values()):
        return True, "Exact legacy schema matched through revision 0002"
    missing = [name for name, status in report.items() if status == "MISSING"]
    incompatible = [
        f"{name}: {status.removeprefix('INCOMPATIBLE: ')}"
        for name, status in report.items()
        if status.startswith("INCOMPATIBLE:")
    ]
    if incompatible:
        return False, incompatible[0]
    return False, f"Missing required legacy object(s): {missing}"


def run_migration() -> None:
    settings = get_settings()
    engine = build_engine(settings)

    with engine.begin() as connection:
        alembic_cfg = get_alembic_config(engine, connection=connection)
        context = MigrationContext.configure(connection)
        current_rev = context.get_current_revision()
        state = classify_database_state(connection)
        logger.info("Database migration state: %s", state)

        if current_rev is not None:
            logger.info(
                f"Database already versioned at revision: '{current_rev}'. Running standard upgrade head."
            )
            command.upgrade(alembic_cfg, "head")
            return

        inspector = sa.inspect(connection)
        tables = set(inspector.get_table_names())
        legacy_intersect = set(LEGACY_TABLES).intersection(tables)

        if not legacy_intersect:
            logger.info(
                "Database is empty/unversioned. Executing full migration chain to head..."
            )
            command.upgrade(alembic_cfg, "head")
            return

        logger.info(
            "Untracked legacy schema detected. Inspecting all baseline objects..."
        )
        report = classify_legacy_schema(connection)
        logger.info("Legacy schema classification: %s", _format_report(report))

        incompatible = [
            f"{name}: {status.removeprefix('INCOMPATIBLE: ')}"
            for name, status in report.items()
            if status.startswith("INCOMPATIBLE:")
        ]
        if incompatible:
            logger.error("SCHEMA RECONCILIATION FAILED CLOSED: %s", incompatible[0])
            logger.error(
                "Existing legacy objects are incompatible; no mutation was attempted."
            )
            sys.exit(1)

        missing = [name for name, status in report.items() if status == "MISSING"]
        if missing:
            logger.info(
                "Creating only missing compatible baseline objects: %s", missing
            )
            _create_missing_legacy_objects(connection, report)
            post_report = classify_legacy_schema(connection)
            logger.info(
                "Post-reconciliation schema classification: %s",
                _format_report(post_report),
            )
            if not all(status == "MATCH" for status in post_report.values()):
                logger.error("SCHEMA RECONCILIATION FAILED CLOSED after creation.")
                sys.exit(1)

        is_valid, reason = validate_legacy_schema(connection)
        if not is_valid:
            logger.error("SCHEMA RECONCILIATION FAILED CLOSED: %s", reason)
            sys.exit(1)

        logger.info("Schema validation successful: %s", reason)
        logger.info("Stamping baseline revision '0002_reservation_ledger'...")
        command.stamp(alembic_cfg, "0002_reservation_ledger")
        logger.info("Baseline stamp successful. Running upgrade head...")
        command.upgrade(alembic_cfg, "head")
        logger.info(
            "Inventory database migration and baseline reconciliation completed successfully."
        )


if __name__ == "__main__":
    run_migration()
