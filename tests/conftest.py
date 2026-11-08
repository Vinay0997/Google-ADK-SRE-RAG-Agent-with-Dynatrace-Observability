import pytest
from opentelemetry import metrics, trace


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    """Stop telemetry exporters before pytest closes captured output."""
    for provider in (
        trace.get_tracer_provider(),
        metrics.get_meter_provider(),
    ):
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            shutdown()
