#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
CLUSTER="${CLUSTER:-sre-agent-cluster}"
REPOSITORY="${REPOSITORY:-sre-agent}"
BQ_LOCATION="${BQ_LOCATION:-US}"
GSA="adk-agent"
GSA_EMAIL="${GSA}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable container.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com aiplatform.googleapis.com bigquery.googleapis.com

gcloud artifacts repositories create "$REPOSITORY" --repository-format=docker \
  --location="$REGION" || echo "repository exists"
gcloud container clusters create-auto "$CLUSTER" --region "$REGION" || echo "cluster exists"

gcloud iam service-accounts create "$GSA" --display-name "ADK agent" || echo "GSA exists"
for ROLE in roles/aiplatform.user roles/bigquery.dataEditor roles/bigquery.jobUser roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${GSA_EMAIL}" --role "$ROLE" --condition=None >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$GSA_EMAIL" \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:${PROJECT_ID}.svc.id.goog[sre-agent/adk-observability-ksa]"

bq --location="$BQ_LOCATION" mk --dataset "${PROJECT_ID}:agent_observability" || echo "dataset exists"
bq mk --table "${PROJECT_ID}:agent_observability.agent_executions" \
  bigquery/agent_executions_schema.json || echo "table exists"
echo "GCP setup complete."
