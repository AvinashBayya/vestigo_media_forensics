#!/usr/bin/env bash
# Checks that the Dev Container has every tool Vestigo needs.
# Usage: scripts/verify-env.sh [--servers]
#   --servers  also check that the backend (8400) and frontend (5180) are answering
set -uo pipefail

failures=0

check() {
  local label="$1"; shift
  local output
  if output="$("$@" 2>&1)" && [ -n "$output" ]; then
    printf '  ok       %-12s %s\n' "$label" "${output%%$'\n'*}"
  else
    printf '  MISSING  %-12s\n' "$label"
    failures=$((failures + 1))
  fi
}

echo "Tools:"
check python    python3 -c 'import sys; assert sys.version_info[:2] == (3, 11), sys.version; print(sys.version.split()[0])'
check node      node --version
check npm       npm --version
check exiftool  exiftool -ver
check tesseract tesseract --version
check ffmpeg    ffmpeg -version
check ffprobe   ffprobe -version

if tesseract --list-langs 2>/dev/null | grep -qx eng; then
  printf '  ok       %-12s %s\n' "ocr-lang" "eng"
else
  printf '  MISSING  %-12s %s\n' "ocr-lang" "eng"
  failures=$((failures + 1))
fi

if [ "${1:-}" = "--servers" ]; then
  echo "Servers:"
  check backend  curl -fsS http://localhost:8400/api/v1/health
  check frontend curl -fsS -o /dev/null -w '%{http_code}' http://localhost:5180/
fi

if [ "$failures" -gt 0 ]; then
  echo "$failures check(s) failed."
  exit 1
fi
echo "All checks passed."
