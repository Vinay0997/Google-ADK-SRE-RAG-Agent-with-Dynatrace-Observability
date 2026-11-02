import logging
from dataclasses import dataclass
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TelemetryHandles:
    tracer: trace.Tracer
    meter: metrics.Meter
    exporter_mode: str


def _signal_url(base: str, signal: str) -> str:
    return f"{base.rstrip('/')}/v1/{signal}"


def configure_telemetry() -> TelemetryHandles:
    """Configure traces + metrics.

    If Dynatrace endpoint/token are present, OTLP/HTTP is used.
    Otherwise console exporters are used so the project remains runnable locally.
    """
    settings = get_settings()
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "1.0.0",
            "deployment.environment.name": settings.deployment_environment,
            "cloud.provider": "gcp",
            "cloud.platform": "gcp_cloud_run",
        }
    )

    trace_provider = TracerProvider(resource=resource)

    if settings.dynatrace_otlp_endpoint and settings.dynatrace_api_token:
        headers = {"Authorization": f"Api-Token {settings.dynatrace_api_token}"}
        trace_exporter = OTLPSpanExporter(
            endpoint=_signal_url(settings.dynatrace_otlp_endpoint, "traces"),
            headers=headers,
        )
        metric_exporter = OTLPMetricExporter(
            endpoint=_signal_url(settings.dynatrace_otlp_endpoint, "metrics"),
            headers=headers,
        )
        exporter_mode = "dynatrace-otlp-http"
    else:
        trace_exporter = ConsoleSpanExporter()
        metric_exporter = ConsoleMetricExporter()
        exporter_mode = "console"

    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)

    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=10_000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    tracer = trace.get_tracer(settings.otel_service_name)
    meter = metrics.get_meter(settings.otel_service_name)
    logger.info("Telemetry configured: %s", exporter_mode)
    return TelemetryHandles(tracer=tracer, meter=meter, exporter_mode=exporter_mode)


TELEMETRY = configure_telemetry()
tracer = TELEMETRY.tracer
meter = TELEMETRY.meter

request_counter = meter.create_counter(
    "agent.request.count",
    description="Number of agent requests",
)
error_counter = meter.create_counter(
    "agent.error.count",
    description="Number of failed agent workflows",
)
workflow_success_counter = meter.create_counter(
    "agent.workflow.success.count",
    description="Number of successful agent workflows",
)
request_duration = meter.create_histogram(
    "agent.request.duration",
    unit="s",
    description="End-to-end agent request duration",
)
rag_duration = meter.create_histogram(
    "rag.retrieval.duration",
    unit="s",
    description="RAG retrieval duration",
)
rag_quality = meter.create_histogram(
    "rag.retrieval.quality",
    description="Normalized retrieval quality score",
)
groundedness_metric = meter.create_histogram(
    "agent.groundedness.score",
    description="Groundedness score from 0 to 1",
)
relevance_metric = meter.create_histogram(
    "agent.answer_relevance.score",
    description="Answer relevance score from 0 to 1",
)
hallucination_metric = meter.create_histogram(
    "agent.hallucination.risk",
    description="Hallucination risk from 0 to 1",
)
