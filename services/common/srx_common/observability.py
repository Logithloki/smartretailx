"""HTTP correlation and optional OpenTelemetry wiring for FastAPI services."""

from __future__ import annotations

import os
from typing import Any

from .logging import set_correlation_id

CORRELATION_HEADER = "X-Correlation-ID"


def current_trace_id() -> str | None:
    """Return the active W3C trace id without making tracing mandatory locally."""
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        return format(context.trace_id, "032x") if context.is_valid else None
    except ImportError:
        return None


def instrument_fastapi(app: Any, service_name: str) -> None:
    """Install correlation middleware and OTLP tracing when an exporter exists.

    Local tests and Docker Compose work without a collector. ECS supplies
    OTEL_EXPORTER_OTLP_ENDPOINT, which activates SDK export to the ADOT sidecar.
    """

    @app.middleware("http")
    async def correlation_middleware(request: Any, call_next: Any):
        correlation_id = set_correlation_id(request.headers.get(CORRELATION_HEADER))
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
