"""Shared building blocks for the SmartRetailX services."""

from .auth import Authenticator, Principal, principal_from_claims
from .config import BaseServiceSettings
from .events import EventEnvelope, new_event
from .logging import configure_logging, get_correlation_id, set_correlation_id
from .observability import current_trace_id, instrument_fastapi
from .pricing import PriceQuote, Promotion, effective_price, money

__all__ = [
    "Authenticator",
    "Principal",
    "principal_from_claims",
    "BaseServiceSettings",
    "EventEnvelope",
    "configure_logging",
    "get_correlation_id",
    "set_correlation_id",
    "new_event",
    "current_trace_id",
    "instrument_fastapi",
    "PriceQuote",
    "Promotion",
    "effective_price",
    "money",
]
