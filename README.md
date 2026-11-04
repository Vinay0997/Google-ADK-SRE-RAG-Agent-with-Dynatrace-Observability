# Google ADK SRE RAG Agent - Dynatrace Observability Demo

A GitHub-ready personal project for demonstrating:

- Google Agent Development Kit (ADK)
- Gemini on Vertex AI
- Tool-based RAG over SRE runbooks
- Google Cloud Run deployment
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
FastAPI /ask on Cloud Run
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

Configure Vertex AI in `.env`:

```text
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

Authenticate locally with Application Default Credentials:

```bash
gcloud auth application-default login
```

Start the API:

```bash
uvicorn main:api --host 0.0.0.0 --port 8080 --reload
```

In another terminal, run the smoke test:

```bash
./scripts/smoke_test.sh
```

Without Dynatrace configuration, traces and metrics use console exporters.

## Deploy to Google Cloud Run

Set your project and region in Cloud Shell or a machine with the Google Cloud CLI:

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
gcloud config set project "$PROJECT_ID"
```

Enable the required Google Cloud APIs and create the Cloud Run service account:

```bash
./scripts/setup_gcp.sh
```

Create a Dynatrace Classic token with `openTelemetryTrace.ingest` and `metrics.ingest`, then store it in Secret Manager:

```bash
./scripts/create_dynatrace_secret.sh
export DT_OTLP_ENDPOINT="https://YOUR_ENVIRONMENT_ID.live.dynatrace.com/api/v2/otlp"
```

Deploy the FastAPI service:

```bash
./scripts/deploy_cloud_run.sh
```

The deploy script prints the Cloud Run URL, Swagger URL, and a `curl` command for `POST /ask`.

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
http POST /ask
└── agent.request
    ├── agent.execute
    │   └── rag.retrieve
    └── evaluation.rag_quality
```

# Critical interview statement

**Cloud Run and Dynatrace do not automatically calculate hallucination or groundedness.** The application evaluator calculates the quality scores from the question, retrieved context, and final answer; OpenTelemetry exports the resulting metrics and trace attributes to Dynatrace.

# GKE

The `k8s/` folder shows how the same container can run as a Kubernetes Deployment. For an interview discussion, explain that the application-level OpenTelemetry instrumentation remains valid, while GKE additionally allows Dynatrace Operator/application injection and Kubernetes-level monitoring.

# Security

- Never commit `.env`.
- Never commit the Dynatrace token.
- Store the Dynatrace token in Google Secret Manager for Cloud Run.
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
