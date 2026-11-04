import logging
import os
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import (
    Counter,
    Histogram,
    MeterProvider,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.settings import get_settings

logger = logging.getLogger(__name__)

# Dynatrace expects delta temporality for counters and histograms.
DELTA_PREFERENCE = {
    Counter: AggregationTemporality.DELTA,
    Histogram: AggregationTemporality.DELTA,
    ObservableCounter: AggregationTemporality.DELTA,
    UpDownCounter: AggregationTemporality.CUMULATIVE,
    ObservableUpDownCounter: AggregationTemporality.CUMULATIVE,
    ObservableGauge: AggregationTemporality.CUMULATIVE,
}


@dataclass
class TelemetryHandles:
    tracer: trace.Tracer
    meter: metrics.Meter
    exporter_mode: str


def _signal_url(base: str, signal: str) -> str:
    return f"{base.rstrip('/')}/v1/{signal}"


def configure_telemetry() -> TelemetryHandles:
    settings = get_settings()
    on_k8s = bool(os.getenv("KUBERNETES_SERVICE_HOST"))
    attrs = {
        "service.name": settings.otel_service_name,
        "service.version": "1.1.0",
        "deployment.environment.name": settings.deployment_environment,
        "cloud.provider": "gcp",
        "cloud.platform": "gcp_kubernetes_engine" if on_k8s else "gcp_cloud_run",
    }
    if os.getenv("POD_NAME"):
        attrs["k8s.pod.name"] = os.environ["POD_NAME"]
    if os.getenv("POD_NAMESPACE"):
        attrs["k8s.namespace.name"] = os.environ["POD_NAMESPACE"]
    resource = Resource.create(attrs)

    if settings.otel_collector_endpoint:
        base, headers, exporter_mode = settings.otel_collector_endpoint, {}, "otel-collector"
    elif settings.dynatrace_otlp_endpoint and settings.dynatrace_api_token:
        base = settings.dynatrace_otlp_endpoint
        headers = {"Authorization": f"Api-Token {settings.dynatrace_api_token}"}
        exporter_mode = "dynatrace-otlp-http"
    else:
        base, headers, exporter_mode = "", {}, "console"

    if base:
        trace_exporter = OTLPSpanExporter(endpoint=_signal_url(base, "traces"), headers=headers)
        metric_exporter = OTLPMetricExporter(
            endpoint=_signal_url(base, "metrics"),
            headers=headers,
            preferred_temporality=DELTA_PREFERENCE,
        )
    else:
        trace_exporter = ConsoleSpanExporter()
        metric_exporter = ConsoleMetricExporter()

    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)

    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=10_000)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    logger.info("Telemetry configured: %s", exporter_mode)
    return TelemetryHandles(
        tracer=trace.get_tracer(settings.otel_service_name),
        meter=metrics.get_meter(settings.otel_service_name),
        exporter_mode=exporter_mode,
    )


TELEMETRY = configure_telemetry()
tracer = TELEMETRY.tracer
meter = TELEMETRY.meter

request_counter = meter.create_counter("agent.request.count", description="Number of agent requests")
error_counter = meter.create_counter("agent.error.count", description="Number of failed agent workflows")
workflow_success_counter = meter.create_counter(
    "agent.workflow.success.count", description="Number of successful agent workflows"
)
request_duration = meter.create_histogram(
    "agent.request.duration", unit="s", description="End-to-end agent request duration"
)
rag_duration = meter.create_histogram("rag.retrieval.duration", unit="s", description="RAG retrieval duration")
rag_quality = meter.create_histogram("rag.retrieval.quality", description="Normalized retrieval quality score")
groundedness_metric = meter.create_histogram("agent.groundedness.score", description="Groundedness score 0-1")
relevance_metric = meter.create_histogram("agent.answer_relevance.score", description="Answer relevance score 0-1")
hallucination_metric = meter.create_histogram("agent.hallucination.risk", description="Hallucination risk 0-1")

# GenAI metrics used by the Dynatrace AI Observability app.
token_usage = meter.create_histogram(
    "gen_ai.client.token.usage", unit="{token}", description="Input and output tokens per LLM turn"
)
cost_counter = meter.create_counter(
    "gen_ai.client.cost.usd", unit="USD", description="Estimated LLM cost in USD"
)
eval_score_metric = meter.create_histogram(
    "gen_ai.evaluation.score.value", description="Evaluation score by evaluator name"
)


def emit_judge_result(span, name: str, score: float, passed: bool, explanation: str = "") -> None:
    # Attaches an evaluation result to the inference span and emits it as a metric.
    span.add_event(
        "gen_ai.evaluation.result",
        {
            "gen_ai.evaluation.name": name,
            "gen_ai.evaluation.score.value": float(score),
            "gen_ai.evaluation.score.label": "pass" if passed else "fail",
            "gen_ai.evaluation.explanation": explanation[:500],
        },
    )
    eval_score_metric.record(float(score), {"gen_ai.evaluation.name": name})
