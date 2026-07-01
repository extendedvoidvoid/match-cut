#!/usr/bin/env bash
# Enforces repo good practices. See docs/GOOD_PRACTICES.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

errors=0

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "FAIL: missing required file: $1"
    errors=$((errors + 1))
  fi
}

require_file "AGENTS.md"
require_file "docs/GOOD_PRACTICES.md"
require_file "docs/STRUCTURE.md"
require_file "docs/REQUIREMENTS.md"
require_file ".nvmrc"
require_file ".github/workflows/ci.yml"

# No new fix/plan notes at repo root (archived under docs/history/)
while IFS= read -r -d '' f; do
  echo "FAIL: stray dev note at repo root (move to docs/history/): $f"
  errors=$((errors + 1))
done < <(find . -maxdepth 1 -type f \( -name '*_FIX.md' -o -name '*_FIXES.md' -o -name '*_PLAN.md' -o -name '*_ANALYSIS.md' \) -print0 2>/dev/null)

if [[ ! -x "bin/mc" ]]; then
  echo "FAIL: bin/mc must exist and be executable"
  errors=$((errors + 1))
fi

if [[ "$errors" -gt 0 ]]; then
  echo ""
  echo "$errors practice check(s) failed. See docs/GOOD_PRACTICES.md"
  exit 1
fi

echo "OK: good practices check passed"