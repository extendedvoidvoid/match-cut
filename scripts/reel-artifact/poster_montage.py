#!/usr/bin/env python3
"""Textless poster montage — centered scale crescendo + fps ramp. No repeats."""

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
from paysage import align_cover
from render import CANVAS_H, CANVAS_W, cap_durations_for_unique_pool, compute_durations

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fetch-posters"))
from poster_pool import UniquePosterDeck, load_textless_pool  # noqa: E402

DEFAULT_STEM = "insta_reel_poster_montage_6-30_60s"


def scale_frac_at(t: float, ramp_until: float, start_scale: float, end_scale: float) -> float:
    if t < ramp_until:
        p = t / max(ramp_until, 1e-6)
        return start_scale + (end_scale - start_scale) * p
    return end_scale


def render_poster_centered(bgr: np.ndarray, scale_frac: float) -> np.ndarray:
    if scale_frac >= 0.999:
        return align_cover(bgr)
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
    h, w = bgr.shape[:2]
    tw, th = max(1, int(CANVAS_W * scale_frac)), max(1, int(CANVAS_H * scale_frac))
    s = min(tw / w, th / h)
    nw, nh = max(1, int(w * s)), max(1, int(h * s))
    resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x0 = (CANVAS_W - nw) // 2
    y0 = (CANVAS_H - nh) // 2
    canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    return canvas


def render_poster_montage(
    poster_deck: UniquePosterDeck,
    durations: list[float],
    out_path: Path,
    seed: int,
    ramp_until: float = 30.0,
    start_scale: float = 0.10,
    end_scale: float = 1.0,
    iterations_path: Path | None = None,
) -> dict:
    n = len(durations)
    total_sec = sum(durations)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pad = max(4, len(str(n)))

    log_lines = [
        "# match-cut poster montage — strict textless TMDB posters only",
        f"# seed={seed}  frames={n}  ramp_until={ramp_until}s  total={total_sec:.1f}s",
        f"# scale {start_scale:.0%}→{end_scale:.0%} centered (cover at 100%)",
        "# policy: unique poster_path each frame — no repeats",
        "",
    ]
    t = 0.0
    render_durations: list[float] = []
    frames_written = 0

    with tempfile.TemporaryDirectory(prefix="reel-poster-montage-") as tmp:
        tmp_path = Path(tmp)
        concat_lines: list[str] = []
        deck_exhausted = False

        for i, dur in enumerate(durations):
            asset = poster_deck.draw()
            if asset is None:
                deck_exhausted = True
                print(
                    f"warn: poster deck exhausted at slot {i}/{n} ({frames_written} frames)",
                    file=sys.stderr,
                )
                break

            bgr = cv2.imread(asset.path)
            if bgr is None:
                continue

            sf = scale_frac_at(t, ramp_until, start_scale, end_scale)
            frame = render_poster_centered(bgr, sf)
            frame_path = tmp_path / f"frame_{frames_written:0{pad}d}.png"
            cv2.imwrite(str(frame_path), frame)
            concat_lines.append(f"file '{frame_path}'")
            concat_lines.append(f"duration {dur:.6f}")

            fps = 1.0 / dur if dur > 0 else 0.0
            log_lines.append(
                f"frame={frames_written:04d}  title={asset.title!r}  "
                f"poster={Path(asset.path).name}  tmdb={asset.tmdb_id}  "
                f"t={t:.3f}s  dur={dur:.4f}s  fps={fps:.2f}  scale={sf:.3f}"
            )
            render_durations.append(dur)
            t += dur
            frames_written += 1

        if frames_written == 0:
            raise RuntimeError(
                "no textless posters — run: mc fetch-posters status && mc fetch-posters bulk",
            )

        if deck_exhausted and frames_written < n:
            scale = total_sec / sum(render_durations)
            concat_lines = []
            for fi, d in enumerate(render_durations):
                scaled = d * scale
                concat_lines.append(f"file '{tmp_path / f'frame_{fi:0{pad}d}.png'}'")
                concat_lines.append(f"duration {scaled:.6f}")
            render_durations = [d * scale for d in render_durations]

        concat_lines.append(f"file '{tmp_path / f'frame_{frames_written - 1:0{pad}d}.png'}'")
        concat_file = tmp_path / "concat.txt"
        concat_file.write_text("\n".join(concat_lines) + "\n")

        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-c:v", "mpeg4", "-q:v", "5", "-pix_fmt", "yuv420p",
                str(out_path),
            ],
            check=True,
        )

    iter_path = iterations_path or numbered_iterations_path(out_path)
    iter_path.write_text("\n".join(log_lines) + "\n")

    return {
        "mode": "poster_montage",
        "frames": frames_written,
        "slots_requested": n,
        "duration_sec": sum(render_durations),
        "output": str(out_path),
        "iterations": str(iter_path),
        "unique_posters": True,
        "posters_used": poster_deck.used_count,
        "seed": seed,
        "start_scale": start_scale,
        "end_scale": end_scale,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Textless poster montage — 6→30 fps, 10%→100% centered scale",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-number", action="store_true")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--start-rate", type=float, default=6.0)
    parser.add_argument("--end-rate", type=float, default=30.0)
    parser.add_argument("--ramp-until", type=float, default=30.0)
    parser.add_argument("--start-scale", type=float, default=0.10)
    parser.add_argument("--end-scale", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--iterations", type=Path, default=None)
    args = parser.parse_args()

    pool = load_textless_pool()
    if not pool:
        print("empty textless pool", file=sys.stderr)
        return 1

    durations = compute_durations(
        args.duration, args.start_rate, args.end_rate, args.ramp_until,
    )
    durations, capped = cap_durations_for_unique_pool(durations, len(pool))
    poster_deck = UniquePosterDeck(pool, args.seed)

    out_path = args.output
    if out_path is None and not args.no_number:
        out_path = numbered_path(DEFAULT_STEM)
    elif out_path is None:
        out_path = Path.home() / "Downloads" / f"{DEFAULT_STEM}.mp4"

    print(
        f"poster montage: {len(durations)} frames  pool={len(pool)}  "
        f"rate {args.start_rate}→{args.end_rate} until {args.ramp_until}s  "
        f"scale {args.start_scale:.0%}→{args.end_scale:.0%}  capped={capped}",
        file=sys.stderr,
    )

    if args.dry_run:
        print(json.dumps({
            "frames": len(durations),
            "pool": len(pool),
            "capped": capped,
            "output": str(out_path),
        }, indent=2))
        return 0

    result = render_poster_montage(
        poster_deck,
        durations,
        out_path,
        args.seed,
        args.ramp_until,
        args.start_scale,
        args.end_scale,
        args.iterations,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())