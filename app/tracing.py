"""
OpenTelemetry tracing configuration for Cloud Trace.

Initialises the OTel SDK with:
- Cloud Trace exporter (auto-detected on Cloud Run)
- Console exporter fallback for local development
- FastAPI auto-instrumentation
- requests library auto-instrumentation

Usage:
    Call ``init_tracing(app)`` once at startup from main.py.
    Use ``get_tracer(__name__)`` in any module to create spans.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "morning-brief")
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


def _is_cloud_run() -> bool:
    """Detect if running inside Cloud Run (K_SERVICE env var is set)."""
    return bool(os.getenv("K_SERVICE"))


def init_tracing(app) -> None:  # noqa: ANN001 (FastAPI type avoided for import order)
    """
    Bootstrap OpenTelemetry and instrument the FastAPI app.

    On Cloud Run the spans are exported to Cloud Trace.
    Locally they are printed to the console.
    """
    resource = Resource.create(
        {
            "service.name": _SERVICE_NAME,
            "deployment.environment": _ENVIRONMENT,
        }
    )

    provider = TracerProvider(resource=resource)

    if _is_cloud_run():
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(CloudTraceSpanExporter())
            )
            logger.info("Tracing: Cloud Trace exporter active")
        except Exception:
            logger.exception("Failed to init Cloud Trace exporter, falling back to console")
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("Tracing: Console exporter active (local dev)")

    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI (inbound HTTP)
    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument requests (outbound HTTP, e.g. feedparser uses urllib
    # but Gmail API client uses requests under the hood)
    RequestsInstrumentor().instrument()

    logger.info("OpenTelemetry tracing initialised for '%s'", _SERVICE_NAME)


def get_tracer(name: str) -> trace.Tracer:
    """Return a tracer scoped to the given module name."""
    return trace.get_tracer(name)
