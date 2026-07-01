#!/usr/bin/env bash
# Match-cut ecosystem hygiene — manifest, QC artifacts, optional caches.
# Safe by default: never deletes film-grab images without --purge-assets.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PURGE_ASSETS=false
PRUNE_QC=false
RETRY_FAILED=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge-assets) PURGE_ASSETS=true ;;
    --prune-qc) PRUNE_QC=true ;;
    --retry-failed) RETRY_FAILED=true ;;
    -h|--help)
      echo "Usage: scripts/ecosystem-cleanup.sh [--prune-qc] [--retry-failed] [--purge-assets]"
      exit 0
      ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
  shift
done

if [[ -f "$ROOT/.env.local" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env.local"
  set +a
fi

VENV_PY="$ROOT/.venv-film-grab/bin/python"
PY="${VENV_PY}"
[[ -x "$PY" ]] || PY="${MATCHCUT_PYTHON:-python3}"

echo "== film-grab pipeline =="
if [[ -x "$VENV_PY" || -f "$ROOT/scripts/fetch-film-grab/fetch.py" ]]; then
  if $RETRY_FAILED; then
    "$PY" "$ROOT/scripts/fetch-film-grab/fetch.py" cleanup --retry
  else
    "$PY" "$ROOT/scripts/fetch-film-grab/fetch.py" cleanup
  fi
  "$PY" "$ROOT/scripts/fetch-film-grab/fetch.py" health || true
else
  echo "skip: fetch.py / venv missing"
fi

if $PURGE_ASSETS; then
  echo "== purge assets/film-grab =="
  rm -rf "$ROOT/assets/film-grab"
  echo "purged"
fi

if $PRUNE_QC; then
  echo "== prune old QC audits (keep latest + last 7 days) =="
  find "$ROOT/docs/audits" -mindepth 1 -maxdepth 1 -type d ! -name latest -mtime +7 -exec rm -rf {} + 2>/dev/null || true
fi

echo "== context7 key =="
if [[ -n "${CONTEXT7_API_KEY:-}" ]]; then
  echo "CONTEXT7_API_KEY: set (local)"
else
  echo "CONTEXT7_API_KEY: not set — use .env.local or ctx7 login"
fi

echo "== done =="