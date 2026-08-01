from functools import lru_cache

from srx_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "user-service"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
