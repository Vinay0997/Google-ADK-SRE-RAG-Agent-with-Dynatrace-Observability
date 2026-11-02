# TP2 likely questions and concise answers

## How does Streamlit data reach Dynatrace?
The Python application is instrumented with OpenTelemetry. It creates spans and metrics while Streamlit serves a user request, and the OTLP HTTP exporters send them to the Dynatrace SaaS OTLP ingest endpoint using an API token. Dynatrace itself is not running inside the Streamlit deployment.

## Why HTTP and not gRPC?
For direct Dynatrace Classic OTLP ingest I use OTLP/HTTP with protobuf. Dynatrace's direct OTLP API documents HTTP ingest; if a client emits gRPC, an OpenTelemetry/Dynatrace Collector can be used as an intermediary.

## How did you instrument Google ADK?
I added application-level spans around the ADK request and execution boundary, and I instrumented the custom RAG tool itself. I also create an evaluation span after the final response. This gives me a deterministic trace hierarchy even if framework internals change.

## Where does groundedness come from?
Not from Streamlit or Dynatrace automatically. The evaluator receives the original question, retrieved evidence, and generated answer and assigns groundedness and relevance scores. I record those scores as OpenTelemetry metrics and span attributes. Hallucination risk in this demo is `1 - groundedness`.

## Is this a production agent?
This is my personal production-style demo deployed with Streamlit. It is intentionally separate from customer systems and contains no customer data.

## How do you monitor retrieval quality?
The retrieval tool records the selected document IDs, top-k, retrieval latency, and a normalized lexical relevance score. For a production RAG system I would add context precision/recall and golden-dataset regression evaluation.

## What changes in GKE?
The application OpenTelemetry code can stay the same. GKE adds Kubernetes control, so Dynatrace Operator/application injection can provide additional pod, node, namespace, workload, and service visibility.

## What is your role in this project?
I built the ADK agent, tool-based RAG, Streamlit interface, OpenTelemetry instrumentation, Dynatrace export, custom evaluation metrics, and the GKE deployment example end-to-end.
