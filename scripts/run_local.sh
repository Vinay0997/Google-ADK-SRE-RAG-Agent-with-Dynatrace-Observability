#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Edit GOOGLE_CLOUD_PROJECT before testing."
fi

uvicorn main:api --host 0.0.0.0 --port 8080 --reload
