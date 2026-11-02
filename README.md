# Google ADK SRE RAG Agent — Dynatrace Observability Demo

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
FastAPI /ask
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

# Run from Google Cloud Shell

## 1. Clone your GitHub repo

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

## 2. Set your project

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
gcloud config set project "$PROJECT_ID"
```

Confirm billing is enabled for the project.

## 3. Enable APIs and create the service account

```bash
./scripts/setup_gcp.sh
```

This enables Cloud Run, Cloud Build, Artifact Registry, Vertex AI, and Secret Manager and creates `adk-observability-sa`.

## 4. Create a Dynatrace token

Create a Dynatrace Classic token with:

- `openTelemetryTrace.ingest`
- `metrics.ingest`

Then store it without exposing it in GitHub:

```bash
./scripts/create_dynatrace_secret.sh
```

## 5. Set the Dynatrace OTLP endpoint

```bash
export DT_OTLP_ENDPOINT="https://YOUR_ENVIRONMENT_ID.live.dynatrace.com/api/v2/otlp"
```

## 6. Deploy to Cloud Run

```bash
./scripts/deploy_cloud_run.sh
```

The script prints the Cloud Run URL and a ready-to-run curl command.

## 7. Test the agent

```bash
export SERVICE_URL="YOUR_CLOUD_RUN_URL"

curl -s -X POST "$SERVICE_URL/ask" \
  -H 'Content-Type: application/json' \
  -d '{
    "question":"Our Cloud Run service started returning 5xx immediately after deployment. What should I check?"
  }' | python -m json.tool
```

Example response shape:

```json
{
  "answer": "...",
  "session_id": "session-...",
  "trace_id": "...",
  "retrieved_documents": [
    {"id": "cloud-run-5xx", "title": "Cloud Run 5xx After Deployment", "score": 1.0}
  ],
  "evaluation": {
    "groundedness": 0.94,
    "answer_relevance": 0.96,
    "hallucination_risk": 0.06,
    "evaluator": "gemini-judge"
  },
  "telemetry_exporter": "dynatrace-otlp-http",
  "duration_seconds": 2.431
}
```

Use `trace_id` to find/correlate the exact request in Dynatrace.

# Run locally in Cloud Shell first

If you want to validate before deployment:

```bash
cp .env.example .env
sed -i "s/your-gcp-project-id/$PROJECT_ID/" .env
./scripts/run_local.sh
```

In another Cloud Shell tab:

```bash
./scripts/smoke_test.sh
```

Without Dynatrace configuration, traces and metrics use console exporters.

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

**Cloud Run does not automatically calculate hallucination or groundedness.** The application evaluator calculates the quality scores from the question, retrieved context, and final answer; OpenTelemetry exports the resulting metrics and trace attributes to Dynatrace.

# GKE

The `k8s/` folder shows how the same container can run as a Kubernetes Deployment. For an interview discussion, explain that the application-level OpenTelemetry instrumentation remains valid, while GKE additionally allows Dynatrace Operator/application injection and Kubernetes-level monitoring.

# Security

- Never commit `.env`.
- Never commit the Dynatrace token.
- Store the token in Secret Manager for Cloud Run.
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
