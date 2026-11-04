#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
echo "== Pods =="
kubectl -n sre-agent get pods -o wide
echo "== Agent logs (last 20) =="
kubectl -n sre-agent logs deploy/google-adk-sre-agent --tail=20
echo "== Collector logs (last 10) =="
kubectl -n sre-agent logs deploy/otel-collector --tail=10

kubectl -n sre-agent port-forward svc/google-adk-sre-agent 8080:80 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF' EXIT
sleep 3
for Q in "A GKE pod is in CrashLoopBackOff. What should I inspect first?" \
         "What is our company's 2027 Nashville office lease amount?"; do
  curl -s -X POST localhost:8080/ask -H 'Content-Type: application/json' \
    -d "{\"question\": \"$Q\"}" | python3 -m json.tool | head -40
done

sleep 15
echo "== BigQuery: latest executions =="
bq query --use_legacy_sql=false \
  "SELECT timestamp, pod_name, model, input_tokens, output_tokens, estimated_cost_usd, groundedness, hallucination_risk, workflow_success
   FROM \`${PROJECT_ID}.agent_observability.agent_executions\`
   ORDER BY timestamp DESC LIMIT 10"
