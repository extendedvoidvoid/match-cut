#!/usr/bin/env bash
# LM Studio terminal control — M3 Max tuned for Qwen2.5-VL poster QC
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$ROOT/.env"

# Defaults (override in .env)
LM_PORT="${LM_STUDIO_PORT:-32768}"
LM_HOST="${LM_STUDIO_HOST:-127.0.0.1}"
LM_MODEL_KEY="${LM_STUDIO_MODEL_KEY:-qwen2.5-vl-7b-instruct}"
LM_IDENTIFIER="${LM_STUDIO_MODEL_ID:-qwen_qwen2.5-vl-7b-instruct}"
LM_CONTEXT="${LM_STUDIO_CONTEXT:-4096}"
LM_PARALLEL="${LM_STUDIO_PARALLEL:-1}"
LM_GPU="${LM_STUDIO_GPU:-max}"
LM_BASE_URL="http://${LM_HOST}:${LM_PORT}/v1"

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a; source <(grep -E '^LM_STUDIO_|^LOCAL_' "$ENV_FILE" 2>/dev/null | sed 's/^/export /') 2>/dev/null || true
    set +a
    LM_PORT="${LM_STUDIO_PORT:-$LM_PORT}"
    LM_HOST="${LM_STUDIO_HOST:-$LM_HOST}"
    LM_MODEL_KEY="${LM_STUDIO_MODEL_KEY:-$LM_MODEL_KEY}"
    LM_IDENTIFIER="${LM_STUDIO_MODEL_ID:-$LM_IDENTIFIER}"
    LM_CONTEXT="${LM_STUDIO_CONTEXT:-$LM_CONTEXT}"
    LM_PARALLEL="${LM_STUDIO_PARALLEL:-$LM_PARALLEL}"
    LM_GPU="${LM_STUDIO_GPU:-$LM_GPU}"
    LM_BASE_URL="${LM_STUDIO_BASE_URL:-http://${LM_HOST}:${LM_PORT}/v1}"
  fi
}

cmd_status() {
  load_env
  echo "== LM Studio server =="
  lms server status 2>/dev/null || true
  echo ""
  echo "== Loaded models =="
  lms ps 2>/dev/null || true
  echo ""
  echo "== API =="
  echo "base_url=$LM_BASE_URL"
  curl -sf "${LM_BASE_URL}/models" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for m in d.get('data',[]):
    print(' ', m.get('id'))
" 2>/dev/null || echo "  (API not reachable)"
}

cmd_load_vision() {
  load_env
  echo "Loading $LM_MODEL_KEY → $LM_IDENTIFIER"
  echo "  gpu=$LM_GPU context=$LM_CONTEXT parallel=$LM_PARALLEL"
  lms unload "$LM_IDENTIFIER" 2>/dev/null || lms unload -a 2>/dev/null || true
  lms load "$LM_MODEL_KEY" \
    --gpu "$LM_GPU" \
    --context-length "$LM_CONTEXT" \
    --parallel "$LM_PARALLEL" \
    --identifier "$LM_IDENTIFIER" \
    -y
  lms ps
}

cmd_unload() {
  load_env
  lms unload "$LM_IDENTIFIER" 2>/dev/null || lms unload -a
}

cmd_server_start() {
  load_env
  lms server start --port "$LM_PORT" --bind "$LM_HOST"
  lms server status
}

cmd_test() {
  load_env
  PY="${MATCHCUT_PYTHON:-python3}"
  exec "$PY" "$ROOT/scripts/lmstudio/poster_qc.py" --base-url "$LM_BASE_URL" --model "$LM_IDENTIFIER" "$@"
}

cmd_benchmark() {
  load_env
  PY="${MATCHCUT_PYTHON:-python3}"
  exec "$PY" "$ROOT/scripts/lmstudio/benchmark_vision.py" \
    --base-url "$LM_BASE_URL" --model "$LM_IDENTIFIER" "$@"
}

cmd_scene_empty() {
  load_env
  PY="${MATCHCUT_PYTHON:-python3}"
  exec "$PY" "$ROOT/scripts/lmstudio/scene_empty.py" \
    --base-url "$LM_BASE_URL" --model "$LM_IDENTIFIER" "$@"
}

cmd_env_write() {
  load_env
  mkdir -p "$(dirname "$ENV_FILE")"
  touch "$ENV_FILE"
  for kv in \
    "LM_STUDIO_PORT=$LM_PORT" \
    "LM_STUDIO_HOST=$LM_HOST" \
    "LM_STUDIO_BASE_URL=$LM_BASE_URL" \
    "LM_STUDIO_MODEL_KEY=$LM_MODEL_KEY" \
    "LM_STUDIO_MODEL_ID=$LM_IDENTIFIER" \
    "LM_STUDIO_CONTEXT=$LM_CONTEXT" \
    "LM_STUDIO_PARALLEL=$LM_PARALLEL" \
    "LM_STUDIO_GPU=$LM_GPU" \
    "LM_STUDIO_TEMPERATURE=0.1" \
    "LLM_PROVIDER=local"; do
    key="${kv%%=*}"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      sed -i '' "s|^${key}=.*|${kv}|" "$ENV_FILE"
    else
      echo "$kv" >> "$ENV_FILE"
    fi
  done
  echo "wrote LM Studio vars → $ENV_FILE"
}

usage() {
  cat <<EOF
mc lmstudio — LM Studio control (Qwen2.5-VL poster QC)

  status          server + loaded models + API check
  load-vision     reload Qwen VL (gpu=max context=4096 parallel=1)
  unload          unload vision model
  server-start    start API server on port \$LM_STUDIO_PORT (default 32768)
  env-write       sync optimal defaults into match-cut/.env
  test [image]    run typography QC on one poster (or sample)
  scene-empty     Qwen nature|city|interior on n_faces==0 stills
  qc-batch        QC all by-slug posters → assets/movie-posters/qc.jsonl
  benchmark       time N images (default 100) → qwen_benchmark.jsonl + summary

Tunable via match-cut/.env:
  LM_STUDIO_PORT LM_STUDIO_HOST LM_STUDIO_CONTEXT LM_STUDIO_PARALLEL LM_STUDIO_GPU
EOF
}

main() {
  local cmd="${1:-status}"
  shift || true
  case "$cmd" in
    status) cmd_status ;;
    load-vision|load) cmd_load_vision ;;
    unload) cmd_unload ;;
    server-start) cmd_server_start ;;
    env-write) cmd_env_write ;;
    test) cmd_test "$@" ;;
    scene-empty) cmd_scene_empty "$@" ;;
    qc-batch) cmd_test --batch "$@" ;;
    benchmark)
      local n=100 src=bulk
      shift || true
      [[ "${1:-}" =~ ^[0-9]+$ ]] && { n="$1"; shift; }
      [[ -n "${1:-}" ]] && src="$1"
      cmd_benchmark -n "$n" --source "$src"
      ;;
    -h|--help|help) usage ;;
    *) echo "unknown: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"