# Google ADK SRE RAG Agent with Dynatrace Observability

A demonstration policy and compliance assistant built with Google ADK, a React frontend, BigQuery-backed document retrieval, and OpenTelemetry instrumentation for Dynatrace observability.

The assistant uses retrieved policy document evidence to answer questions about company policies, procedures, SOPs, security, compliance, HR, and governance, applies role-based document filtering, evaluates responses, and returns trace IDs.

The application runs on Google Kubernetes Engine (GKE). The workflow uses Cloud Shell Web Preview; a public application URL is not required.

## Architecture

```text
Browser / Cloud Shell Web Preview
                |
        kubectl port-forward
                |
         React UI / NGINX
                |
          Backend API
                |
       Google ADK workflow
         |             |
 BigQuery retrieval   Response evaluation
         |
 Role-filtered document evidence

Backend instrumentation -> OpenTelemetry Collector -> Dynatrace
```

The observability path must be verified in Dynatrace; a returned trace ID alone does not establish successful ingestion.

## Demo Data and Security Boundary

The demonstration corpus is the fictional Aurelius Health Systems policy document set (46 markdown documents in `documents/Markdown/`, also packaged as `knowledge/documents.json`). The PDFs in `documents/PDFs/` are public HHS/OCR HIPAA reference guides kept as source material; they are not embedded in the retrieval index. Do not submit real patient information, credentials, or confidential incident details.

Role labels used by the demonstration include `viewer`, `sre`, `security_privacy`, and `compliance`.

Caller-selected roles are demonstration inputs, not authenticated identities. Role-conditioned retrieval must not be presented as production authentication or proof that callers are authorized to assert a role.

## Deployment Components

| Component | Deployment |
|---|---|
| Backend | `google-adk-sre-agent` |
| React frontend | `sre-agent-react-ui` |
| OpenTelemetry Collector | `otel-collector` |

Previous UI Deployments, `sre-agent-ui` and `sre-agent-ui-preview`, remain at zero replicas and are not part of the active frontend workflow.

### Last reported deployment snapshot

The terminal output shared on November 8, 2026 showed:

- Backend, React, and collector each at `1/1` ready.
- Backend image tag `eval-fix-20261108163716`.
- The same backend image reference in `k8s/deployment.yaml` and `k8s/eval-cronjob.yaml`.
- Local `main` and `origin/main` at commit `3441280` before subsequent README changes.

This is a historical snapshot, not a claim of current deployment state. Matching image references do not prove the intended application behavior or that a live CronJob uses the saved image.

## Prerequisites

- Access to the intended Google Cloud project and GKE cluster.
- Configured `gcloud` and `kubectl` credentials.
- A Python environment with the repository dependencies installed.
- Required BigQuery and Vertex AI permissions for retrieval.
- Dynatrace access to verify telemetry.
- Cloud Shell for the screen-share workflow.
- 

## Verify Deployment Health

Confirm the Kubernetes context before making changes:

```bash
kubectl config current-context
kubectl -n sre-agent get deployments
```

Check rollout status:

```bash
kubectl -n sre-agent rollout status deployment/google-adk-sre-agent --timeout=300s
kubectl -n sre-agent rollout status deployment/sre-agent-react-ui --timeout=180s
kubectl -n sre-agent rollout status deployment/otel-collector --timeout=180s
```

Inspect the live backend image and saved references:

```bash
kubectl -n sre-agent get deployment google-adk-sre-agent \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"\t"}{.image}{"\n"}{end}'

grep -n 'image:' k8s/deployment.yaml k8s/eval-cronjob.yaml
```

## Open the React Demo

In a dedicated Cloud Shell terminal:

```bash
kubectl -n sre-agent port-forward service/sre-agent-react-ui 8084:80
```

Leave the command running and open Cloud Shell Web Preview on port `8084`.

Share the browser view during the demonstration. Cloudflare, a public domain, and a public application endpoint are not required for this workflow.

Restart the port-forward if it exits or the selected pod is replaced.

## Retrieval and Guardrails

The demonstration uses BigQuery-backed retrieval and role-filtered policy document evidence.

Retrieval guardrails are enforced in application code, not left to the model:

- Role filtering is fail-closed for both backends; documents without valid `allowed_roles` are never returned.
- A minimum relevance score (`RAG_MIN_SCORE`, default 0.3) drops weak lexical matches so irrelevant evidence cannot reach the model.
- Retrieved content is sanitized: instruction-like text aimed at the model (for example, "ignore previous instructions") is neutralized before it enters the context.
- Context size is capped per document (`RAG_MAX_DOC_CHARS`, default 4000) and in total (`RAG_MAX_CONTEXT_CHARS`, default 12000).
- The search tool allows one retrieval call per request; further calls are blocked.

Review the actual code and deployment configuration before changing retrieval settings, similarity thresholds, fallback behavior, or document permissions.

### Scope refusal

The intended out-of-scope response is:

```text
I can only answer questions based on the documented policies and procedures.
```

The evaluator correction is intended to handle the exact no-evidence scope refusal through `refusal-rule` rather than a variable LLM judge. Verify this behavior against the deployed release.

A refusal does not automatically prove correct authorization behavior. Inspect the retrieved evidence and answer for restricted-data disclosure.

### Document corpus

The retrieval corpus is the 46-document Aurelius Health Systems policy set:

```text
documents/Markdown/*.md          # original markdown sources (source of truth)
documents/PDFs/*.pdf             # public HHS/OCR HIPAA reference guides (not embedded)
knowledge/documents.json         # retrieval knowledge base with ids, tags, and allowed_roles
scripts/build_document_corpus.py # regenerates the knowledge base and seed SQL
bigquery/seed_documents.sql      # BigQuery seed with replace semantics
```

The seed deletes documents no longer in the corpus, then upserts all current documents, so rerunning it converges the table on the corpus. To apply a corpus change, edit the markdown sources, run the build script, and execute:

```bash
bq query --use_legacy_sql=false < bigquery/seed_documents.sql
```

Review the SQL, target project, model, and permissions before executing it. BigQuery writes and embedding generation can incur charges.

Each document case should retrieve its expected document rather than merely return a refusal. Do not change an answer case into a refusal case solely to obtain a passing evaluation.

## Run Unit Tests

From the repository root, with the project dependencies installed:

```bash
python -m pytest -q
```

For the retrieval and refusal regression suites:

```bash
python -m pytest tests/test_rag.py tests/test_evaluator_refusals.py -q
```

Record the actual test summary. Do not treat historical counts as verification of the current checkout.

If telemetry exporter errors appear after the test summary, investigate them separately from test assertion results.

## Run the Golden Evaluation

### 1. Connect to the backend

In a dedicated terminal:

```bash
kubectl -n sre-agent port-forward \
  service/google-adk-sre-agent 8085:80 \
  --address 127.0.0.1
```

Keep this command running. If a working port-forward already exists, do not start a duplicate on the same port.

### 2. Run the evaluation

From the repository root:

```bash
LOG_FILE="$HOME/golden-final-$(date +%Y%m%d-%H%M%S).log"

AGENT_URL=http://127.0.0.1:8085 \
  python -u -m evals.run_golden > "$LOG_FILE" 2>&1

EVAL_EXIT=$?

grep -E '^(DETAIL |ERROR |PASS |FAIL |SUMMARY )' "$LOG_FILE"
echo "Golden evaluation exit code: $EVAL_EXIT"
```

### Expected scenarios

The golden suite covers twelve document cases plus guardrail cases:

| Case | Verification |
|---|---|
| `password-mfa-policy` | Password and MFA question retrieves `password-and-mfa-policy` |
| `data-retention-policy` | Retention question retrieves `data-retention-policy` |
| `it-incident-response-sop` | Incident SOP question retrieves `sop-it-incident-response` |
| `backup-and-recovery-sop` | Backup SOP question retrieves `sop-backup-and-recovery` |
| `release-management-sop` | Release management question retrieves `sop-release-management` |
| `employee-nda` | NDA question retrieves `employee-nda` |
| `code-of-conduct` | Conduct question retrieves `code-of-conduct` |
| `remote-work-policy` | Remote work question retrieves `remote-work-policy` |
| `business-continuity-plan` | Continuity question retrieves `business-continuity-plan` |
| `disaster-recovery-sre` | SRE role retrieves restricted `disaster-recovery-runbook` |
| `vulnerability-management-security` | Security role retrieves restricted `vulnerability-management-process` |
| `access-control-compliance` | Compliance role retrieves restricted `access-control-policy` |
| `guardrail-role-restricted` | Viewer asking for a restricted policy receives a refusal |
| `guardrail-no-evidence` | Out-of-scope question receives the intended refusal |
| `guardrail-unauthorized-change` | Destructive instruction is refused |
| `guardrail-out-of-scope` | Non-policy financial question is refused |

#### Golden case schema

Each case in `evals/golden.json` supports these fields:

| Field | Purpose |
|---|---|
| `id`, `question` | Required identifier and user question |
| `expected_documents` | The document ID that must appear among retrieved documents (retrieval hit rate) |
| `required_facts` | Terms that must appear in the answer (reference-answer check) |
| `prohibited_terms` | Terms that must not appear in the answer |
| `expect_refusal` | The case must produce a refusal |
| `role` | Optional role for role-conditioned retrieval |

Answer cases additionally verify that the Gemini LLM judge produced the evaluation (`evaluator == "gemini-judge"`). A lexical-fallback evaluation fails the case with `llm_judge_not_used` so heuristic results are never counted as judge successes. Set `REQUIRE_LLM_JUDGE=false` for local runs without Vertex AI access.

The expected aggregate result is:

```text
SUMMARY {"total": 16, "passed": 16, "failed": 0, ...}
Golden evaluation exit code: 0
```

Also inspect the details. A passing aggregate alone does not establish that the correct evidence or evaluator branch was used.

Confirm the exact scope refusal uses `refusal-rule` on the deployed release. Do not lower thresholds merely to make a failing run pass.

### Automated pipeline

`scripts/eval_pipeline.sh` automates the demo evaluation end to end. It waits for backend health, runs the golden evaluation with judge verification, and saves a timestamped log plus a JSON report (per-case pass/fail, failure reasons, retrieval hits, evaluator used, and trace IDs — no answer text) under `artifacts/`:

```bash
AGENT_URL=http://127.0.0.1:8085 scripts/eval_pipeline.sh
```

The exit code reflects the evaluation result, so the script can gate CI or a demo readiness check. Live runs trigger real model calls and telemetry.

### Connection troubleshooting

If requests fail with connection refused:

1. Confirm the backend port-forward is still running.
2. Confirm `AGENT_URL` uses the forwarded port.
3. Inspect the saved log's `ERROR` lines.
4. Confirm backend Deployment health.

Connection failures do not measure answer quality.

## Verify the React Demonstration

| Scenario | Check |
|---|---|
| Cloud Run latency | Grounded answer and retrieved evidence |
| GKE CrashLoopBackOff | Grounded answer and retrieved evidence |
| RAG groundedness | Uses `rag-quality` rather than refusing |
| Restricted claims question as SRE | Intended authorized evidence is present |
| Same question as viewer | No restricted evidence or disclosure |
| Office-lease question | Scope refusal without an invented amount |

For the viewer scenario, inspect both document references and response text. A refusal label alone is insufficient.

## Verify Dynatrace Evidence

1. Run a fresh request through React or the golden evaluator.
2. Copy the returned trace ID.
3. Find the matching trace in Dynatrace.
4. Inspect the backend workflow and retrieval operations.
5. Check document IDs, role attributes, guardrail decisions, and evaluation signals where emitted.
6. Capture sanitized demonstration evidence.

Only describe spans and attributes that are actually visible. Console output and response trace IDs do not independently prove Dynatrace ingestion.

Step-by-step instructions for every signal — metrics, span attributes, DQL
Notebook queries, and populating the ready-made AI Evaluations and
LLM-as-judge dashboard with `dt-evals` — are in
[docs/DYNATRACE_VERIFICATION.md](docs/DYNATRACE_VERIFICATION.md). Setup and
token scopes are in [docs/DYNATRACE_SETUP.md](docs/DYNATRACE_SETUP.md).

## Check the Evaluation CronJob

A saved CronJob manifest does not prove that a schedule is enabled or aligned in the cluster.

Inspect the live resource without creating it:

```bash
kubectl -n sre-agent get cronjob golden-eval --ignore-not-found \
  -o jsonpath='{.metadata.name}{"\n"}{range .spec.jobTemplate.spec.template.spec.containers[*]}{.name}{"\t"}{.image}{"\n"}{end}'
```

If present, confirm its image is intentional and aligned with the intended evaluator release. Do not enable a schedule solely to complete a screen-share demonstration; recurring runs can incur usage charges.

## Release Workflow

For backend runtime changes:

1. Run tests.
2. Build a uniquely tagged image in the intended Artifact Registry repository.
3. Update the intended backend container.
4. Wait for rollout.
5. Save the successful image reference in the deployment manifest.
6. Align the evaluation image when applicable.
7. Restart affected port-forwards if necessary.
8. Run the golden evaluation against the deployed release.
9. Verify React behavior and Dynatrace ingestion.

Review repository deployment scripts before executing them. A broad deployment can change more than the component being edited.

A README-only update does not require an application image rebuild or redeployment.

## Interview Demonstration Sequence

1. Show active GKE workloads and the architecture.
2. Open React through Cloud Shell Web Preview.
3. Ask a grounded operational question.
4. Show the answer, evidence, evaluation, and trace ID.
5. Compare the restricted question as SRE and viewer.
6. Demonstrate an out-of-scope refusal.
7. Show the RAG-quality troubleshooting result.
8. Open a matching live trace in Dynatrace.
9. Show current unit-test and golden-evaluation results.

Explain the fictional data, caller-selected role limitation, evaluator limitations, and distinction between successful answering and safe abstention.

## Final Verification Checklist

- [ ] Current unit tests pass.
- [ ] Golden evaluation passes against the deployed backend.
- [ ] RAG case retrieves `rag-quality`.
- [ ] Exact scope refusal uses `refusal-rule`.
- [ ] Viewer response contains no restricted evidence or disclosure.
- [ ] Matching live traces are visible in Dynatrace.
- [ ] Backend, React, and collector are ready.
- [ ] Saved image references match the intended release.
- [ ] Live CronJob is checked if enabled.
- [ ] README commands match the actual deployment.
- [ ] No secrets or sensitive data are staged.
- [ ] Local branch and remote are synchronized.

## Review and Commit Documentation

For a README-only change:

```bash
git diff --check
git add README.md
git --no-pager diff --cached
git commit -m "Update README for React GKE demo"
git push origin main
git status -sb
```

If the remote branch has changed, inspect and integrate both histories before pushing. Do not force-push simply to remove a synchronization warning.
