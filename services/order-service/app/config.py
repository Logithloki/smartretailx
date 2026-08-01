from functools import lru_cache

from srx_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "order-service"

    orders_table_name: str = "smartretailx-orders"
    idempotency_table_name: str = "smartretailx-idempotency"
    orders_queue_url: str = ""
    # Saga compensation receiver (Week 2 Day 5).
    order_events_queue_url: str = ""
    # Off by default so tests and one-shot CLI use never spawn a poller.
    compensation_consumer_enabled: bool = False
    idempotency_ttl_seconds: int = 86400


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
