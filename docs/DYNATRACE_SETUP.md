# Dynatrace setup

For how to verify every signal in the Dynatrace UI — metrics, traces, DQL
queries, and the ready-made AI Evaluations dashboard — see
[DYNATRACE_VERIFICATION.md](DYNATRACE_VERIFICATION.md).

## 1. Create a Dynatrace Classic access token
For this repository you need:

- `openTelemetryTrace.ingest`
- `metrics.ingest`

If you later add OTLP log export, also add `logs.ingest`.

Never commit the token to GitHub.

## 2. Identify the OTLP base endpoint
For Dynatrace SaaS Classic:

```text
https://<environment-id>.live.dynatrace.com/api/v2/otlp
```

Do not use `.live.apps.dynatrace.com` as the OTLP ingest hostname.

This project appends:

- `/v1/traces`
- `/v1/metrics`

and uses binary OTLP over HTTP/protobuf.

## 3. Store the token in Google Secret Manager

```bash
export PROJECT_ID="your-project-id"
./scripts/create_dynatrace_secret.sh
```

## 4. Deploy with the endpoint

```bash
export PROJECT_ID="your-project-id"
export REGION="us-central1"
export DT_OTLP_ENDPOINT="https://YOUR_ENVIRONMENT_ID.live.dynatrace.com/api/v2/otlp"
./scripts/deploy_cloud_run.sh
```

## 5. Generate a trace
Use the URL printed by the deployment script:

```bash
export SERVICE_URL="https://...run.app"
curl -s -X POST "$SERVICE_URL/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Our Cloud Run service started returning 5xx immediately after deployment. What should I check?"}' \
  | python -m json.tool
```

The JSON response includes a `trace_id`. Use it during the demo to correlate the exact request in Dynatrace.

## 6. Metrics to search for

- `agent.request.count`
- `agent.error.count`
- `agent.workflow.success.count`
- `agent.request.duration`
- `rag.retrieval.duration`
- `rag.retrieval.quality`
- `agent.groundedness.score`
- `agent.answer_relevance.score`
- `agent.hallucination.risk`

## Troubleshooting

### HTTP 401/403 from OTLP exporter
Check the token and ingest scopes.

### HTTP 404
Confirm the base endpoint is `https://<environment-id>.live.dynatrace.com/api/v2/otlp` and not the UI `.apps` hostname.

### No telemetry but agent works
Check Cloud Run logs. The application logs which telemetry exporter mode was selected at startup. If it says `console`, the endpoint/token were not supplied to the service.
