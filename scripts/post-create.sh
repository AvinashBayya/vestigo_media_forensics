#!/usr/bin/env bash
# Runs once after the Dev Container is created: system tools, then project dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."

sudo apt-get update
sudo apt-get install -y exiftool tesseract-ocr libtesseract-dev ffmpeg

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

if [ -f web/package-lock.json ]; then
  (cd web && npm ci)
fi

bash scripts/verify-env.sh
