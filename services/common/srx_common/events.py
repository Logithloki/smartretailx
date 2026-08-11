"""Versioned event envelope shared by every asynchronous boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .observability import current_trace_id


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eventType: str = Field(min_length=1, max_length=80)
    eventVersion: str = Field(default="1.0", pattern=r"^\d+\.\d+$")
    eventId: str = Field(min_length=1, max_length=240)
    occurredAt: datetime
    correlationId: str = Field(min_length=1, max_length=200)
    aggregateId: str = Field(min_length=1, max_length=100)
    causationId: str | None = Field(default=None, max_length=240)
    traceId: str | None = Field(default=None, max_length=200)
    payload: dict[str, Any]


def new_event(
    *,
    event_type: str,
    event_id: str,
    aggregate_id: str,
    correlation_id: str,
    payload: dict[str, Any],
    causation_id: str | None = None,
    trace_id: str | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        eventType=event_type,
        eventId=event_id,
        occurredAt=datetime.now(UTC),
        correlationId=correlation_id,
        aggregateId=aggregate_id,
        causationId=causation_id,
        traceId=trace_id or current_trace_id(),
        payload=payload,
    )
