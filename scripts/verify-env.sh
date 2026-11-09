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

# Local AI is optional, so nothing here counts as a failure: a stock container with no runtime and
# no staged model is a correct, supported setup. This reports the state and moves on.
echo "Local AI (optional):"
if python3 -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec("needle") else 1)' 2>/dev/null; then
  version="$(python3 -c 'import importlib.metadata as m; print(m.version("cactus-needle"))' 2>/dev/null || echo installed)"
  printf '  ok       %-12s %s\n' "runtime" "$version"
else
  printf '  absent   %-12s %s\n' "runtime" 'install with: pip install -e ".[dev,ai]"'
fi
for generation in 2 3; do
  engine="$(python3 -c "from app.services.ai import runtime; print(runtime.engine_library_path($generation) or '')" 2>/dev/null)"
  if [ -n "$engine" ]; then
    printf '  ok       %-12s %s\n' "engine v$generation" "$engine"
  else
    printf '  absent   %-12s %s\n' "engine v$generation" "stage with: needle fetch --generation $generation"
  fi
done

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
