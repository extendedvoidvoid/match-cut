#!/usr/bin/env python3
"""Build structural units: 1 kiss : 2 empty establishing (no people).

unit = [empty, empty, kiss]  (default order)
kiss sorted far→close (not closeup first, then by eye_dist asc)
empty = n_faces==0; optional nature+city pair from scene_type (Qwen)

Prints gap math vs duration/rate targets; writes units jsonl + gap report.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CLS = ROOT / "assets" / "film-grab" / "classifications.jsonl"
DEFAULT_OUT = ROOT / "assets" / "film-grab" / "pools"
DEFAULT_NUMBERS = ROOT / "assets" / "film-grab" / "scene_empty_numbers.json"


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def kiss_far_key(r: dict) -> tuple:
    """Far-from-lens first: not closeup, then smaller eye_dist, then smaller mouth_dist_norm."""
    labs = r.get("labels") or {}
    close = 1 if labs.get("closeup") else 0
    eye = labs.get("eye_dist")
    eye_v = float(eye) if eye is not None else 1e9
    mouth = labs.get("mouth_dist_norm")
    mouth_v = float(mouth) if mouth is not None else 1e9
    return (close, eye_v, mouth_v)


def scene_of(r: dict) -> str:
    return str((r.get("labels") or {}).get("scene_type") or "unlabeled")


def pick_empty_pair(
    by_scene: dict[str, list[dict]],
    idx: dict[str, int],
    mode: str,
) -> tuple[dict, dict, str] | None:
    """Return (e1, e2, pair_tag) or None if cannot form pair."""

    def take(scene: str) -> dict | None:
        bucket = by_scene.get(scene) or []
        i = idx.get(scene, 0)
        if i >= len(bucket):
            return None
        idx[scene] = i + 1
        return bucket[i]

    if mode == "nature_city":
        # prefer one nature + one city (establishing contrast)
        n = take("nature")
        c = take("city")
        if n and c:
            return n, c, "nature+city"
        # fall back: two nature, two city, then any labeled, then unlabeled
        for a, b, tag in (
            ("nature", "nature", "nature+nature"),
            ("city", "city", "city+city"),
            ("interior", "interior", "interior+interior"),
            ("other", "other", "other+other"),
            ("unlabeled", "unlabeled", "unlabeled+unlabeled"),
        ):
            if a == "nature" and n and not c:
                # already took nature; pair with anything
                for s in ("interior", "other", "unlabeled", "nature"):
                    x = take(s)
                    if x:
                        return n, x, f"nature+{s}"
                return None
            if a == "city" and c and not n:
                for s in ("interior", "other", "unlabeled", "city"):
                    x = take(s)
                    if x:
                        return c, x, f"city+{s}"
                return None
            e1, e2 = take(a), take(b)
            if e1 and e2:
                return e1, e2, tag
        return None

    if mode == "any":
        e1, e2 = take("unlabeled"), take("unlabeled")
        # merge all into stream via unlabeled first filled below by caller
        return (e1, e2, "any") if e1 and e2 else None

    # nature_only / city_only
    s = "nature" if mode == "nature_only" else "city"
    e1, e2 = take(s), take(s)
    if e1 and e2:
        return e1, e2, f"{s}+{s}"
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="1 kiss : 2 empty unit builder + gap report")
    p.add_argument("--classifications", type=Path, default=DEFAULT_CLS)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument(
        "--order",
        choices=("eek", "eke", "kee"),
        default="eek",
        help="eek=empty,empty,kiss | eke=empty,kiss,empty | kee=kiss,empty,empty",
    )
    p.add_argument(
        "--empty-pair",
        choices=("nature_city", "nature_only", "city_only", "any"),
        default="nature_city",
        help="How to pick the two establishing empties (needs scene_type from Qwen)",
    )
    p.add_argument("--duration", type=float, default=60.0, help="Target seconds for gap math")
    p.add_argument("--start-rate", type=float, default=1.0)
    p.add_argument("--end-rate", type=float, default=30.0)
    p.add_argument("--flat-rate", type=float, default=0.0, help="If >0, use constant rate for gap math")
    p.add_argument("--allow-reuse", action="store_true", help="Note reuse if units short of slots")
    args = p.parse_args()

    cls_path = args.classifications.expanduser().resolve()
    if not cls_path.is_file():
        print(f"error: missing {cls_path}", file=sys.stderr)
        return 1

    rows = load_rows(cls_path)
    empties: list[dict] = []
    kisses: list[dict] = []
    for r in rows:
        labs = r.get("labels") or {}
        nf = labs.get("n_faces") or 0
        iid = str(r.get("image_id") or "")
        if ".see-cache" in iid:
            continue
        if nf == 0:
            empties.append(r)
        if labs.get("kiss_geo"):
            kisses.append(r)

    kisses.sort(key=kiss_far_key)
    empties.sort(key=lambda r: (r.get("film_slug") or "", r.get("filename") or r.get("image_id") or ""))

    by_scene: dict[str, list[dict]] = defaultdict(list)
    for e in empties:
        by_scene[scene_of(e)].append(e)
    # for mode=any, put all empties in unlabeled stream too
    if args.empty_pair == "any":
        by_scene["unlabeled"] = list(empties)

    n_kiss = len(kisses)
    n_empty = len(empties)
    scene_counts = {k: len(v) for k, v in sorted(by_scene.items())}

    order_map = {
        "eek": ("empty", "empty", "kiss"),
        "eke": ("empty", "kiss", "empty"),
        "kee": ("kiss", "empty", "empty"),
    }
    pattern = order_map[args.order]

    units = []
    idx: dict[str, int] = defaultdict(int)
    pair_tags: dict[str, int] = defaultdict(int)

    for ui, kiss in enumerate(kisses):
        picked = pick_empty_pair(by_scene, idx, args.empty_pair)
        if not picked:
            break
        e1, e2, pair_tag = picked
        pair_tags[pair_tag] += 1
        slot_rows = {"empty": [e1, e2], "kiss": [kiss]}
        e_i = 0
        slots = []
        for kind in pattern:
            if kind == "empty":
                row = slot_rows["empty"][e_i]
                e_i += 1
            else:
                row = slot_rows["kiss"][0]
            labs = row.get("labels") or {}
            slots.append(
                {
                    "kind": kind,
                    "image_id": row.get("image_id"),
                    "path": row.get("path"),
                    "film_slug": row.get("film_slug"),
                    "closeup": labs.get("closeup"),
                    "eye_dist": labs.get("eye_dist"),
                    "mouth_dist_norm": labs.get("mouth_dist_norm"),
                    "n_faces": labs.get("n_faces"),
                    "scene_type": labs.get("scene_type"),
                }
            )
        units.append(
            {
                "unit_index": ui,
                "order": args.order,
                "pattern": list(pattern),
                "empty_pair_mode": args.empty_pair,
                "empty_pair_tag": pair_tag,
                "kiss_scale": "close" if (kiss.get("labels") or {}).get("closeup") else "far",
                "slots": slots,
            }
        )

    max_units = len(units)

    # Gap math: approximate slots for duration
    if args.flat_rate and args.flat_rate > 0:
        slots_need = int(math.ceil(args.duration * args.flat_rate))
        rate_note = f"flat {args.flat_rate}"
    else:
        # linear ramp start→end over full duration → avg rate
        avg = (args.start_rate + args.end_rate) / 2.0
        slots_need = int(math.ceil(args.duration * avg))
        rate_note = f"ramp {args.start_rate}→{args.end_rate} avg≈{avg:.1f}"

    units_need = int(math.ceil(slots_need / 3.0))
    kiss_need = units_need
    empty_need = units_need * 2
    kiss_gap = max(0, kiss_need - n_kiss)
    empty_gap = max(0, empty_need - n_empty)

    out_dir = DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    units_path = args.out or (out_dir / "units_1k2e.jsonl")
    units_path = units_path.expanduser().resolve()
    with units_path.open("w") as f:
        for u in units:
            f.write(json.dumps(u, separators=(",", ":"), ensure_ascii=False) + "\n")

    # nature/city pair capacity
    n_nat = scene_counts.get("nature", 0)
    n_city = scene_counts.get("city", 0)
    nature_city_units_cap = min(n_nat, n_city)  # one each per unit ideal

    gap_path = out_dir / "units_1k2e_gap.json"
    report = {
        "module": "select.units_1k2e",
        "unit_contract": "1 kiss : 2 empty establishing",
        "order": args.order,
        "pattern": list(pattern),
        "empty_pair_mode": args.empty_pair,
        "empty_pair_tags": dict(pair_tags),
        "pools": {
            "empty_n_faces_0": n_empty,
            "scene_type_counts": scene_counts,
            "nature_city_pair_cap": nature_city_units_cap,
            "kiss_geo": n_kiss,
            "kiss_far_not_closeup": sum(
                1 for k in kisses if not (k.get("labels") or {}).get("closeup")
            ),
            "kiss_closeup": sum(
                1 for k in kisses if (k.get("labels") or {}).get("closeup")
            ),
        },
        "units_built": max_units,
        "slots_if_unique": max_units * 3,
        "bottleneck": (
            "kiss"
            if max_units >= n_kiss
            else ("empty_scene_pair" if args.empty_pair != "any" else "empty")
        ),
        "target": {
            "duration_sec": args.duration,
            "rate": rate_note,
            "slots_need_approx": slots_need,
            "units_need": units_need,
            "kiss_need": kiss_need,
            "empty_need": empty_need,
        },
        "gaps": {
            "kiss_gap": kiss_gap,
            "empty_gap": empty_gap,
            "nature_gap_for_pair": max(0, n_kiss - n_nat) if args.empty_pair == "nature_city" else None,
            "city_gap_for_pair": max(0, n_kiss - n_city) if args.empty_pair == "nature_city" else None,
            "download_priority": (
                "kiss_meta_brute"
                if kiss_gap > 0
                else ("empty_establishing" if empty_gap > 0 else "none")
            ),
        },
        "unique_duration_at_rates": {
            "5": round((max_units * 3) / 5.0, 2),
            "10": round((max_units * 3) / 10.0, 2),
            "15": round((max_units * 3) / 15.0, 2),
            "30": round((max_units * 3) / 30.0, 2),
        },
        "reuse_needed_for_target": max_units < units_need,
        "units_output": str(units_path),
        "scene_numbers_file": str(DEFAULT_NUMBERS),
        "policy": "prefer nature+city establishers when scene_type labeled; grow kiss_geo primary",
    }
    gap_path.write_text(json.dumps(report, indent=2) + "\n")
    # snapshot numbers for later
    snap = out_dir / "units_1k2e_gap_latest.json"
    snap.write_text(json.dumps(report, indent=2) + "\n")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
