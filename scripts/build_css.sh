#!/usr/bin/env bash
# Build Tailwind CSS for production.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

INPUT="app/static/src/input.css"
OUTPUT="app/static/app.css"

if command -v npx >/dev/null 2>&1; then
  npx --yes tailwindcss@3.4.17 -i "$INPUT" -o "$OUTPUT" --minify
  echo "Built $OUTPUT via npx"
elif [ -x "$ROOT/bin/tailwindcss" ]; then
  "$ROOT/bin/tailwindcss" -i "$INPUT" -o "$OUTPUT" --minify
  echo "Built $OUTPUT via standalone CLI"
else
  echo "Install Node.js (npx) or download tailwindcss standalone to bin/tailwindcss" >&2
  exit 1
fi
