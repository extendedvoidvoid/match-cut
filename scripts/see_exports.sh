#!/usr/bin/env bash
# Flat SEE trays at project root — lanes must not mix by default.
# Usage:
#   mc see              → essay lane only (default)
#   mc see vj           → VJ reels only
#   mc see all          → everything (debug)
#   mc see list|refresh [essay|vj|all]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXPORTS="$ROOT/exports"
ACTION="open"
LANE="essay"

usage() {
  echo "Usage: see_exports.sh [open|list|refresh] [essay|vj|all]"
  echo "  essay (default)  vertical reframe + site demos — album essay / Station F"
  echo "  vj               ~1min reels / VJ experiments only"
  echo "  all              both (noisy — not default)"
  exit 2
}

for arg in "$@"; do
  case "$arg" in
    open|list|refresh) ACTION="$arg" ;;
    essay|vj|all) LANE="$arg" ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

link_one() {
  local src="$1" dest="$2"
  [[ -f "$src" ]] || return 0
  ln -sfn "$src" "$dest"
}

fill_essay() {
  local dir="$1"
  mkdir -p "$dir"
  find "$dir" -maxdepth 1 -type l -delete 2>/dev/null || true

  if [[ -d "$EXPORTS/vertical_ready" ]]; then
    for f in "$EXPORTS/vertical_ready"/*.{mp4,mov,MP4,MOV}; do
      [[ -e "$f" ]] || continue
      link_one "$f" "$dir/vertical__$(basename "$f")"
    done
  fi
  if [[ -d "$EXPORTS/vertical_test_A" ]]; then
    for f in "$EXPORTS/vertical_test_A"/*_vertical.mp4; do
      [[ -e "$f" ]] || continue
      base="$(basename "$f")"
      [[ -e "$dir/vertical__${base}" ]] && continue
      link_one "$f" "$dir/vertical__${base}"
    done
  fi
  if [[ -f "$ROOT/public/effect demo.mp4" ]]; then
    link_one "$ROOT/public/effect demo.mp4" "$dir/site__effect-demo-landscape.mp4"
  fi
  if [[ -f "$ROOT/public/effect-demo-vertical.mp4" ]]; then
    link_one "$ROOT/public/effect-demo-vertical.mp4" "$dir/site__effect-demo-vertical.mp4"
  fi

  cat > "$dir/README.txt" << EOF
SEE/essay — ALBUM ESSAY / vertical reframe / Station F path
==========================================================
NOT VJ reels. Chanel/show landscape → 9:16 belongs here later.

  mc see          (or mc see essay)
  mc see vj       VJ one-minute montages only
  mc see all      both (only if you mean to mix)

See docs/history/LANES.md
Updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
}

fill_vj() {
  local dir="$1"
  mkdir -p "$dir"
  find "$dir" -maxdepth 1 -type l -delete 2>/dev/null || true

  if [[ -d "$EXPORTS/reels" ]]; then
    for f in "$EXPORTS/reels"/*.mp4; do
      [[ -e "$f" ]] || continue
      link_one "$f" "$dir/reel__$(basename "$f")"
    done
  fi
  if [[ -d "$EXPORTS/reference" ]]; then
    for f in "$EXPORTS/reference"/*.{mp4,mov,MP4,MOV}; do
      [[ -e "$f" ]] || continue
      link_one "$f" "$dir/ref__$(basename "$f")"
    done
  fi

  cat > "$dir/README.txt" << EOF
SEE/vj — VJ / ~1 minute montages (experimentation)
==================================================
NOT Station F spine. NOT album cover essay.
Other Grok instance may own this lane — do not merge into essay by default.

  mc see vj
  mc see essay    Station F / vertical / essay lane

See docs/history/LANES.md
Updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
}

# root SEE/ = essay default tray (no reels)
# SEE/vj = VJ only
# SEE/all = flat dump if requested

case "$LANE" in
  essay)
    fill_essay "$ROOT/SEE"
    TARGET="$ROOT/SEE"
    ;;
  vj)
    fill_vj "$ROOT/SEE/vj"
    TARGET="$ROOT/SEE/vj"
    ;;
  all)
    fill_essay "$ROOT/SEE"
    fill_vj "$ROOT/SEE/vj"
    # also flat all under SEE/all for one window
    ALL="$ROOT/SEE/all"
    mkdir -p "$ALL"
    find "$ALL" -maxdepth 1 -type l -delete 2>/dev/null || true
    for f in "$ROOT/SEE"/vertical__* "$ROOT/SEE"/site__* "$ROOT/SEE/vj"/reel__* "$ROOT/SEE/vj"/ref__*; do
      [[ -e "$f" ]] || continue
      ln -sfn "$(readlink "$f" 2>/dev/null || echo "$f")" "$ALL/$(basename "$f")"
    done
    cat > "$ALL/README.txt" << EOF
SEE/all — BOTH lanes (debug only)
Do not treat as one product. See LANES.md
Updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
    TARGET="$ALL"
    ;;
esac

count="$(find "$TARGET" -maxdepth 1 -type l 2>/dev/null | wc -l | tr -d ' ')"
echo "SEE lane=$LANE links=$count → $TARGET"

case "$ACTION" in
  refresh|list)
    ls -la "$TARGET" | head -60
    ;;
  open)
    open "$TARGET"
    ;;
  *)
    usage
    ;;
esac
