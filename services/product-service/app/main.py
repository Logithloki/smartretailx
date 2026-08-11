"""Product Service - the catalogue read path and admin CRUD (backlog 28)."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from srx_common import Authenticator, configure_logging, instrument_fastapi

from .cache import ProductCache
from .config import Settings, get_settings
from .models import (
    HealthResponse,
    Product,
    ProductCreate,
    ProductListResponse,
    ProductUpdate,
    Promotion,
    PromotionCreate,
    PromotionListResponse,
    PromotionUpdate,
)
from .services import (
    ProductAlreadyExists,
    ProductNotFound,
    ProductRepository,
    PromotionAlreadyExists,
    PromotionNotFound,
)

logger = logging.getLogger(__name__)

CACHE_HEADER = "X-Cache"


def create_app(
    settings: Settings | None = None,
    repository: ProductRepository | None = None,
    cache: ProductCache | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.service_name, settings.log_level)

    repo = repository or ProductRepository(settings)
    products = cache or ProductCache(
        maxsize=settings.cache_max_size, ttl=settings.cache_ttl_seconds
    )
    auth = Authenticator(settings)

    stop_reconciler = threading.Event()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        def reconcile_loop() -> None:
            # Every task may run this loop. Conditional DynamoDB transitions
            # guarantee only one task wins any SCHEDULED->ACTIVE / ACTIVE->EXPIRED move.
            while not stop_reconciler.wait(settings.promotion_reconcile_seconds):
                try:
                    repo.reconcile_promotions()
                except Exception:
                    logger.exception("promotion lifecycle reconciliation failed")

        worker = threading.Thread(target=reconcile_loop, name="promotion-reconciler", daemon=True)
        worker.start()
        try:
            yield
        finally:
            stop_reconciler.set()
            worker.join(timeout=1)

    app = FastAPI(
        title="SmartRetailX Product Service",
        version="1.0.0",
        description="Product catalogue with a per-task TTL cache.",
        lifespan=lifespan,
    )
    instrument_fastapi(app, settings.service_name)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(service=settings.service_name, env=settings.env)

    # ---- reads (any authenticated caller) -------------------------------

    @app.get("/v1/products", response_model=ProductListResponse, tags=["products"])
    def list_products(
        response: Response,
        category: str | None = Query(None, min_length=1, max_length=60),
        limit: int = Query(50, ge=1, le=100),
        _=Depends(auth.current_user),
    ) -> ProductListResponse:
        key = f"list:{category or '*'}:{limit}"
        cached = products.get(key)
        if cached is not None:
            response.headers[CACHE_HEADER] = "HIT"
            priced = [repo.priced(product) for product in cached]
            return ProductListResponse(products=priced, count=len(priced))

        found = repo.list(category=category, limit=limit)
        products.set(key, found)
        response.headers[CACHE_HEADER] = "MISS"
        priced = [repo.priced(product) for product in found]
        return ProductListResponse(products=priced, count=len(priced))

    @app.get("/v1/products/{product_id}", response_model=Product, tags=["products"])
    def get_product(
        product_id: str,
        response: Response,
        _=Depends(auth.current_user),
    ) -> Product:
        key = f"item:{product_id}"
        cached = products.get(key)
        if cached is not None:
            response.headers[CACHE_HEADER] = "HIT"
            return repo.priced(cached)

        product = repo.get(product_id)
        if product is None:
            # Negative results are not cached: a product that appears shortly
            # after a 404 would otherwise stay invisible for the whole TTL.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
            )
        products.set(key, product)
        response.headers[CACHE_HEADER] = "MISS"
        return repo.priced(product)

    # ---- admin CRUD (backlog item 28) -----------------------------------

    @app.post(
        "/v1/products",
        response_model=Product,
        status_code=status.HTTP_201_CREATED,
        tags=["admin"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def create_product(payload: ProductCreate) -> Product:
        product = Product(**payload.model_dump())
        try:
            repo.create(product)
        except ProductAlreadyExists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="product already exists"
            ) from None
        _invalidate(product.productId)
        return product

    @app.put(
        "/v1/products/{product_id}",
        response_model=Product,
        tags=["admin"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def update_product(product_id: str, payload: ProductUpdate) -> Product:
        changes = payload.model_dump(exclude_none=True)
        try:
            product = repo.update(product_id, changes)
        except ProductNotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
            ) from None
        _invalidate(product_id)
        return product

    @app.delete(
        "/v1/products/{product_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["admin"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def delete_product(product_id: str) -> Response:
        try:
            repo.delete(product_id)
        except ProductNotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
            ) from None
        _invalidate(product_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ---- promotion administration ---------------------------------------

    @app.get(
        "/v1/promotions", response_model=PromotionListResponse, tags=["admin"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def list_promotions(limit: int = Query(100, ge=1, le=100)) -> PromotionListResponse:
        found = repo.list_promotions(limit)
        return PromotionListResponse(promotions=found, count=len(found))

    @app.post(
        "/v1/promotions", response_model=Promotion, status_code=status.HTTP_201_CREATED, tags=["admin"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def create_promotion(payload: PromotionCreate) -> Promotion:
        try:
            created = repo.create_promotion(payload)
        except PromotionAlreadyExists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="promotion already exists") from None
        _invalidate("*")
        return created

    @app.put(
        "/v1/promotions/{promotion_id}", response_model=Promotion, tags=["admin"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def update_promotion(promotion_id: str, payload: PromotionUpdate) -> Promotion:
        try:
            updated = repo.update_promotion(promotion_id, payload.model_dump(exclude_none=True))
        except PromotionNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="promotion not found") from None
        _invalidate("*")
        return updated

    def _invalidate(product_id: str) -> None:
        """Drop this task's cached copies after a write.

        Only this task's cache - with several tasks running, the others
        converge when their TTL expires. That bounded staleness is the
        documented trade-off for not running ElastiCache.
        """
        products.invalidate(f"item:{product_id}")
        products.clear()  # list keys vary by category/limit; cheapest correct move

    return app


app = create_app()
