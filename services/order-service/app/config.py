from functools import lru_cache

from srx_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "order-service"

    orders_table_name: str = "smartretailx-orders"
    order_outbox_table_name: str = "smartretailx-order-outbox"
    idempotency_table_name: str = "smartretailx-idempotency"
    products_table_name: str = "smartretailx-products"
    promotions_table_name: str = "smartretailx-promotions"
    orders_queue_url: str = ""
    local_inline_outbox_enabled: bool = False
    # Queue used by the saga compensation receiver.
    order_events_queue_url: str = ""
    # Off by default so tests and one-shot CLI use never spawn a poller.
    compensation_consumer_enabled: bool = False
    event_bus_name: str = "smartretailx-events"
    idempotency_ttl_seconds: int = 86400
    order_summaries_bucket: str = "smartretailx-order-summaries"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
