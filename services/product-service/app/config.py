from functools import lru_cache

from srx_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "product-service"

    products_table_name: str = "smartretailx-products"
    promotions_table_name: str = "smartretailx-promotions"

    # Per-task in-memory cache (ADR-03). ElastiCache Serverless is named as the
    # production path; at demo scale a 30s TTL in-process costs nothing.
    cache_ttl_seconds: int = 30
    cache_max_size: int = 500
    promotion_reconcile_seconds: int = 15


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
