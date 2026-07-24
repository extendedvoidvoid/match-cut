#!/usr/bin/env python3
"""Benchmark Qwen VL poster QC — per-image timestamps + 100-image totals."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BULK = ROOT / "assets" / "movie-posters" / "bulk"
SLUG = ROOT / "assets" / "movie-posters" / "by-slug"
DEFAULT_OUT = ROOT / "assets" / "movie-posters" / "qwen_benchmark.jsonl"

sys.path.insert(0, str(ROOT / "scripts" / "lmstudio"))
from poster_qc import qc_poster  # noqa: E402


def pick_images(n: int, source: str) -> list[Path]:
    if source == "slug":
        pool = sorted(SLUG.glob("*.jpg"))
    elif source == "bulk":
        pool = sorted(BULK.glob("*.jpg"))
    else:
        pool = sorted(set(SLUG.glob("*.jpg")) | set(BULK.glob("*.jpg")))
    return pool[:n]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Qwen vision latency")
    parser.add_argument("-n", "--count", type=int, default=100)
    parser.add_argument("--source", choices=("all", "bulk", "slug"), default="bulk")
    parser.add_argument("--base-url", default=os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:32768/v1"))
    parser.add_argument("--model", default=os.environ.get("LM_STUDIO_MODEL_ID", "qwen_qwen2.5-vl-7b-instruct"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    images = pick_images(args.count, args.source)
    if len(images) < args.count:
        print(f"warn: only {len(images)} images available (wanted {args.count})", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("")
    run_start = time.perf_counter()
    run_iso = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []

    for i, path in enumerate(images):
        t0 = time.perf_counter()
        ts = datetime.now(timezone.utc).isoformat()
        try:
            result = qc_poster(
                path, base_url=args.base_url, model=args.model, temperature=0.1,
            )
            err = None
        except Exception as exc:
            result = {}
            err = str(exc)
        elapsed = time.perf_counter() - t0
        row = {
            "index": i,
            "timestamp_utc": ts,
            "duration_sec": round(elapsed, 3),
            "path": str(path),
            "name": path.name,
            "verdict": result.get("verdict"),
            "has_typography": result.get("has_typography"),
            "error": err,
        }
        rows.append(row)
        with args.output.open("a") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
        print(
            f"[{i+1:03d}/{len(images)}] {elapsed:6.2f}s  {path.name[:40]:40s}  "
            f"{result.get('verdict', 'ERR')}",
            file=sys.stderr,
        )
        if err:
            print(f"  error: {err}", file=sys.stderr)
            break

    total = time.perf_counter() - run_start
    ok = [r for r in rows if not r.get("error")]
    durations = [r["duration_sec"] for r in ok]
    summary = {
        "run_started_utc": run_iso,
        "run_finished_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "base_url": args.base_url,
        "requested": args.count,
        "completed": len(rows),
        "successful": len(ok),
        "total_wall_sec": round(total, 2),
        "avg_sec_per_image": round(sum(durations) / len(durations), 2) if durations else None,
        "min_sec": round(min(durations), 2) if durations else None,
        "max_sec": round(max(durations), 2) if durations else None,
        "images_per_hour": round(len(ok) / total * 3600, 1) if total > 0 and ok else None,
        "output": str(args.output),
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())