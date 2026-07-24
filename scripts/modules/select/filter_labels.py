#!/usr/bin/env python3
"""Select module: filter classifications by label; optional sort; write pool jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CLS = ROOT / "assets" / "film-grab" / "classifications.jsonl"
DEFAULT_OUT = ROOT / "assets" / "film-grab" / "pools"


def main() -> int:
    p = argparse.ArgumentParser(description="Filter/sort classification labels → pool jsonl")
    p.add_argument("--classifications", type=Path, default=DEFAULT_CLS)
    p.add_argument("--label", default="kiss_geo", help="Boolean label required true")
    p.add_argument("--sort", default=None, help="Numeric label key to sort by (asc)")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    cls_path = args.classifications.expanduser().resolve()
    if not cls_path.is_file():
        print(f"error: missing {cls_path}", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for line in cls_path.read_text().splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        labs = o.get("labels") or {}
        if not labs.get(args.label):
            continue
        rows.append(o)

    if args.sort:
        def key_fn(r: dict) -> float:
            v = (r.get("labels") or {}).get(args.sort)
            if v is None:
                return 1e18
            return float(v)

        rows.sort(key=key_fn)

    if args.limit > 0:
        rows = rows[: args.limit]

    out = args.out
    if out is None:
        DEFAULT_OUT.mkdir(parents=True, exist_ok=True)
        out = DEFAULT_OUT / f"pool_{args.label}.jsonl"
    else:
        out = out.expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")

    summary = {
        "module": "select.filter_labels",
        "label": args.label,
        "sort": args.sort,
        "count": len(rows),
        "output": str(out),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
