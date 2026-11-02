# Architecture

## Goal
Demonstrate a personal, production-style Google ADK agent with observable RAG execution and live quality evaluation.

## Request path

```text
User / browser
        |
        v
Streamlit application
        |
        v
Google ADK Runner + Gemini
        |
        +--> search_runbooks tool --> local runbook knowledge base
        |
        v
Agent final answer
        |
        v
RAG evaluator (Gemini judge, with local fallback)
        |
        +--> groundedness
        +--> answer relevance
        +--> hallucination risk = 1 - groundedness
        |
        v
OpenTelemetry SDK
        |
        +--> distributed traces
        +--> custom metrics
        |
        v
OTLP/HTTP
        |
        v
Dynatrace SaaS
```

## Important interview statement
Streamlit and Dynatrace do **not** calculate hallucination or groundedness. The application evaluation layer calculates those values from the question, retrieved evidence, and generated answer. OpenTelemetry transports the resulting telemetry to Dynatrace.

## Trace hierarchy
The project intentionally creates these spans:

- `streamlit.agent.request`
  - `agent.execute`
    - `rag.retrieve` (tool span)
  - `evaluation.rag_quality`

Google ADK may also emit framework-level telemetry depending on ADK/runtime configuration. The custom spans above are the stable demo surface.

## Streamlit deployment
Streamlit Community Cloud hosts the UI. The project uses application-level OpenTelemetry and sends OTLP/HTTP directly to Dynatrace when the optional Dynatrace settings are configured.

For GKE, keep the same application OpenTelemetry instrumentation. Additionally, a customer can use Dynatrace Operator / Kubernetes application injection for richer cluster, pod, namespace, and workload observability.
