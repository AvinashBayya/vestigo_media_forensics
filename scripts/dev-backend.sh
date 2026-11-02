#!/usr/bin/env bash
# Starts the FastAPI backend on port 8400 with auto-reload.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8400
