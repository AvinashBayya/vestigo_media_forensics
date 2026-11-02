#!/usr/bin/env bash
# Starts the Vite dev server on port 5180. API calls are proxied to the backend on 8400.
set -euo pipefail
cd "$(dirname "$0")/../web"
exec npm run dev
