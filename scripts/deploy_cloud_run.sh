#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-google-adk-sre-agent}"
SA_NAME="${SA_NAME:-adk-observability-sa}"
MODEL_NAME="${MODEL_NAME:-gemini-2.5-flash}"
DT_OTLP_ENDPOINT="${DT_OTLP_ENDPOINT:-}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "Set PROJECT_ID first."
  exit 1
fi
if [[ -z "${DT_OTLP_ENDPOINT}" ]]; then
  echo "Set DT_OTLP_ENDPOINT, for example:"
  echo "export DT_OTLP_ENDPOINT=https://abc12345.live.dynatrace.com/api/v2/otlp"
  exit 1
fi

gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --service-account "${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --memory 1Gi \
  --cpu 1 \
  --timeout 120 \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},MODEL_NAME=${MODEL_NAME},EVALUATOR_MODEL=${MODEL_NAME},APP_NAME=sre_rag_observability,OTEL_SERVICE_NAME=${SERVICE_NAME},DEPLOYMENT_ENVIRONMENT=cloud-run,DYNATRACE_OTLP_ENDPOINT=${DT_OTLP_ENDPOINT},USE_LLM_EVALUATOR=true" \
  --set-secrets "DYNATRACE_API_TOKEN=dynatrace-api-token:latest"

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --format='value(status.url)')

echo
echo "Deployed: ${SERVICE_URL}"
echo "Swagger: ${SERVICE_URL}/docs"
echo "Test:"
echo "curl -s -X POST ${SERVICE_URL}/ask -H 'Content-Type: application/json' -d '{\"question\":\"Our Cloud Run service started returning 5xx after deployment. What should I check?\"}' | python -m json.tool"
