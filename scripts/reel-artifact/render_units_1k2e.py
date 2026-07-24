#!/usr/bin/env python3
"""60s reel from 1 kiss : 2 empty units (nature+city + far→close kiss).

Cycles units if fewer than slots needed. Rate crescendo via compute_durations.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

from export_naming import numbered_iterations_path, numbered_path
from render import CANVAS_H, CANVAS_W, compute_durations

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UNITS = ROOT / "assets" / "film-grab" / "pools" / "units_1k2e.jsonl"
DEFAULT_STEM = "insta_reel_kiss_1k2e_crescendo_60s"


def load_units(path: Path) -> list[dict]:
    units = []
    for line in path.read_text().splitlines():
        if line.strip():
            units.append(json.loads(line))
    return units


def flatten_slots(units: list[dict]) -> list[dict]:
    """Ordered stream: unit0 e,e,k, unit1 e,e,k, … (already far→close by unit index)."""
    slots = []
    for u in units:
        for s in u.get("slots") or []:
            s = dict(s)
            s["unit_index"] = u.get("unit_index")
            s["kiss_scale"] = u.get("kiss_scale")
            s["empty_pair_tag"] = u.get("empty_pair_tag")
            slots.append(s)
    return slots


def resolve_path(slot: dict) -> Path | None:
    p = slot.get("path")
    if p and Path(p).is_file():
        return Path(p)
    iid = slot.get("image_id")
    if iid:
        cand = ROOT / "assets" / "film-grab" / iid
        if cand.is_file():
            return cand
    return None


def fit_cover(bgr: np.ndarray) -> np.ndarray:
    h, w = bgr.shape[:2]
    scale = max(CANVAS_W / w, CANVAS_H / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)
    x0 = max(0, (nw - CANVAS_W) // 2)
    y0 = max(0, (nh - CANVAS_H) // 2)
    crop = resized[y0 : y0 + CANVAS_H, x0 : x0 + CANVAS_W]
    if crop.shape[0] != CANVAS_H or crop.shape[1] != CANVAS_W:
        canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
        ch, cw = crop.shape[:2]
        canvas[:ch, :cw] = crop
        return canvas
    return crop


def main() -> int:
    p = argparse.ArgumentParser(description="Render 1k2e unit crescendo reel")
    p.add_argument("--units", type=Path, default=DEFAULT_UNITS)
    p.add_argument("--duration", type=float, default=60.0)
    p.add_argument("--start-rate", type=float, default=2.0)
    p.add_argument("--end-rate", type=float, default=24.0)
    p.add_argument("--ramp-until", type=float, default=60.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    units_path = args.units.expanduser().resolve()
    if not units_path.is_file():
        print(f"error: missing {units_path} — run select.units_1k2e first", file=sys.stderr)
        return 1

    units = load_units(units_path)
    base_slots = flatten_slots(units)
    if not base_slots:
        print("error: no slots in units file", file=sys.stderr)
        return 1

    durations = compute_durations(
        args.duration, args.start_rate, args.end_rate, args.ramp_until
    )
    n = len(durations)

    # cycle slots for full duration
    stream = [base_slots[i % len(base_slots)] for i in range(n)]

    out_path = args.output
    if out_path is None:
        out_path = numbered_path(DEFAULT_STEM)
    else:
        out_path = out_path.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"render 1k2e: units={len(units)} unique_slots={len(base_slots)} "
        f"frames={n} duration={sum(durations):.1f}s rate {args.start_rate}→{args.end_rate} "
        f"out={out_path}",
        file=sys.stderr,
    )
    if args.dry_run:
        print(json.dumps({"frames": n, "units": len(units), "output": str(out_path)}, indent=2))
        return 0

    pad = max(4, len(str(n)))
    log_lines = [
        "# match-cut 1 kiss : 2 empty (nature+city) + kiss far→close + rate crescendo",
        f"# units={len(units)} unique_slots={len(base_slots)} frames={n} "
        f"rate={args.start_rate}→{args.end_rate} duration={args.duration}s",
        f"# cycle units to fill 60s (reuse={'yes' if n > len(base_slots) else 'no'})",
        "",
    ]

    with tempfile.TemporaryDirectory(prefix="reel-1k2e-") as tmp:
        tmp_path = Path(tmp)
        t = 0.0
        written = 0
        for i, (slot, dur) in enumerate(zip(stream, durations)):
            path = resolve_path(slot)
            if path is None:
                print(f"warn: missing {slot.get('image_id')}", file=sys.stderr)
                continue
            bgr = cv2.imread(str(path))
            if bgr is None:
                print(f"warn: read fail {path}", file=sys.stderr)
                continue
            frame = fit_cover(bgr)
            fp = tmp_path / f"f{i:0{pad}d}.png"
            cv2.imwrite(str(fp), frame)
            fps = 1.0 / dur if dur > 0 else 0.0
            log_lines.append(
                f"{i:04d}  t={t:.3f}s  fps={fps:.2f}  kind={slot.get('kind')}  "
                f"scene={slot.get('scene_type')}  scale={slot.get('kiss_scale')}  "
                f"unit={slot.get('unit_index')}  {slot.get('image_id')}"
            )
            t += dur
            written += 1
            if (i + 1) % 50 == 0:
                print(f"  framed {i+1}/{n}", file=sys.stderr)

        if written == 0:
            print("error: no frames written", file=sys.stderr)
            return 1

        # variable duration via concat demuxer is heavy; use fixed high fps + duplicate
        # Simpler: ffmpeg with -framerate based on average, or use filter_complex setpts
        # Match other reels: write duration list and use concat
        list_file = tmp_path / "concat.txt"
        with list_file.open("w") as f:
            for i, dur in enumerate(durations[:written]):
                fp = tmp_path / f"f{i:0{pad}d}.png"
                if not fp.is_file():
                    continue
                f.write(f"file '{fp}'\n")
                f.write(f"duration {dur:.6f}\n")
            # last file must be listed again for concat demuxer
            last = tmp_path / f"f{written-1:0{pad}d}.png"
            f.write(f"file '{last}'\n")

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-vf",
            f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease,"
            f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        print("ffmpeg…", file=sys.stderr)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr[-2000:], file=sys.stderr)
            return r.returncode

    iter_path = numbered_iterations_path(out_path)
    iter_path.write_text("\n".join(log_lines) + "\n")
    summary = {
        "module": "render.units_1k2e",
        "output": str(out_path),
        "iterations": str(iter_path),
        "units": len(units),
        "unique_slots": len(base_slots),
        "frames": written,
        "duration_sec": round(sum(durations[:written]), 2),
        "start_rate": args.start_rate,
        "end_rate": args.end_rate,
        "cycled": written > len(base_slots),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
