"""Inventory Service - admin stock endpoints plus the saga consumer."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from srx_common import Authenticator, configure_logging, instrument_fastapi

from .config import Settings, get_settings
from .consumer import InventoryConsumer
from .database import build_engine, build_session_factory
from .events import InventoryOutboxPublisher, SagaEventPublisher
from .models import Availability, AvailabilityResponse, HealthResponse, StockAdjustment, StockLevel, StockListResponse
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

    # create_engine does not connect. Schema changes are owned by Alembic and
    # run as an explicit deployment step, never by application startup.
    engine = None
    if stock is None:
        engine = build_engine(settings)
        stock = ResilientStock(StockRepository(build_session_factory(engine)), settings)

    auth = Authenticator(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop = threading.Event()
        threads: list[threading.Thread] = []
        if settings.consumer_enabled and settings.orders_queue_url:
            saga_publisher = publisher or SagaEventPublisher(settings)
            consumer = InventoryConsumer(settings, stock, publisher=saga_publisher)
            consumer_thread = threading.Thread(
                target=consumer.run_forever, args=(stop,), name="inventory-consumer", daemon=True
            )
            outbox_thread = threading.Thread(
                target=InventoryOutboxPublisher(stock, saga_publisher).run_forever,
                args=(stop,),
                name="inventory-outbox",
                daemon=True,
            )
            threads.extend([consumer_thread, outbox_thread])
            for thread in threads:
                thread.start()
        yield
        stop.set()
        for thread in threads:
            thread.join(timeout=5)

    app = FastAPI(
        title="SmartRetailX Inventory Service",
        version="1.0.0",
        description="Stock levels and the reservation half of the order saga.",
        lifespan=lifespan,
    )
    instrument_fastapi(app, settings.service_name)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(service=settings.service_name, env=settings.env)

    @app.get(
        "/v1/availability",
        response_model=AvailabilityResponse,
        tags=["availability"],
    )
    def availability(
        productIds: list[str] = Query(..., min_length=1, max_length=20),
        _=Depends(auth.current_user),
    ) -> AvailabilityResponse:
        """Customer checkout hint only; final stock truth is reserve()."""
        unique_ids = list(dict.fromkeys(productIds))
        levels = []
        for product_id in unique_ids:
            level = stock.get(product_id)
            quantity = level.quantity if level else 0
            levels.append(Availability(productId=product_id, quantity=quantity, available=quantity > 0))
        return AvailabilityResponse(availability=levels, count=len(levels))

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
