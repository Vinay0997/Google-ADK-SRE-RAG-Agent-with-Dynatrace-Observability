# Google ADK SRE RAG Agent — Dynatrace Observability Demo

A GitHub-ready personal project for demonstrating:

- Google Agent Development Kit (ADK)
- Gemini through Vertex AI or a Gemini API key
- Tool-based RAG over SRE runbooks
- Streamlit deployment
- OpenTelemetry distributed tracing and custom metrics
- Dynatrace OTLP/HTTP ingestion
- Groundedness, relevance, hallucination-risk, and retrieval-quality evaluation
- GKE deployment pattern for discussion

> This is a personal demo. It contains no customer code or customer data.

## Architecture

```text
User
  |
  v
Streamlit UI
  |
  v
Google ADK Agent + Gemini
  |
  +--> search_runbooks tool --> knowledge/runbooks.json
  |
  v
Final answer
  |
  v
RAG evaluator
  |
  +--> groundedness
  +--> answer relevance
  +--> hallucination risk
  |
  v
OpenTelemetry traces + metrics
  |
  v
OTLP/HTTP
  |
  v
Dynatrace SaaS
```

See `docs/ARCHITECTURE.md` for details.

## Repository layout

```text
.
├── app/
│   ├── agent.py
│   ├── evaluator.py
│   ├── rag.py
│   ├── settings.py
│   └── telemetry.py
├── knowledge/runbooks.json
├── scripts/
│   ├── setup_gcp.sh
│   ├── create_dynatrace_secret.sh
│   ├── deploy_cloud_run.sh
│   ├── run_local.sh
│   └── smoke_test.sh
├── k8s/
│   ├── deployment.yaml
│   └── service.yaml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DYNATRACE_SETUP.md
│   ├── DEMO_SCRIPT.md
│   └── INTERVIEW_QA.md
├── tests/test_rag.py
├── streamlit_app.py
├── main.py
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Run locally

Create a virtual environment and install the application:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

For the simplest local and Streamlit Community Cloud setup, create a Gemini API key in Google AI Studio and set these values in `.env`:

```text
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your-gemini-api-key
```

Vertex AI remains supported. Set `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, provide `GOOGLE_CLOUD_PROJECT`, and authenticate with Application Default Credentials if you prefer it.

Start the UI:

```bash
streamlit run streamlit_app.py
```

Open the URL printed by Streamlit, ask an SRE question, and inspect the answer, retrieved runbooks, evaluation scores, and trace ID. Without Dynatrace configuration, traces and metrics use console exporters.

## Deploy to Streamlit Community Cloud

1. Push this repository to GitHub.
2. In Streamlit Community Cloud, create an app from that repository and select `streamlit_app.py` as the main file.
3. In **Advanced settings → Secrets**, add the following. These values are exposed to the app as environment variables; do not commit them.

```toml
GOOGLE_GENAI_USE_VERTEXAI = "FALSE"
GOOGLE_API_KEY = "your-gemini-api-key"

# Optional Dynatrace OTLP export
# DYNATRACE_OTLP_ENDPOINT = "https://YOUR_ENVIRONMENT_ID.live.dynatrace.com/api/v2/otlp"
# DYNATRACE_API_TOKEN = "your-dynatrace-token"
```

The Streamlit deployment route does not require `gcloud` or Cloud Run. The previous FastAPI and Cloud Run files remain available only for an API/container deployment option.

# What to show in Dynatrace

Search/chart these custom metrics:

```text
agent.request.count
agent.error.count
agent.workflow.success.count
agent.request.duration
rag.retrieval.duration
rag.retrieval.quality
agent.groundedness.score
agent.answer_relevance.score
agent.hallucination.risk
```

For traces, explain the hierarchy:

```text
streamlit.agent.request
├── agent.execute
│   └── rag.retrieve
└── evaluation.rag_quality
```

# Critical interview statement

**Streamlit and Dynatrace do not automatically calculate hallucination or groundedness.** The application evaluator calculates the quality scores from the question, retrieved context, and final answer; OpenTelemetry exports the resulting metrics and trace attributes to Dynatrace.

# GKE

The `k8s/` folder shows how the same container can run as a Kubernetes Deployment. For an interview discussion, explain that the application-level OpenTelemetry instrumentation remains valid, while GKE additionally allows Dynatrace Operator/application injection and Kubernetes-level monitoring.

# Security

- Never commit `.env`.
- Never commit the Dynatrace token.
- Store deployment secrets in Streamlit Community Cloud Secrets.
- Do not attach raw sensitive prompts or retrieved customer content as telemetry attributes.
- This sample only records safe IDs, timing, scores, and low-cardinality metadata.

# Useful demo prompts

Good evidence:

```text
Our Cloud Run API has high latency. How should I troubleshoot it?
```

```text
A GKE pod is in CrashLoopBackOff. What should I inspect first?
```

```text
Our RAG groundedness score dropped. How should we troubleshoot retrieval versus generation?
```

Poor evidence / hallucination guardrail test:

```text
What is our company's 2027 Nashville office lease amount?
```

# Notes

This demo uses an in-memory ADK session service, which is suitable for a personal demo. For a production system, use persistent session storage and production identity/access patterns.
