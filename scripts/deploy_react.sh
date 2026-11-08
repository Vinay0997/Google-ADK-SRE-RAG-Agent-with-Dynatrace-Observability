#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT_ID="${PROJECT_ID:-adk-dynatrace-observability}"
IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/sre-agent-react-ui:react-$(date +%Y%m%d%H%M%S)"
export IMAGE

test -f k8s/react-ui.yaml || {
  echo "Missing k8s/react-ui.yaml"
  exit 1
}

echo "Current Kubernetes context:"
kubectl config current-context
echo "Building React image: $IMAGE"

gcloud builds submit frontend \
  --project="$PROJECT_ID" \
  --tag="$IMAGE"

TMP_MANIFEST=$(mktemp)
trap 'rm -f "$TMP_MANIFEST"' EXIT
export TMP_MANIFEST

python3 - <<'PY'
import os
import re
from pathlib import Path

path = Path("k8s/react-ui.yaml")
text = path.read_text()
updated, count = re.subn(
    r"(?m)^(\s*image:\s*).+$",
    lambda match: match.group(1) + os.environ["IMAGE"],
    text,
)
if count != 1:
    raise SystemExit("Expected exactly one container image in React manifest.")
Path(os.environ["TMP_MANIFEST"]).write_text(updated)
PY

kubectl apply -f "$TMP_MANIFEST"
kubectl -n sre-agent rollout status \
  deployment/sre-agent-react-ui --timeout=180s

cp "$TMP_MANIFEST" k8s/react-ui.yaml

echo "React rollout succeeded; image reference saved."
kubectl -n sre-agent get deployment,service sre-agent-react-ui
