#!/usr/bin/env bash
# Context7 stack audit — parallel queries (M3 Max default: 4 jobs)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export CTX7_TELEMETRY_DISABLED=1

AUDIT_DIR="${1:-docs/audits/latest}"
mkdir -p "$AUDIT_DIR/ctx7"

PARALLEL="${MATCHCUT_CTX7_PARALLEL:-4}"
CTX7="npx -y ctx7"

if [[ -n "${CONTEXT7_API_KEY:-}" ]]; then
  export CONTEXT7_API_KEY
fi

query() {
  local id="$1"
  local lib="$2"
  local q="$3"
  local out="$AUDIT_DIR/ctx7/${id}.log"
  echo "[$id] $lib — starting" >&2
  if $CTX7 docs "$lib" "$q" >"$out" 2>&1; then
    echo "[$id] PASS" >&2
    echo "pass" >"$AUDIT_DIR/ctx7/${id}.status"
  else
    echo "[$id] FAIL (see $out)" >&2
    echo "fail" >"$AUDIT_DIR/ctx7/${id}.status"
  fi
}

# Resolve MediaPipe library ID once
MP_LIB="$AUDIT_DIR/ctx7/mediapipe-libid.txt"
if [[ ! -f "$MP_LIB" ]]; then
  $CTX7 library "mediapipe tasks vision" "face landmarker browser" 2>/dev/null | head -20 >"$MP_LIB" || true
fi
MP_ID="/google/mediapipe"
if grep -qE '^/[a-z0-9_-]+/[a-z0-9_.-]+' "$MP_LIB" 2>/dev/null; then
  MP_ID="$(grep -oE '^/[a-z0-9_-]+/[a-z0-9_.-]+' "$MP_LIB" | head -1)"
fi

query "next-webpack" "/vercel/next.js" "webpack asyncWebAssembly experiments config Next.js 14" &
query "react-hooks" "/facebook/react" "useCallback useEffect exhaustive deps performance" &
query "tailwind" "/tailwindlabs/tailwindcss" "tailwind config content paths Next.js app directory" &
query "mediapipe" "$MP_ID" "Face Landmarker browser JavaScript detect eyes" &

# Cap parallel jobs
while (( $(jobs -r | wc -l | tr -d ' ') >= PARALLEL )); do
  sleep 0.2
done
wait

failures=0
for f in "$AUDIT_DIR/ctx7"/*.status; do
  [[ -f "$f" ]] || continue
  if [[ "$(cat "$f")" == "fail" ]]; then
    failures=$((failures + 1))
  fi
done

if [[ "$failures" -gt 0 ]]; then
  echo "Context7 audit: $failures query(s) failed" >&2
  exit 1
fi

echo "Context7 audit: all queries passed" >&2