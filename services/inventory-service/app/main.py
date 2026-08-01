"""Inventory Service - admin stock endpoints plus the saga consumer."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from srx_common import Authenticator, configure_logging

from .config import Settings, get_settings
from .consumer import InventoryConsumer
from .database import build_engine, build_session_factory, create_schema
from .events import SagaEventPublisher
from .models import HealthResponse, StockAdjustment, StockLevel, StockListResponse
from .resilience import ResilientStock
from .services import StockRepository

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    stock: ResilientStock | None = None,
    publisher: SagaEventPublisher | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.service_name, settings.log_level)

    # create_engine does not connect; only create_schema does, and that is
    # done at startup rather than import so building the app never requires a
    # reachable database (imports must stay side-effect free).
    engine = None
    if stock is None:
        engine = build_engine(settings)
        stock = ResilientStock(StockRepository(build_session_factory(engine)), settings)

    auth = Authenticator(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if engine is not None:
            create_schema(engine)

        stop = threading.Event()
        thread: threading.Thread | None = None
        if settings.consumer_enabled and settings.orders_queue_url:
            consumer = InventoryConsumer(settings, stock, publisher=publisher)
            thread = threading.Thread(
                target=consumer.run_forever, args=(stop,), name="inventory-consumer", daemon=True
            )
            thread.start()
        yield
        stop.set()
        if thread is not None:
            thread.join(timeout=5)

    app = FastAPI(
        title="SmartRetailX Inventory Service",
        version="1.0.0",
        description="Stock levels and the reservation half of the order saga.",
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(service=settings.service_name, env=settings.env)

    # Backlog item 30: stock read/adjust, admin only. Customers never see
    # stock levels - they are commercially sensitive and not needed to shop.
    @app.get(
        "/v1/inventory",
        response_model=StockListResponse,
        tags=["inventory"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def list_stock(limit: int = Query(100, ge=1, le=500)) -> StockListResponse:
        levels = stock.list_all(limit)
        return StockListResponse(stock=levels, count=len(levels))

    @app.get(
        "/v1/inventory/{product_id}",
        response_model=StockLevel,
        tags=["inventory"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def get_stock(product_id: str) -> StockLevel:
        level = stock.get(product_id)
        if level is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="product not stocked"
            )
        return level

    @app.patch(
        "/v1/inventory/{product_id}",
        response_model=StockLevel,
        tags=["inventory"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def adjust_stock(product_id: str, payload: StockAdjustment) -> StockLevel:
        """Absolute set, not a delta - two operators adjusting at once would
        race on '+10' but agree on 'set to 40'."""
        return stock.upsert(product_id, payload.quantity)

    return app


app = create_app()
