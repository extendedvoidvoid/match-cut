#!/usr/bin/env python3
"""READ:SEE ratio gate — take top 1/ratio of ranked READ candidates for SEE.

Input:  assets/film-grab/candidates_read.jsonl (from discover_genre)
Output: assets/film-grab/candidates_see.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "film-grab"


def main() -> int:
    p = argparse.ArgumentParser(description="READ:SEE ratio gate")
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--read-see-ratio", type=float, default=10.0, help="READ:SEE e.g. 10 = see top 10 percent")
    p.add_argument("--samples-per-film", type=int, default=2)
    p.add_argument("--min-see", type=int, default=5, help="Always SEE at least this many films")
    p.add_argument("--max-see", type=int, default=40, help="Cap SEE queue size")
    p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="candidates_read.jsonl path",
    )
    args = p.parse_args()

    out_dir = args.output.expanduser().resolve()
    in_path = (args.input or out_dir / "candidates_read.jsonl").expanduser().resolve()
    if not in_path.is_file():
        print(f"error: run acquire.read_genre first; missing {in_path}", file=sys.stderr)
        return 1

    rows = []
    for line in in_path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))

    n = len(rows)
    if n == 0:
        print(json.dumps({"module": "acquire.ratio_gate", "see_count": 0, "read_count": 0}))
        return 0

    ratio = max(args.read_see_ratio, 1.0)
    k = max(args.min_see, int(math.ceil(n / ratio)))
    k = min(k, args.max_see, n)
    see = rows[:k]

    see_path = out_dir / "candidates_see.jsonl"
    with see_path.open("w") as f:
        for r in see:
            r = dict(r)
            r["see_samples"] = args.samples_per_film
            r["see_status"] = "queued"
            f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")

    summary = {
        "module": "acquire.ratio_gate",
        "read_count": n,
        "read_see_ratio": ratio,
        "see_count": len(see),
        "samples_per_film": args.samples_per_film,
        "top_see": [
            {"slug": r["film_slug"], "score": r.get("read_score"), "genres": r.get("genres")}
            for r in see[:12]
        ],
        "output": str(see_path),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
