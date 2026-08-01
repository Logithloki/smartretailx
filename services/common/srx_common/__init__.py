"""Shared building blocks for the SmartRetailX services."""

from .auth import Authenticator, Principal, principal_from_claims
from .config import BaseServiceSettings
from .logging import configure_logging, get_correlation_id, set_correlation_id

__all__ = [
    "Authenticator",
    "Principal",
    "principal_from_claims",
    "BaseServiceSettings",
    "configure_logging",
    "get_correlation_id",
    "set_correlation_id",
]
