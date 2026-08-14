"""Unit tests for Inventory database baseline reconciliation & migration logic."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.migration import MigrationContext

from app.database import create_schema, Base
from app.migrate import get_alembic_config, run_migration, validate_legacy_schema


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
    mock_engine.url = sa.engine.make_url("postgresql+psycopg2://user:pass@localhost:5432/db")
    with pytest.raises(RuntimeError, match="create_schema.*is strictly prohibited on non-SQLite engines"):
        create_schema(mock_engine)


def test_empty_database_migrates_normally(test_engine, monkeypatch):
    """1. completely empty DB -> 0001/0002 execute normally."""
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
        conn.execute(sa.text("CREATE INDEX ix_inventory_outbox_state_created ON inventory_outbox (state, created_at)"))

    monkeypatch.setattr("app.migrate.build_engine", lambda settings: test_engine)
    run_migration()

    with test_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() == "0002_reservation_ledger"


def test_missing_table_fails_closed(test_engine):
    """3. stock exists but processed_events missing -> FAIL CLOSED."""
    with test_engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, quantity INT NOT NULL, updated_at DATETIME NOT NULL)"))

    valid, reason = validate_legacy_schema(test_engine)
    assert not valid
    assert "Missing required legacy table: 'processed_events'" in reason


def test_wrong_column_fails_closed(test_engine):
    """4. wrong stock column/constraint -> FAIL CLOSED."""
    # stock missing quantity
    with test_engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, updated_at DATETIME NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE processed_events (event_id VARCHAR(200) NOT NULL PRIMARY KEY, processed_at DATETIME NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE inventory_outbox (event_id VARCHAR(240) NOT NULL PRIMARY KEY, event_type VARCHAR(80) NOT NULL, aggregate_id VARCHAR(100) NOT NULL, payload TEXT NOT NULL, state VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, published_at DATETIME, message_id VARCHAR(100))"))
        conn.execute(sa.text("CREATE INDEX ix_inventory_outbox_state_created ON inventory_outbox (state, created_at)"))
        conn.execute(sa.text("CREATE TABLE reservation_ledger (order_id VARCHAR(100) NOT NULL, product_id VARCHAR(100) NOT NULL, quantity INT NOT NULL, state VARCHAR(12) NOT NULL, reserved_at DATETIME NOT NULL, released_at DATETIME, PRIMARY KEY (order_id, product_id))"))

    valid, reason = validate_legacy_schema(test_engine)
    assert not valid
    assert "Table 'stock' is missing required column: 'quantity'" in reason


def test_missing_outbox_index_fails_closed(test_engine):
    """5. missing outbox index -> FAIL CLOSED."""
    Base.metadata.create_all(test_engine)
    # Do NOT create index ix_inventory_outbox_state_created

    valid, reason = validate_legacy_schema(test_engine)
    assert not valid
    assert "missing index 'ix_inventory_outbox_state_created'" in reason


def test_exact_legacy_0001_only_does_not_falsely_stamp_0002(test_engine):
    """6. exact legacy 0001 only but 0002 object absent -> do not falsely stamp 0002."""
    with test_engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE stock (product_id VARCHAR(100) NOT NULL PRIMARY KEY, quantity INT NOT NULL, updated_at DATETIME NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE processed_events (event_id VARCHAR(200) NOT NULL PRIMARY KEY, processed_at DATETIME NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE inventory_outbox (event_id VARCHAR(240) NOT NULL PRIMARY KEY, event_type VARCHAR(80) NOT NULL, aggregate_id VARCHAR(100) NOT NULL, payload TEXT NOT NULL, state VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, published_at DATETIME, message_id VARCHAR(100))"))
        conn.execute(sa.text("CREATE INDEX ix_inventory_outbox_state_created ON inventory_outbox (state, created_at)"))
        # Missing reservation_ledger!

    valid, reason = validate_legacy_schema(test_engine)
    assert not valid
    assert "Missing required legacy table: 'reservation_ledger'" in reason


def test_already_versioned_db_runs_normal_upgrade(test_engine, monkeypatch):
    """7. already versioned DB -> normal upgrade path."""
    alembic_cfg = get_alembic_config(test_engine)
    command.stamp(alembic_cfg, "0001_inventory_inbox_outbox")

    monkeypatch.setattr("app.migrate.build_engine", lambda settings: test_engine)
    run_migration()

    with test_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() == "0002_reservation_ledger"
