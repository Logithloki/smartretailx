"""Settings shared by all four services.

The single most important line in this file is the default for `env`. It is
"production", not "local": an unset ENV must never silently disable security
(guide Week 2, "auth fail-closed").
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # FAIL CLOSED. A missing or empty ENV behaves exactly like production.
    env: str = "production"

    app_region: str = "eu-west-1"
    # Set only for LocalStack; None means "use the real AWS endpoints".
    aws_endpoint_url: str | None = None
    log_level: str = "INFO"

    cognito_user_pool_id: str | None = None
    cognito_app_client_id: str | None = None
    cognito_issuer: str | None = None

    # Groups handed to the stub principal in local mode. Lets you exercise the
    # admin UI locally without minting a token, while defaulting to the least
    # privileged role so RBAC bugs surface in development.
    local_dev_groups: str = "customer"

    @property
    def is_local(self) -> bool:
        return self.env.strip().lower() == "local"

    @property
    def local_dev_group_list(self) -> tuple[str, ...]:
        return tuple(g.strip() for g in self.local_dev_groups.split(",") if g.strip())

    def boto_kwargs(self) -> dict:
        """Client kwargs that point at LocalStack locally and real AWS in prod."""
        kwargs: dict = {"region_name": self.app_region}
        if self.aws_endpoint_url:
            kwargs["endpoint_url"] = self.aws_endpoint_url
        return kwargs
