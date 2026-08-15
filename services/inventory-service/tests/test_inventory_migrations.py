"""Unit tests for Inventory database baseline reconciliation & migration logic."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.migration import MigrationContext

from app.database import create_schema, Base
from app.migrate import (
    LEGACY_INDEX,
    classify_legacy_schema,
    classify_database_state,
    get_alembic_config,
    run_migration,
    validate_legacy_schema,
)


@pytest.fixture
def test_engine():
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sa.pool.StaticPool,
        future=True,
    )
    yield engine
    engine.dispose()


def test_sqlite_test_bootstrap_supported(test_engine):
    """10. SQLite test bootstrap remains supported."""
    create_schema(test_engine)
    inspector = sa.inspect(test_engine)
    tables = inspector.get_table_names()
    assert "stock" in tables
    assert "processed_events" in tables
    assert "inventory_outbox" in tables
    assert "reservation_ledger" in tables


def test_production_create_schema_blocked():
    """9. production create_schema/create_all is blocked on non-SQLite engines."""
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    mock_engine.url = sa.engine.make_url(
        "postgresql+psycopg2://user:pass@localhost:5432/db"
    )
    with pytest.raises(
        RuntimeError,
        match="create_schema.*is strictly prohibited on non-SQLite engines",
    ):
        create_schema(mock_engine)


def test_empty_database_migrates_normally(test_engine, monkeypatch):
    """1. completely empty DB -> 0001/0002 execute normally."""
    assert classify_database_state(test_engine) == "EMPTY"
    monkeypatch.setattr("app.migrate.build_engine", lambda settings: test_engine)
    run_migration()

    inspector = sa.inspect(test_engine)
    tables = inspector.get_table_names()
    assert "alembic_version" in tables
    assert "stock" in tables
    assert "reservation_ledger" in tables

    with test_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() == "0002_reservation_ledger"


def test_exact_legacy_schema_stamps_and_upgrades(test_engine, monkeypatch):
    """2. exact legacy schema + no Alembic revision -> stamp 0002 then upgrade."""
    # Pre-create exact legacy tables via Base.metadata
    Base.metadata.create_all(test_engine)

    # Manually create missing index on inventory_outbox expected by validator
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE INDEX ix_inventory_outbox_state_created ON inventory_outbox (state, created_at)"
            )
        )

    assert classify_database_state(test_engine) == "FULL_LEGACY_MATCH"

    monkeypatch.setattr("app.migrate.build_engine", lambda settings: test_engine)
    run_migration()

    with test_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() == "0002_reservation_ledger"


def test_partial_legacy_schema_reconciles_without_recreating_stock(
    test_engine, monkeypatch
):
    """A valid stock table is preserved while all missing baseline objects are created."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, "
                "quantity INT NOT NULL, updated_at DATETIME NOT NULL, "
                "CONSTRAINT stock_quantity_non_negative CHECK (quantity >= 0))"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO stock (product_id, quantity, updated_at) "
                "VALUES ('legacy-product', 7, CURRENT_TIMESTAMP)"
            )
        )

    report = classify_legacy_schema(test_engine)
    assert classify_database_state(test_engine) == "COMPATIBLE_PARTIAL_LEGACY"
    assert report == {
        "stock": "MATCH",
        "processed_events": "MISSING",
        "inventory_outbox": "MISSING",
        "ix_inventory_outbox_state_created": "MISSING",
        "reservation_ledger": "MISSING",
    }

    monkeypatch.setattr("app.migrate.build_engine", lambda settings: test_engine)
    run_migration()

    inspector = sa.inspect(test_engine)
    assert set(inspector.get_table_names()) >= {
        "stock",
        "processed_events",
        "inventory_outbox",
        "reservation_ledger",
        "alembic_version",
    }
    assert "ix_inventory_outbox_state_created" in {
        index["name"] for index in inspector.get_indexes("inventory_outbox")
    }
    with test_engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT product_id, quantity FROM stock WHERE product_id = 'legacy-product'"
            )
        ).one()
        assert tuple(row) == ("legacy-product", 7)
        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() == "0002_reservation_ledger"


def test_partial_report_lists_all_missing_objects(test_engine):
    """Classification must not stop at the first missing object."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, "
                "quantity INT NOT NULL, updated_at DATETIME NOT NULL, "
                "CONSTRAINT stock_quantity_non_negative CHECK (quantity >= 0))"
            )
        )

    assert classify_legacy_schema(test_engine)["processed_events"] == "MISSING"
    assert classify_legacy_schema(test_engine)["inventory_outbox"] == "MISSING"
    assert (
        classify_legacy_schema(test_engine)["ix_inventory_outbox_state_created"]
        == "MISSING"
    )
    assert classify_legacy_schema(test_engine)["reservation_ledger"] == "MISSING"


def test_missing_index_is_reconciled(test_engine, monkeypatch):
    """A missing outbox index is a compatible partial schema, not an incompatibility."""
    Base.metadata.create_all(test_engine)
    assert "ix_inventory_outbox_state_created" in classify_legacy_schema(test_engine)
    assert (
        classify_legacy_schema(test_engine)["ix_inventory_outbox_state_created"]
        == "MISSING"
    )

    monkeypatch.setattr("app.migrate.build_engine", lambda settings: test_engine)
    run_migration()

    assert validate_legacy_schema(test_engine)[0]


def test_incompatible_existing_stock_fails_closed_without_creation(test_engine):
    """An existing incompatible object blocks reconciliation before any creation."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, "
                "quantity VARCHAR(20) NOT NULL, updated_at DATETIME NOT NULL)"
            )
        )

    report = classify_legacy_schema(test_engine)
    assert classify_database_state(test_engine) == "INCOMPATIBLE_LEGACY"
    assert report["stock"].startswith("INCOMPATIBLE:")
    assert not validate_legacy_schema(test_engine)[0]


def test_incompatible_stock_constraint_fails_closed_before_creation(
    test_engine, monkeypatch
):
    """A wrong existing check constraint is never repaired automatically."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, "
                "quantity INT NOT NULL, updated_at DATETIME NOT NULL, "
                "CONSTRAINT stock_quantity_non_negative CHECK (quantity > 0))"
            )
        )

    monkeypatch.setattr("app.migrate.build_engine", lambda settings: test_engine)
    with pytest.raises(SystemExit):
        run_migration()

    assert sa.inspect(test_engine).get_table_names() == ["stock"]


def test_incompatible_existing_outbox_index_fails_closed(test_engine):
    """An existing index with the wrong column order is incompatible."""
    Base.metadata.create_all(test_engine)
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE INDEX ix_inventory_outbox_state_created "
                "ON inventory_outbox (created_at, state)"
            )
        )

    report = classify_legacy_schema(test_engine)
    assert report[LEGACY_INDEX].startswith("INCOMPATIBLE:")


def test_incompatible_existing_outbox_type_fails_closed(test_engine):
    """An existing outbox payload with the wrong type is not silently accepted."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE inventory_outbox (event_id VARCHAR(240) NOT NULL PRIMARY KEY, "
                "event_type VARCHAR(80) NOT NULL, aggregate_id VARCHAR(100) NOT NULL, "
                "payload TEXT NOT NULL, state VARCHAR(20) NOT NULL, "
                "created_at DATETIME NOT NULL, published_at DATETIME, "
                "message_id VARCHAR(100)"
                ")"
            )
        )

    assert classify_legacy_schema(test_engine)["inventory_outbox"].startswith(
        "INCOMPATIBLE:"
    )


def test_missing_table_validation_is_not_sufficient_anymore(test_engine):
    """The strict validator still reports incomplete state before reconciliation."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, "
                "quantity INT NOT NULL, updated_at DATETIME NOT NULL, "
                "CONSTRAINT stock_quantity_non_negative CHECK (quantity >= 0))"
            )
        )

    valid, reason = validate_legacy_schema(test_engine)
    assert not valid
    assert "processed_events" in reason


def test_wrong_column_fails_closed(test_engine):
    """4. wrong stock column/constraint -> FAIL CLOSED."""
    # stock missing quantity
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, updated_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE processed_events (event_id VARCHAR(200) NOT NULL PRIMARY KEY, processed_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE inventory_outbox (event_id VARCHAR(240) NOT NULL PRIMARY KEY, event_type VARCHAR(80) NOT NULL, aggregate_id VARCHAR(100) NOT NULL, payload JSON NOT NULL, state VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, published_at DATETIME, message_id VARCHAR(100))"
            )
        )
        conn.execute(
            sa.text(
                "CREATE INDEX ix_inventory_outbox_state_created ON inventory_outbox (state, created_at)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE reservation_ledger (order_id VARCHAR(100) NOT NULL, product_id VARCHAR(100) NOT NULL, quantity INT NOT NULL, state VARCHAR(12) NOT NULL, reserved_at DATETIME NOT NULL, released_at DATETIME, PRIMARY KEY (order_id, product_id))"
            )
        )

    valid, reason = validate_legacy_schema(test_engine)
    assert not valid
    assert "Table 'stock' is missing required column(s): ['quantity']" in reason


def test_missing_outbox_index_is_reported_as_partial(test_engine):
    """5. missing outbox index is compatible partial state."""
    Base.metadata.create_all(test_engine)
    # Do NOT create index ix_inventory_outbox_state_created

    assert classify_legacy_schema(test_engine)[LEGACY_INDEX] == "MISSING"


def test_exact_legacy_0001_only_does_not_falsely_stamp_0002(test_engine):
    """6. exact legacy 0001 only but 0002 object absent -> do not falsely stamp 0002."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, quantity INT NOT NULL, updated_at DATETIME NOT NULL, CONSTRAINT stock_quantity_non_negative CHECK (quantity >= 0))"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE processed_events (event_id VARCHAR(200) NOT NULL PRIMARY KEY, processed_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE inventory_outbox (event_id VARCHAR(240) NOT NULL PRIMARY KEY, event_type VARCHAR(80) NOT NULL, aggregate_id VARCHAR(100) NOT NULL, payload JSON NOT NULL, state VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, published_at DATETIME, message_id VARCHAR(100))"
            )
        )
        conn.execute(
            sa.text(
                "CREATE INDEX ix_inventory_outbox_state_created ON inventory_outbox (state, created_at)"
            )
        )
        # Missing reservation_ledger!

    valid, reason = validate_legacy_schema(test_engine)
    assert not valid
    assert "Missing required legacy object(s): ['reservation_ledger']" in reason


def test_already_versioned_db_runs_normal_upgrade(test_engine, monkeypatch):
    """7. already versioned DB -> normal upgrade path."""
    with test_engine.begin() as conn:
        alembic_cfg = get_alembic_config(test_engine, connection=conn)
        command.stamp(alembic_cfg, "0001_inventory_inbox_outbox")
    assert classify_database_state(test_engine) == "ALREADY_VERSIONED"

    monkeypatch.setattr("app.migrate.build_engine", lambda settings: test_engine)
    run_migration()

    with test_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() == "0002_reservation_ledger"
