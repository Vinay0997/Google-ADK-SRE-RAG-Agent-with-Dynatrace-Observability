# 7-minute TP2 demo script

## 0:00-1:00 — architecture
Say:

> I built a personal SRE RAG agent using Google ADK and Gemini and deployed it as a container on Google Cloud Run. The main focus is observability. I instrumented the request, ADK workflow, RAG tool, and evaluation stage with OpenTelemetry and export traces and custom metrics to Dynatrace over OTLP/HTTP.

Show the architecture in `docs/ARCHITECTURE.md`.

## 1:00-2:00 — Cloud Run
Show the Cloud Run service/revision and `/healthz`.

Open Swagger at `/docs` or use curl.

Question:

```text
Our Cloud Run service started returning 5xx immediately after deployment. What should I check?
```

## 2:00-4:00 — exact trace in Dynatrace
Copy `trace_id` from the API response.

Explain:

> This is the trace for the exact user request. The parent is agent.request. Inside it I can see agent execution, the RAG retrieval tool, and the evaluation span. I can use the span durations to identify whether latency is in retrieval, agent/model execution, or evaluation.

Show attributes such as:

- `agent.session_id`
- `agent.duration.seconds`
- `rag.best_score`
- `rag.document_ids`
- `evaluation.groundedness`
- `evaluation.hallucination_risk`

## 4:00-5:30 — quality metrics
Show:

- request latency
- request/error counts
- RAG retrieval quality
- groundedness
- answer relevance
- hallucination risk

Say:

> Cloud Run itself does not provide hallucination metrics. I calculate these in the evaluation layer and emit them as OpenTelemetry metrics and trace attributes. Dynatrace receives and trends them.

## 5:30-6:15 — poor-evidence example
Ask something unrelated to the knowledge base, for example:

```text
What is our company's 2027 Nashville office lease amount?
```

Explain that retrieval is weak and the agent should say the runbooks do not have evidence instead of inventing a value.

## 6:15-7:00 — GKE
Say:

> The same container can run in GKE with the same OpenTelemetry application instrumentation. In GKE I can additionally deploy Dynatrace Operator / application injection for Kubernetes-level visibility into pods, namespaces, workloads, and service dependencies. Cloud Run is more managed, so for this demo I use application-level OpenTelemetry with direct OTLP/HTTP export.

## Wrap-up — evaluation dashboard

If time allows, show the ready-made **AI Evaluations and LLM-as-judge** dashboard
and explain the two evaluation layers:

> The golden suite I ran earlier is my deterministic regression layer — it
> checks retrieval hit rate, reference facts, and that the Gemini judge
> produced every score. This dashboard is the continuous-evaluation layer:
> `dt-evals` reads the captured GenAI spans, scores them with an LLM judge,
> and writes the results back to Dynatrace as bizevents, which populate these
> KPIs.

If the dashboard is empty, state it plainly and show the bizevents query from
[DYNATRACE_VERIFICATION.md](DYNATRACE_VERIFICATION.md) to demonstrate you
know exactly what feeds each tile — do not claim it is populated when it is
not. Note that `dt-evals` and this dashboard are scheduled for retirement on
January 1, 2027, so present it as a demonstration of the LLM-as-judge pattern
rather than a permanent platform choice.
