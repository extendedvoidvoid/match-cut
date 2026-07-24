#!/usr/bin/env python3
"""Eye-locked face montage — biggest unused stills, sacred-geometry smear, 6→30 fps + 10→100% scale."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

from export_naming import numbered_iterations_path, numbered_path
from poster_montage import scale_frac_at
from render import (
    CANVAS_H,
    CANVAS_W,
    DEFAULT_CACHE,
    DEFAULT_IMAGES,
    EYE_TARGET_X,
    EYE_TARGET_Y,
    QualifiedImage,
    analyze_image,
    cap_durations_for_unique_pool,
    collect_images,
    compute_durations,
    create_face_landmarker,
    filter_existing,
    has_eye_lock,
    resolve_head_oval,
    warp_head_mask,
)
from sacred_geometry import PuzzleState, capacity_at, render_background_layer

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
MANIFESTS = ROOT / "exports" / "manifests"
ELIGIBLE_CACHE = SCRIPT_DIR / "face_montage_eligible.jsonl"
DEFAULT_STEM = "insta_reel_face_montage_6-30_60s"
# End state: inter-eye span completes horizontal axis (~94% canvas width)
EYE_DIST_END_FRAC = 0.94


def eye_target_dist(scale_frac: float, start_scale: float, end_scale: float) -> float:
    """Ramp inter-eye distance from 10% width → full horizontal axis at end."""
    start_dist = CANVAS_W * start_scale
    end_dist = CANVAS_W * EYE_DIST_END_FRAC
    if scale_frac >= end_scale - 1e-6:
        return end_dist
    t = (scale_frac - start_scale) / max(end_scale - start_scale, 1e-6)
    t = max(0.0, min(1.0, t))
    return start_dist + (end_dist - start_dist) * t

STEM_RE = re.compile(r"film='([^']+)'\s+image=([^\s]+)")


def load_used_face_paths(film_grab: Path, manifests_dir: Path, *, exclude_prior_faces: bool) -> set[str]:
    """By default empty — last render was poster montage (different asset class)."""
    if not exclude_prior_faces:
        return set()

    stem_to_path: dict[str, str] = {p.stem: str(p) for p in film_grab.rglob("*.jpg")}
    used: set[str] = set()
    skip_names = ("poster_montage", "poster_pair", "triplet")
    for mf in manifests_dir.glob("*.txt"):
        if any(s in mf.name for s in skip_names):
            continue
        for line in mf.read_text().splitlines():
            m = STEM_RE.search(line)
            if not m:
                continue
            path = stem_to_path.get(m.group(2))
            if path:
                used.add(path)
    return used


def load_cached_eligible() -> list[QualifiedImage]:
    if not ELIGIBLE_CACHE.exists():
        return []
    out: list[QualifiedImage] = []
    for line in ELIGIBLE_CACHE.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        oval = tuple(tuple(p) for p in d["head_oval"]) if d.get("head_oval") else ()
        out.append(
            QualifiedImage(
                d["path"],
                tuple(d["left"]),
                tuple(d["right"]),
                d["eye_dist"],
                oval,
                d.get("film_slug", ""),
                d.get("film_title", ""),
            ),
        )
    return out


def save_eligible(pool: list[QualifiedImage]) -> None:
    from dataclasses import asdict

    ELIGIBLE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with ELIGIBLE_CACHE.open("w") as f:
        for q in pool:
            f.write(json.dumps(asdict(q), separators=(",", ":")) + "\n")


def build_eligible_pool(
    images_root: Path,
    cache_path: Path,
    used_paths: set[str],
    *,
    rescan: bool = False,
) -> list[QualifiedImage]:
    """All strict eye-lock stills, sorted biggest eye_dist first, excluding prior reels."""
    if not rescan:
        cached = [q for q in load_cached_eligible() if q.path not in used_paths and Path(q.path).is_file()]
        if cached:
            cached.sort(key=lambda q: q.eye_dist, reverse=True)
            print(f"loaded {len(cached)} eligible from cache", file=sys.stderr)
            return cached

    qualified_map: dict[str, QualifiedImage] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            oval = tuple(tuple(p) for p in d["head_oval"]) if d.get("head_oval") else ()
            slug, title = d.get("film_slug", ""), d.get("film_title", "")
            if not slug:
                slug = Path(d["path"]).parent.name
            if not title:
                title = slug.replace("-", " ").title()
            qualified_map[d["path"]] = QualifiedImage(
                d["path"], tuple(d["left"]), tuple(d["right"]), d["eye_dist"], oval, slug, title,
            )

    landmarker = create_face_landmarker(max_faces=1)
    renderable: list[QualifiedImage] = []
    try:
        images = collect_images(images_root)
        print(f"scanning {len(images)} stills for eye-lock (exclude {len(used_paths)} used)…", file=sys.stderr)
        for i, path in enumerate(images, 1):
            p = str(path)
            if p in used_paths:
                continue
            if p in qualified_map and has_eye_lock(qualified_map[p]):
                renderable.append(qualified_map[p])
                continue
            if i % 250 == 0:
                print(f"  {i}/{len(images)} renderable={len(renderable)}", file=sys.stderr)
            q = analyze_image(path, landmarker)
            if q:
                renderable.append(q)
    finally:
        landmarker.close()

    renderable = filter_existing(renderable)
    renderable.sort(key=lambda q: q.eye_dist, reverse=True)
    save_eligible(renderable)
    print(f"eligible pool: {len(renderable)} (biggest eye_dist={renderable[0].eye_dist:.1f})", file=sys.stderr)
    return renderable


def align_eye_montage_frame(
    img_bgr: np.ndarray,
    q: QualifiedImage,
    head_oval: tuple[tuple[float, float], ...],
    scale_frac: float,
    frame_index: int,
    time_sec: float,
    seed: int,
    puzzle: PuzzleState,
    *,
    start_scale: float = 0.10,
    end_scale: float = 1.0,
    total_sec: float = 60.0,
) -> np.ndarray:
    """Eye-lock; inter-eye ramps to span horizontal axis at end."""
    h, w = img_bgr.shape[:2]
    left, right = q.left, q.right
    ecx = (left[0] + right[0]) / 2.0
    ecy = (left[1] + right[1]) / 2.0
    dist = math.hypot(right[0] - left[0], right[1] - left[1])
    angle = math.atan2(right[1] - left[1], right[0] - left[0])

    target_dist = eye_target_dist(scale_frac, start_scale, end_scale)
    eye_scale = target_dist / max(dist, 1.0)
    sw, sh = w * eye_scale, h * eye_scale
    if scale_frac >= 0.85:
        canvas_scale = max(CANVAS_W / sw, CANVAS_H / sh)
    else:
        canvas_scale = min(CANVAS_W / sw, CANVAS_H / sh, 1.0)
    s = eye_scale * canvas_scale

    cos_a = math.cos(-angle)
    sin_a = math.sin(-angle)
    t1 = np.array([[1, 0, -ecx], [0, 1, -ecy], [0, 0, 1]], dtype=np.float64)
    sc = np.array([[s, 0, 0], [0, s, 0], [0, 0, 1]], dtype=np.float64)
    rot = np.array([[cos_a, -sin_a, 0], [sin_a, cos_a, 0], [0, 0, 1]], dtype=np.float64)
    t2 = np.array([[1, 0, EYE_TARGET_X], [0, 1, EYE_TARGET_Y], [0, 0, 1]], dtype=np.float64)
    m = (t2 @ rot @ sc @ t1)[:2, :]

    bgra = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    warped = cv2.warpAffine(
        bgra, m, (CANVAS_W, CANVAS_H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    head_mask = warp_head_mask(head_oval, m)
    face_rgb = warped[:, :, :3].copy()
    return render_background_layer(
        face_rgb, head_mask, frame_index, time_sec, seed, total_sec, puzzle,
    )


def select_biggest_unused(
    pool: list[QualifiedImage],
    count: int,
    seed: int,
) -> list[QualifiedImage]:
    """Top N by eye_dist — already sorted; deterministic shuffle within equal tiers via seed."""
    top = pool[:count]
    if len(top) <= 1:
        return top
    # Preserve size ranking but vary order slightly among similar spans
    bands: dict[int, list[QualifiedImage]] = {}
    for q in top:
        band = int(q.eye_dist // 20)
        bands.setdefault(band, []).append(q)
    import random

    rng = random.Random(seed)
    ordered: list[QualifiedImage] = []
    for band in sorted(bands.keys(), reverse=True):
        chunk = bands[band][:]
        rng.shuffle(chunk)
        ordered.extend(chunk)
    return ordered[:count]


def apply_negative_toggle(frame: np.ndarray, frame_index: int, every: int, phase: int) -> np.ndarray:
    """Photographic invert when (index + phase) % every == 0. every<=0 disables."""
    if every <= 0:
        return frame
    if ((frame_index + phase) % every) == 0:
        return cv2.bitwise_not(frame)
    return frame


def render_face_montage(
    picks: list[QualifiedImage],
    durations: list[float],
    out_path: Path,
    seed: int,
    ramp_until: float = 30.0,
    start_scale: float = 0.10,
    end_scale: float = 1.0,
    iterations_path: Path | None = None,
    negative_every: int = 0,
    negative_phase: int = 1,
) -> dict:
    n = min(len(picks), len(durations))
    picks = picks[:n]
    durations = durations[:n]
    total_sec = sum(durations)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pad = max(4, len(str(n)))

    log_lines = [
        "# match-cut face montage — eye-lock + full-canvas background at max capacity",
        f"# seed={seed}  frames={n}  ramp_until={ramp_until}s  total={total_sec:.1f}s",
        f"# eyes {start_scale:.0%}→{EYE_DIST_END_FRAC:.0%} canvas width (horizontal axis)  |  6→30 fps",
        "# background: 100% outside-head smudge + tiled geometry puzzle (1 cell/frame → 540)",
        "# capacity: 0→1 linear over 60s — density max at end",
        (
            f"# negative_toggle: every={negative_every} phase={negative_phase}"
            if negative_every > 0
            else "# negative_toggle: off"
        ),
        "",
    ]
    t = 0.0
    landmarker = create_face_landmarker(max_faces=1)
    oval_cache: dict[str, tuple[tuple[float, float], ...]] = {}
    puzzle = PuzzleState()

    try:
        with tempfile.TemporaryDirectory(prefix="reel-face-montage-") as tmp:
            tmp_path = Path(tmp)
            concat_lines: list[str] = []

            for i, (q, dur) in enumerate(zip(picks, durations)):
                bgr = cv2.imread(q.path)
                if bgr is None:
                    continue
                if q.path not in oval_cache:
                    oval_cache[q.path] = resolve_head_oval(q, landmarker)
                sf = scale_frac_at(t, ramp_until, start_scale, end_scale)
                frame = align_eye_montage_frame(
                    bgr, q, oval_cache[q.path], sf, i, t, seed, puzzle,
                    start_scale=start_scale, end_scale=end_scale, total_sec=total_sec,
                )
                frame = apply_negative_toggle(frame, i, negative_every, negative_phase)
                frame_path = tmp_path / f"frame_{i:0{pad}d}.png"
                cv2.imwrite(str(frame_path), frame)
                concat_lines.append(f"file '{frame_path}'")
                concat_lines.append(f"duration {dur:.6f}")

                fps = 1.0 / dur if dur > 0 else 0.0
                td = eye_target_dist(sf, start_scale, end_scale)
                cap = capacity_at(t, total_sec)
                cells = puzzle.cells_for_frame(i)
                log_lines.append(
                    f"frame={i:04d}  film={q.film_title!r}  image={Path(q.path).stem}  "
                    f"eye_dist={q.eye_dist:.1f}  t={t:.3f}s  dur={dur:.4f}s  "
                    f"fps={fps:.2f}  scale={sf:.3f}  target_ied={td:.1f}px  "
                    f"capacity={cap:.3f}  puzzle_cells={cells}"
                )
                t += dur

            if not concat_lines:
                raise RuntimeError("no frames rendered")

            concat_lines.append(f"file '{tmp_path / f'frame_{len(picks)-1:0{pad}d}.png'}'")
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
    finally:
        landmarker.close()

    iter_path = iterations_path or numbered_iterations_path(out_path)
    iter_path.write_text("\n".join(log_lines) + "\n")

    return {
        "mode": "face_montage",
        "frames": len(picks),
        "duration_sec": total_sec,
        "output": str(out_path),
        "iterations": str(iter_path),
        "seed": seed,
        "start_scale": start_scale,
        "end_scale": end_scale,
        "negative_every": negative_every,
        "negative_phase": negative_phase,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Eye-locked face montage + sacred geometry smear")
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-number", action="store_true")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--start-rate", type=float, default=6.0)
    parser.add_argument("--end-rate", type=float, default=30.0)
    parser.add_argument("--ramp-until", type=float, default=30.0)
    parser.add_argument("--start-scale", type=float, default=0.10)
    parser.add_argument("--end-scale", type=float, default=1.0)
    parser.add_argument("--target-frames", type=int, default=1440)
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--rescan", action="store_true", help="Rescan all stills for eligible pool")
    parser.add_argument(
        "--exclude-prior-faces", action="store_true",
        help="Skip stills used in earlier face reels (default: only avoid poster-montage overlap)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--iterations", type=Path, default=None)
    parser.add_argument(
        "--negative-every",
        type=int,
        default=0,
        help="Invert every N frames (2=on/off). 0=off. Mixes with smudge edges.",
    )
    parser.add_argument(
        "--negative-phase",
        type=int,
        default=1,
        help="Offset for negative toggle (default 1 → frame0 POS, frame1 NEG)",
    )
    args = parser.parse_args()

    used = load_used_face_paths(args.images, MANIFESTS, exclude_prior_faces=args.exclude_prior_faces)
    eligible = build_eligible_pool(args.images, args.cache, used, rescan=args.rescan or args.exclude_prior_faces)

    durations = compute_durations(
        args.duration, args.start_rate, args.end_rate, args.ramp_until,
    )
    frame_count = min(args.target_frames, len(durations))
    durations = durations[:frame_count]
    durations, capped = cap_durations_for_unique_pool(durations, len(eligible))
    picks = select_biggest_unused(eligible, len(durations), args.seed)

    out_path = args.output
    if out_path is None and not args.no_number:
        out_path = numbered_path(DEFAULT_STEM)
    elif out_path is None:
        out_path = Path.home() / "Downloads" / f"{DEFAULT_STEM}.mp4"

    print(
        f"face montage: {len(picks)} frames  eligible={len(eligible)}  excluded_used={len(used)}  "
        f"rate {args.start_rate}→{args.end_rate}  scale {args.start_scale:.0%}→{args.end_scale:.0%}  "
        f"capped={capped}",
        file=sys.stderr,
    )

    if args.dry_run:
        print(json.dumps({
            "frames": len(picks),
            "eligible": len(eligible),
            "excluded": len(used),
            "top_eye_dist": picks[0].eye_dist if picks else 0,
            "capped": capped,
            "output": str(out_path),
        }, indent=2))
        return 0

    if not picks:
        print("no eligible faces", file=sys.stderr)
        return 1

    result = render_face_montage(
        picks, durations, out_path, args.seed,
        args.ramp_until, args.start_scale, args.end_scale, args.iterations,
        negative_every=args.negative_every,
        negative_phase=args.negative_phase,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())