#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
: "${DT_API_TOKEN:?Set DT_API_TOKEN (Dynatrace token)}"
: "${DT_OTLP_ENDPOINT:?Set DT_OTLP_ENDPOINT, e.g. https://ENV.live.dynatrace.com/api/v2/otlp}"
export PROJECT_ID DT_OTLP_ENDPOINT
export REGION="${REGION:-us-central1}"
export REPOSITORY="${REPOSITORY:-sre-agent}"
CLUSTER="${CLUSTER:-sre-agent-cluster}"
BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}"

gcloud builds submit --tag "${BASE}/google-adk-sre-agent:latest" .
gcloud builds submit ui --tag "${BASE}/sre-agent-ui:latest"

gcloud container clusters get-credentials "$CLUSTER" --region "$REGION" --project "$PROJECT_ID"
kubectl apply -f k8s/namespace.yaml
kubectl -n sre-agent create secret generic dynatrace-api-token \
  --from-literal=token="$DT_API_TOKEN" --dry-run=client -o yaml | kubectl apply -f -

VARS='${PROJECT_ID} ${REGION} ${REPOSITORY} ${DT_OTLP_ENDPOINT}'
for f in serviceaccount configmap otel-collector deployment service hpa ui eval-cronjob; do
  envsubst "$VARS" < "k8s/${f}.yaml" | kubectl apply -f -
done

kubectl -n sre-agent rollout status deploy/otel-collector --timeout=180s
kubectl -n sre-agent rollout status deploy/google-adk-sre-agent --timeout=300s
kubectl -n sre-agent rollout status deploy/sre-agent-ui --timeout=180s
echo "UI external IP (may take a minute):"
kubectl -n sre-agent get svc sre-agent-ui
