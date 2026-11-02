#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:8080}"

curl -s "${BASE_URL}/healthz" | python -m json.tool
curl -s -X POST "${BASE_URL}/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Our Cloud Run API has high latency. How should I troubleshoot it?"}' \
  | python -m json.tool
