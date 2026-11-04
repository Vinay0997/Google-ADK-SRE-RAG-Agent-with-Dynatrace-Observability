# End-to-end GKE deployment

Everything runs in Google Cloud: UI, agent, OpenTelemetry Collector, scheduled evaluations, and the BigQuery audit sink. Dynatrace stays external as SaaS.

```text
Streamlit UI (LoadBalancer) -> ADK agent (3+ replicas, HPA) -> Vertex AI Gemini
                                   |-> BigQuery agent_executions (audit rows)
                                   |-> OTLP -> OTel Collector -> Dynatrace
CronJob golden-eval -> agent /ask -> eval metrics -> Collector -> Dynatrace
```

## Deploy
```bash
export PROJECT_ID=your-project REGION=us-central1
export DT_OTLP_ENDPOINT="https://ENV_ID.live.dynatrace.com/api/v2/otlp"
export DT_API_TOKEN="dt0c01...."   # scopes: openTelemetryTrace.ingest, metrics.ingest
./scripts/setup_gke.sh     # APIs, Autopilot cluster, Workload Identity, BigQuery table
./scripts/deploy_gke.sh    # build images, apply manifests
./scripts/demo_gke.sh      # pods, logs, requests, BigQuery rows
```

## Verify in Dynatrace
1. Install the **AI Observability** app from the Dynatrace Hub.
2. Open it and filter by service `google-adk-sre-agent-gke`.
3. Check **Prompts** (needs `gen_ai.input.messages` / `gen_ai.output.messages`, `gen_ai.request.model`, token usage). Set `CAPTURE_PROMPTS=true`.
4. Check model, token, and cost tiles (`gen_ai.client.token.usage`, `gen_ai.client.cost.usd`).
5. Evaluations: each request span carries `gen_ai.evaluation.result` events (groundedness, hallucination_risk). For LLM-as-a-judge events in the app, run Dynatrace `dt-evals` against these spans (see Dynatrace docs, "Run LLM-as-a-judge evaluations with dt-evals").
6. Metrics Explorer: `agent.groundedness.score`, `agent.hallucination.risk`, `rag.retrieval.quality`, `eval.golden.pass.count`.

## Notes
- Prompt capture sends question and answer text to Dynatrace. Disable with `CAPTURE_PROMPTS=false` for sensitive data.
- Cost uses `INPUT_PRICE_PER_MTOK` / `OUTPUT_PRICE_PER_MTOK` in `k8s/configmap.yaml`. Set real pricing.
- Metrics use delta temporality, which Dynatrace requires for counters and histograms.
- The in-memory ADK session store is per pod. With several replicas, a follow-up in the same session may hit a different pod. Use persistent sessions for production.
