"""Order Service - order intake and the read side of My Orders."""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Query, status
from srx_common import Authenticator, Principal, configure_logging, set_correlation_id

from .config import Settings, get_settings
from .events import OrderCommandPublisher
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
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.service_name, settings.log_level)

    repo = repository or OrderRepository(settings)
    events = publisher or OrderCommandPublisher(settings)
    auth = Authenticator(settings)

    app = FastAPI(
        title="SmartRetailX Order Service",
        version="1.0.0",
        description="Places orders and exposes a customer's order history.",
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
        user: Principal = Depends(auth.current_user),
    ) -> Order:
        """Write PENDING to DynamoDB, then publish the reservation command.

        The write comes first deliberately: if the publish fails the order
        still exists and can be retried or reconciled, whereas publishing
        first could reserve stock for an order that was never persisted.
        """
        correlation_id = set_correlation_id()

        order = Order(
            userId=user.subject,
            items=payload.items,
            totalAmount=Order.total_for(payload.items),
        )
        repo.put(order)
        events.publish_order_created(order, correlation_id=correlation_id)

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
