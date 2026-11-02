#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
SECRET_NAME="${SECRET_NAME:-dynatrace-api-token}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "Set PROJECT_ID first."
  exit 1
fi

read -r -s -p "Paste Dynatrace Classic access token: " TOKEN
echo
if [[ -z "${TOKEN}" ]]; then
  echo "Token cannot be empty."
  exit 1
fi

if ! gcloud secrets describe "${SECRET_NAME}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud secrets create "${SECRET_NAME}" \
    --replication-policy="automatic" \
    --project "${PROJECT_ID}"
fi

printf '%s' "${TOKEN}" | gcloud secrets versions add "${SECRET_NAME}" \
  --data-file=- \
  --project "${PROJECT_ID}"

echo "Stored token in Secret Manager secret: ${SECRET_NAME}"
