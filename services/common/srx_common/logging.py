"""Structured JSON logging, shared by the four Fargate services.

Uses the Powertools formatter rather than a hand-rolled one so the services and
the Lambdas emit the *same* log shape. That matters more than it sounds: one
CloudWatch Logs Insights query has to span API -> SQS -> Inventory -> SNS ->
notification Lambda, and it can only do that if every hop spells the fields the
same way.

Powertools' own Logger is built around the Lambda handler decorator, which does
not fit a long-running uvicorn process, so the formatter is attached to the
standard library root logger instead. Service code keeps using plain
`logger.info(...)` and `extra={...}` - no Powertools import anywhere else.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

from aws_lambda_powertools.logging.formatter import LambdaPowertoolsFormatter

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def set_correlation_id(value: str | None = None) -> str:
    cid = value or str(uuid.uuid4())
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str | None:
    return _correlation_id.get()


class CorrelationIdFilter(logging.Filter):
    """Attaches the request's correlation id to every record.

    A filter rather than an argument at each call site: the id has to appear on
    logs emitted deep in a call stack (boto3 retries, SQLAlchemy) that know
    nothing about it.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        cid = get_correlation_id()
        if cid:
            record.correlation_id = cid
        return True


def configure_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        LambdaPowertoolsFormatter(
            service=service,
            # Powertools' own key name, so Insights queries are identical
            # across services and Lambdas.
            log_record_order=["level", "location", "message", "timestamp", "service"],
        )
    )
    handler.addFilter(CorrelationIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # uvicorn installs its own handlers; route them through ours or half the
    # request log stays unstructured.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False
