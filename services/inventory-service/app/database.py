"""Relational storage for stock (ADR-03).

Stock is the one part of the domain that is genuinely relational: a reservation
must decrement several rows atomically and never go negative. That is a
transaction, which is exactly what DynamoDB is bad at and Postgres is good at -
the justification for polyglot persistence rather than one store for everything.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockItem(Base):
    __tablename__ = "stock"

    product_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # Defence in depth: even if the application logic is wrong, the database
    # refuses to hold negative stock.
    __table_args__ = (CheckConstraint("quantity >= 0", name="stock_quantity_non_negative"),)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ReservationLedger(Base):
    """Immutable reservation evidence: RESERVED transitions to RELEASED once."""

    __tablename__ = "reservation_ledger"

    order_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="RESERVED")
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("quantity > 0", name="reservation_quantity_positive"),)


class InventoryOutboxEvent(Base):
    __tablename__ = "inventory_outbox"

    event_id: Mapped[str] = mapped_column(String(240), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message_id: Mapped[str | None] = mapped_column(String(100))

    @property
    def eventId(self) -> str:
        return self.event_id


def build_engine(settings, **kwargs):
    url = settings.sqlalchemy_url
    engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        # SQLite needs this to be usable from the consumer thread in tests.
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Aurora Serverless v2 at min-0 drops idle connections when it pauses;
        # recycling avoids handing out a dead one after a wake-up.
        engine_kwargs.update({"pool_size": 5, "max_overflow": 5, "pool_recycle": 300})
    engine_kwargs.update(kwargs)
    return create_engine(url, **engine_kwargs)


def build_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_schema(engine) -> None:
    Base.metadata.create_all(engine)
