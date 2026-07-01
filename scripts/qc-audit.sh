#!/usr/bin/env bash
# Full QC audit — Option B. Parallel on M3 Max (default 8 jobs).
# Usage: scripts/qc-audit.sh [--deep]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DEEP=false
[[ "${1:-}" == "--deep" ]] && DEEP=true

DATE="$(date +%Y-%m-%d)"
AUDIT_DIR="docs/audits/${DATE}"
LATEST="docs/audits/latest"
PARALLEL="${MATCHCUT_PARALLEL_JOBS:-8}"

mkdir -p "$AUDIT_DIR" "$LATEST"
rm -rf "$LATEST" && mkdir -p "$LATEST"

export CTX7_TELEMETRY_DISABLED=1
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=8192}"

echo "QC audit — hardware profile: ${MATCHCUT_HARDWARE_PROFILE:-m3-max-48gb}"
echo "Parallel jobs: $PARALLEL"
echo "Output: $AUDIT_DIR"
echo ""

run_job() {
  local name="$1"
  shift
  local log="$AUDIT_DIR/${name}.log"
  local status="$AUDIT_DIR/${name}.status"
  echo "[$name] start"
  if "$@" >"$log" 2>&1; then
    echo "pass" >"$status"
    echo "[$name] PASS"
  else
    echo "fail" >"$status"
    echo "[$name] FAIL"
  fi
}

# --- Parallel batch 1 (independent) ---
run_job "practices" npm run check:practices &
run_job "lint" npm run lint &
(
  if npm audit --audit-level=high >"$AUDIT_DIR/npm-audit.log" 2>&1; then
    echo "pass" >"$AUDIT_DIR/npm-audit.status"
  else
    echo "warn" >"$AUDIT_DIR/npm-audit.status"
  fi
  echo "[npm-audit] done"
) &
( npm outdated >"$AUDIT_DIR/outdated.log" 2>&1 || true; echo "pass" >"$AUDIT_DIR/outdated.status"; echo "[outdated] logged (informational)" ) &
run_job "context7" bash scripts/qc-context7.sh "$AUDIT_DIR" &

wait

# --- Sequential (depends on install) ---
run_job "build" npm run build

if $DEEP; then
  run_job "tsc" npx tsc --noEmit
fi

# Symlink latest
cp -R "$AUDIT_DIR/"* "$LATEST/" 2>/dev/null || true

# Report
REPORT="$AUDIT_DIR/qc-report.md"
{
  echo "# QC Report — $DATE"
  echo ""
  echo "Hardware: ${MATCHCUT_HARDWARE_PROFILE:-m3-max-48gb}"
  echo "Deep: $DEEP"
  echo ""
  echo "| Check | Status |"
  echo "|-------|--------|"
  for s in "$AUDIT_DIR"/*.status; do
    [[ -f "$s" ]] || continue
    name="$(basename "$s" .status)"
    st="$(cat "$s")"
    echo "| $name | $st |"
  done
  echo ""
  echo "Logs: \`docs/audits/${DATE}/\`"
} >"$REPORT"

cp "$REPORT" "$LATEST/qc-report.md"

failures=0
for s in "$AUDIT_DIR"/*.status; do
  [[ -f "$s" ]] || continue
  st="$(cat "$s")"
  [[ "$st" == "fail" ]] && failures=$((failures + 1))
  [[ "$st" == "warn" ]] && echo "WARN: $(basename "$s" .status) (non-blocking)"
done

echo ""
echo "Report: $REPORT"

if [[ "$failures" -gt 0 ]]; then
  echo "QC FAILED: $failures blocking check(s)"
  exit 1
fi

echo "QC PASSED"