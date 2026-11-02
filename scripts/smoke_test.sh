#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:8501}"

curl --fail --silent --show-error "${BASE_URL}/_stcore/health" | python -m json.tool
