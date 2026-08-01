"""Order Service - order intake and the read side of My Orders."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from srx_common import Authenticator, Principal, configure_logging, set_correlation_id

from .compensation import CompensationConsumer
from .config import Settings, get_settings
from .events import OrderCommandPublisher
from .idempotency import (
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyStore,
    fingerprint,
)
from .models import (
    CreateOrderRequest,
    HealthResponse,
    Order,
    OrderListResponse,
)
from .services import OrderRepository

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    repository: OrderRepository | None = None,
    publisher: OrderCommandPublisher | None = None,
    idempotency: IdempotencyStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.service_name, settings.log_level)

    repo = repository or OrderRepository(settings)
    events = publisher or OrderCommandPublisher(settings)
    keys = idempotency or IdempotencyStore(settings)
    auth = Authenticator(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Run the saga compensation receiver alongside the API.

        A background thread rather than a separate task definition: the work is
        tiny and long-polling is idle most of the time, so a second Fargate
        task would double the cost for no benefit at demo scale. The report
        notes splitting it out as the scale-up path.
        """
        stop = threading.Event()
        thread: threading.Thread | None = None

        if settings.compensation_consumer_enabled and settings.order_events_queue_url:
            consumer = CompensationConsumer(settings, repository=repo)
            thread = threading.Thread(
                target=consumer.run_forever, args=(stop,), name="compensation", daemon=True
            )
            thread.start()

        yield

        stop.set()
        if thread is not None:
            thread.join(timeout=5)

    app = FastAPI(
        title="SmartRetailX Order Service",
        version="1.0.0",
        description="Places orders and exposes a customer's order history.",
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(service=settings.service_name, env=settings.env)

    @app.post(
        "/v1/orders",
        response_model=Order,
        status_code=status.HTTP_201_CREATED,
        tags=["orders"],
    )
    def create_order(
        payload: CreateOrderRequest,
        response: Response,
        user: Principal = Depends(auth.current_user),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=200),
    ) -> Order:
        """Write PENDING to DynamoDB, then publish the reservation command.

        The write comes first deliberately: if the publish fails the order
        still exists and can be retried or reconciled, whereas publishing
        first could reserve stock for an order that was never persisted.

        Idempotency-Key is optional but honoured when supplied.
        """
        correlation_id = set_correlation_id()
        payload_hash = fingerprint(payload.model_dump(mode="json"))

        if idempotency_key:
            try:
                replay = keys.claim(user.subject, idempotency_key, payload_hash)
            except IdempotencyConflict:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Idempotency-Key was already used with a different request body",
                ) from None
            except IdempotencyInProgress:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="a request with this Idempotency-Key is already in flight",
                ) from None

            if replay is not None:
                existing = repo.get(replay.orderId)
                if existing is not None:
                    response.status_code = status.HTTP_200_OK
                    response.headers["Idempotent-Replay"] = "true"
                    return existing

        order = Order(
            userId=user.subject,
            items=payload.items,
            totalAmount=Order.total_for(payload.items),
        )

        try:
            repo.put(order)
            events.publish_order_created(order, correlation_id=correlation_id)
        except Exception:
            # Never leave a claimed key behind on failure, or the customer's
            # honest retry is met with 409 forever.
            if idempotency_key:
                keys.release(user.subject, idempotency_key)
            raise

        if idempotency_key:
            keys.complete(user.subject, idempotency_key, order.orderId)

        logger.info(
            "order accepted",
            extra={"orderId": order.orderId, "userId": user.subject, "status": order.status.value},
        )
        return order

    @app.get("/v1/orders", response_model=OrderListResponse, tags=["orders"])
    def list_orders(
        limit: int = Query(25, ge=1, le=100),
        user: Principal = Depends(auth.current_user),
    ) -> OrderListResponse:
        """A caller always lists their own orders - the user id comes from the
        verified token, never from a query parameter."""
        orders = repo.list_for_user(user.subject, limit=limit)
        return OrderListResponse(orders=orders, count=len(orders))

    @app.get("/v1/orders/{order_id}", response_model=Order, tags=["orders"])
    def get_order(order_id: str, user: Principal = Depends(auth.current_user)) -> Order:
        order = repo.get(order_id)
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
        if order.userId != user.subject and not user.in_group("admin"):
            # 404 rather than 403: revealing that an id exists but belongs to
            # someone else leaks information about other customers.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
        return order

    return app


app = create_app()
