# Verifying the project in Dynatrace

This guide explains every signal this project sends to Dynatrace, exactly how to
check each one in the Dynatrace UI, and what to do when a panel is empty.

## Where the data goes

The project produces evaluation data through three distinct paths:

| Path | What it is | Where to see it |
|---|---|---|
| A. App metrics | OpenTelemetry histograms/counters sent over OTLP | Data Explorer, Metrics browser, custom dashboards |
| B. App traces | Distributed traces with `agent.*`, `rag.*`, `gen_ai.*`, `evaluation.*` span attributes | Distributed traces, Notebooks (DQL) |
| C. dt-evals results | Evaluation results ingested as bizevents by the `dt-evals` CLI | Ready-made "AI Evaluations and LLM-as-judge" dashboard |

Path C is the only thing that populates the ready-made
**AI Evaluations and LLM-as-judge - AI Observability** dashboard. If that
dashboard shows `null`, `0`, and "No records", it means no `dt-evals` run has
written evaluation bizevents yet — not that your application telemetry is
missing. Paths A and B work independently of it.

## A. Check the application metrics

Open **Data Explorer** (or a Notebook) and query these metric keys:

| Metric | Meaning |
|---|---|
| `agent.request.count` | Requests to `/ask` |
| `agent.error.count` | Failed agent workflows |
| `agent.workflow.success.count` | Successful workflows |
| `agent.request.duration` | Request latency (s) |
| `rag.retrieval.duration` | RAG retrieval time |
| `rag.retrieval.quality` | Normalized retrieval score |
| `agent.groundedness.score` | Judge groundedness score (0-1) |
| `agent.answer_relevance.score` | Judge answer relevance (0-1) |
| `agent.hallucination.risk` | Hallucination risk (0-1) |
| `gen_ai.evaluation.score.value` | Evaluation score split by `gen_ai.evaluation.name` |
| `eval.golden.pass.count` / `eval.golden.fail.count` | Golden suite outcomes (run from `evals.run_golden`) |

Notebook query for score trends:

```sql
timeseries avg_groundedness = avg(agent.groundedness.score),
  avg_relevance = avg(agent.answer_relevance.score),
  avg_risk = avg(agent.hallucination.risk)
```

Notebook query for golden-suite pass/fail counts:

```sql
timeseries passes = sum(eval.golden.pass.count), fails = sum(eval.golden.fail.count)
```

## B. Check the traces and span attributes

Send a request and copy the `trace_id` from the JSON response, then open
**Distributed traces** and search for that trace ID. Inside a single request
trace you should find:

| Span | Key attributes |
|---|---|
| `agent.request` (parent) | `agent.session_id`, `agent.user_id`, `agent.user_role` |
| `agent.execute` | `agent.tool.calls`, `agent.duration.seconds` |
| `chat <model>` (GenAI inference) | `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cost_usd`, `gen_ai.input.messages`, `gen_ai.output.messages` |
| RAG retrieval | `rag.document_ids`, `rag.best_score`, `rag.role`, `rag.top_k` |
| `evaluation.rag_quality` | `evaluation.groundedness`, `evaluation.answer_relevance`, `evaluation.hallucination_risk`, `evaluation.evaluator` |
| Guardrail | `guardrail.action`, `guardrail.name`, `guardrail.reason` |

The GenAI inference span also carries a `gen_ai.evaluation.result` span event
with the judge score, pass/fail label, and explanation.

Notebook queries:

```sql
// Latest agent requests with evaluation attributes
fetch spans
| filter span.name == "evaluation.rag_quality"
| fields timestamp, trace_id, evaluation.evaluator,
        evaluation.groundedness, evaluation.answer_relevance,
        evaluation.hallucination_risk
| sort timestamp desc
```

```sql
// Token usage and cost per model invocation
fetch spans
| filter isNull(parent_id) == false and span.name == "chat *"
| fields timestamp, gen_ai.request.model,
        gen_ai.usage.input_tokens, gen_ai.usage.output_tokens,
        gen_ai.usage.cost_usd
| sort timestamp desc
```

```sql
// Guardrail decisions (refusals)
fetch spans
| filter guardrail.action == "block"
| fields timestamp, guardrail.name, guardrail.reason
```

To correlate a live request end to end: POST to `/ask`, take the `trace_id`
from the response, and paste it into the Distributed traces search. That is
the single trace containing the request, retrieval, model, and evaluation
spans for that exact question.

## C. Populate and check the ready-made AI Evaluations dashboard

The **AI Evaluations and LLM-as-judge** ready-made dashboard is fed by the
open-source `dt-evals` CLI, which reads your captured GenAI spans, sends them
to an LLM judge, and writes results back to Dynatrace as
`gen_ai.evaluation.result` bizevents.

### 1. Validate the CLI configuration

From the directory holding `sre-agent-gke-evals.dt-eval.yaml` (Node.js 20+):

```bash
npx --yes @dynatrace-oss/dt-evals validate
```

If the token is missing after a shell restart:

```bash
read -rsp "Dynatrace platform token: " DT_API_TOKEN
printf '\n'
export DT_API_TOKEN
```

### 2. Preview inputs without spending judge calls

Submit a fresh question through the agent first, then:

```bash
npx --yes @dynatrace-oss/dt-evals run \
  --config sre-agent-gke-evals.dt-eval.yaml \
  --since 15m \
  --sample 100 \
  --metric relevance \
  --dry-run
```

If it finds zero inputs, diagnose before spending judge calls:

```bash
npx --yes @dynatrace-oss/dt-evals doctor --skip-token
```

### 3. Run the live evaluation

```bash
npx --yes @dynatrace-oss/dt-evals run \
  --config sre-agent-gke-evals.dt-eval.yaml \
  --since 15m \
  --sample 100 \
  --metric relevance
```

Check the run history:

```bash
npx --yes @dynatrace-oss/dt-evals runs list --limit 5
```

### 4. Verify the bizevents arrived

In a Notebook, with a timeframe that covers the run:

```sql
fetch bizevents
| filter event.type == "gen_ai.evaluation.result"
| summarize avg_score = avg(gen_ai.evaluation.score.value),
    by: {gen_ai.evaluation.name}
| sort avg_score asc
```

If this returns rows, the dashboard KPIs (quality score, pass rate,
evaluations count) will populate on refresh.

### 5. Read the dashboard correctly

| Dashboard element | Empty means |
|---|---|
| Overall quality score `null` | No evaluation bizevents in the timeframe |
| Pass rate `0.0` (red) | No results — not a failing score |
| Evaluations `0` | No `dt-evals` run completed (or results outside timeframe) |
| Heatmap / distribution "No records" | Same cause as above |

Also check the dashboard filter bar (`Service`, `Provider`, `JudgeModel`,
`Metric`, `EvalType`, `ScoreLabel`, `RunId`). A filter narrower than your
ingested data shows "No records" even when data exists — reset filters to `*`
and widen the timeframe before troubleshooting ingestion.

## Troubleshooting

| Symptom | Check |
|---|---|
| Dashboard all zeros | Run the bizevents query above; if empty, no `dt-evals` results were ingested |
| `dt-evals run` finds zero inputs | Fresh traffic inside `--since` window; `doctor --skip-token`; service-name filter in the YAML matches the OTLP service name |
| 401/403 from OTLP exporter | Token scopes `openTelemetryTrace.ingest`, `metrics.ingest` |
| 404 from OTLP | Base endpoint must be `https://<env-id>.live.dynatrace.com/api/v2/otlp` |
| No telemetry but agent answers | Deployment logs show exporter mode; `console` means endpoint/token were not supplied |
| Metrics present, dashboard empty | Expected — the dashboard only reads `dt-evals` bizevents, not app metrics |

Lifecycle note: `dt-evals` and the ready-made evaluation dashboard are
scheduled for retirement on January 1, 2027. Treat this integration as a
demonstration of LLM-as-judge evaluation, not a permanent platform choice.

## Wrap-up checklist

A complete demo of this project shows all three paths:

1. **Golden suite green** — `scripts/eval_pipeline.sh` exits 0 with
   `llm_judge_not_used` absent from every case.
2. **Traces** — one `trace_id` from a live request opens the full span tree
   with retrieval, model, and evaluation attributes.
3. **Metrics** — groundedness, relevance, and risk trend in Data Explorer.
4. **Dashboard** — `dt-evals run` completes and the bizevents query returns
   rows, populating the ready-made AI Evaluations dashboard.
