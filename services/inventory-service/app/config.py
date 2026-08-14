from functools import lru_cache
from urllib.parse import quote_plus

from srx_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "inventory-service"

    # In production these come from the ECS task definition, and db_password
    # specifically is injected via `secrets.valueFrom` off the RDS-managed
    # secret - never as a plaintext environment value in the task def.
    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "inventory"
    db_user: str = "smartretailx_admin"
    db_password: str = ""

    # Full override, used by tests (SQLite) and any local experiment.
    database_url: str | None = None

    orders_queue_url: str = ""
    sns_topic_arn: str = ""
    consumer_enabled: bool = False

    # Resilience knobs (Week 3 Day 2).
    breaker_fail_max: int = 3
    breaker_reset_timeout: int = 30
    retry_attempts: int = 3

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return (
            f"postgresql+psycopg2://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
