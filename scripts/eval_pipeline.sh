#!/usr/bin/env bash
# Automated evaluation pipeline for the SRE agent demo.
#
# 1. Waits for the backend to be reachable and healthy.
# 2. Runs the golden evaluation with LLM-judge verification enabled.
# 3. Saves a JSON report and a full log under the artifacts directory.
# 4. Propagates the evaluation exit code.
#
# Requires an existing backend or port-forward. Live calls may trigger
# model invocations and telemetry charges; do not enable the evaluation
# CronJob solely to run this script.
set -euo pipefail

AGENT_URL="${AGENT_URL:-http://127.0.0.1:8085}"
REPORT_DIR="${REPORT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/artifacts}"
REQUIRE_LLM_JUDGE="${REQUIRE_LLM_JUDGE:-true}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"

mkdir -p "$REPORT_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$REPORT_DIR/golden-run-$TS.log"
REPORT_FILE="$REPORT_DIR/golden-report-$TS.json"

echo "== 1/2 Preflight: waiting for $AGENT_URL/healthz (max ${HEALTH_TIMEOUT}s) =="
READY=0
DEADLINE=$((SECONDS + HEALTH_TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
  if curl -fsS "$AGENT_URL/healthz" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [ "$READY" != "1" ]; then
  echo "ERROR backend not healthy at $AGENT_URL" | tee -a "$LOG_FILE"
  exit 1
fi
echo "Backend is healthy."

echo "== 2/2 Golden evaluation (REQUIRE_LLM_JUDGE=$REQUIRE_LLM_JUDGE) =="
cd "$(dirname "${BASH_SOURCE[0]}")/.."
AGENT_URL="$AGENT_URL" \
REQUIRE_LLM_JUDGE="$REQUIRE_LLM_JUDGE" \
EVAL_REPORT="$REPORT_FILE" \
  python3 -u -m evals.run_golden 2>&1 | tee "$LOG_FILE"
PIPELINE_EXIT=$?

echo "Log:    $LOG_FILE"
echo "Report: $REPORT_FILE"
exit $PIPELINE_EXIT
