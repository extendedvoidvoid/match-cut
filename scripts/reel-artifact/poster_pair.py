#!/usr/bin/env python3
"""Face extreme close-up → strict textless TMDB poster (same film). 50/50, no poster reuse."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import cv2

from closeup import (
    HEAD_ZOOM_END_FRAC,
    HEAD_ZOOM_START_FRAC,
    BodyPart,
    anchor_for_still,
    create_hand_landmarker,
    draw_renderable_still,
    head_zoom_frac,
)
from export_naming import numbered_iterations_path, numbered_path
from paysage import align_cover, align_face_matrix
from render import (
    DEFAULT_CACHE,
    DEFAULT_IMAGES,
    UniqueDeck,
    cap_durations_for_unique_pool,
    compute_durations,
    create_face_landmarker,
    filter_existing,
    load_pool,
)

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fetch-posters"))
from poster_pool import UniquePosterDeck, load_textless_pool  # noqa: E402

DEFAULT_STEM = "insta_reel_poster_pair_1-30_60s"


def render_poster_pair_reel(
    face_pool: list,
    poster_deck: UniquePosterDeck,
    durations: list[float],
    out_path: Path,
    seed: int,
    ramp_until: float = 30.0,
    iterations_path: Path | None = None,
) -> dict:
    n = len(durations)
    face_pool = filter_existing(face_pool)
    face_deck = UniqueDeck(face_pool, seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pad = max(4, len(str(n * 2)))

    face_lm = create_face_landmarker(max_faces=1)
    hand_lm = create_hand_landmarker()
    total_sec = sum(durations)
    log_lines = [
        "# match-cut poster-pair — face extreme → strict textless poster (same film_slug)",
        f"# seed={seed}  slots={n}  ramp_until={ramp_until}s  total={total_sec:.1f}s",
        "# policy: unique faces + unique poster_path each pair (50/50 timing)",
        "# TMDB: include_image_language=null only — no typed fallback",
        f"# zoom {HEAD_ZOOM_START_FRAC}→{HEAD_ZOOM_END_FRAC}",
        "",
    ]
    t = 0.0
    render_slot_durations: list[float] = []
    rendered_pairs = 0
    frames_written = 0

    try:
        with tempfile.TemporaryDirectory(prefix="reel-poster-pair-") as tmp:
            tmp_path = Path(tmp)
            concat_lines: list[str] = []

            deck_exhausted = False
            for i, dur in enumerate(durations):
                zoom_frac = head_zoom_frac(t, ramp_until, total_sec)
                half = dur / 2.0

                hit = None
                resolved = None
                poster_asset = None
                while True:
                    hit = draw_renderable_still(face_deck, face_lm)
                    if hit is None:
                        deck_exhausted = True
                        print(
                            f"warn: face deck exhausted at slot {i}/{n} ({rendered_pairs} pairs)",
                            file=sys.stderr,
                        )
                        break
                    fq, fbgr = hit
                    slug = Path(fq.path).parent.name
                    poster_asset = poster_deck.draw_for_slug(slug)
                    if poster_asset is None:
                        continue
                    resolved = anchor_for_still(
                        fbgr, fq, BodyPart.HEAD_EXTREME, face_lm, hand_lm,
                    )
                    if resolved is not None:
                        break
                if deck_exhausted:
                    break
                assert hit is not None and resolved is not None and poster_asset is not None
                fq, fbgr = hit
                _, anchor = resolved
                poster_bgr = cv2.imread(poster_asset.path)
                if poster_bgr is None:
                    continue

                face_layer, _ = align_face_matrix(fbgr, anchor, zoom_frac)
                poster_layer = align_cover(poster_bgr)

                for frame in (face_layer, poster_layer):
                    frame_path = tmp_path / f"frame_{frames_written:0{pad}d}.png"
                    cv2.imwrite(str(frame_path), frame)
                    concat_lines.append(f"file '{frame_path}'")
                    concat_lines.append(f"duration {half:.6f}")
                    frames_written += 1

                fps = 1.0 / dur if dur > 0 else 0.0
                log_lines.append(
                    f"pair={rendered_pairs:04d}  face_film={fq.film_title!r}  "
                    f"face={Path(fq.path).stem}  poster={Path(poster_asset.path).name}  "
                    f"poster_tmdb={poster_asset.poster_path}  t={t:.3f}s  "
                    f"slot_fps={fps:.2f}  zoom={zoom_frac:.2f}"
                )
                render_slot_durations.append(dur)
                t += dur
                rendered_pairs += 1

            if rendered_pairs == 0:
                raise RuntimeError(
                    "no face+textless poster pairs — run: mc fetch-posters purge-typed && "
                    "mc fetch-posters match-films --force",
                )

            if deck_exhausted and rendered_pairs < n:
                scale = total_sec / sum(render_slot_durations)
                scaled_half = [d * scale / 2.0 for d in render_slot_durations]
                concat_lines = []
                fi = 0
                for half_d in scaled_half:
                    for _ in range(2):
                        concat_lines.append(f"file '{tmp_path / f'frame_{fi:0{pad}d}.png'}'")
                        concat_lines.append(f"duration {half_d:.6f}")
                        fi += 1
                render_slot_durations = [d * scale for d in render_slot_durations]

            concat_lines.append(f"file '{tmp_path / f'frame_{frames_written-1:0{pad}d}.png'}'")
            concat_file = tmp_path / "concat.txt"
            concat_file.write_text("\n".join(concat_lines) + "\n")

            import subprocess
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
        face_lm.close()
        hand_lm.close()

    iter_path = iterations_path or numbered_iterations_path(out_path)
    iter_path.write_text("\n".join(log_lines) + "\n")

    return {
        "mode": "poster_pair",
        "pairs": rendered_pairs,
        "frames": frames_written,
        "slots_requested": n,
        "duration_sec": sum(render_slot_durations),
        "output": str(out_path),
        "iterations": str(iter_path),
        "unique_faces": True,
        "unique_posters": True,
        "posters_used": poster_deck.used_count,
        "seed": seed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Face → strict textless poster (50/50)")
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--pool", choices=("all", "qualified"), default="all")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-number", action="store_true")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--start-rate", type=float, default=1.0)
    parser.add_argument("--end-rate", type=float, default=30.0)
    parser.add_argument("--ramp-until", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--iterations", type=Path, default=None)
    args = parser.parse_args()

    pool = load_textless_pool()
    slug_assets = [a for a in pool if a.film_slug]
    poster_deck = UniquePosterDeck(pool, args.seed)

    durations = compute_durations(args.duration, args.start_rate, args.end_rate, args.ramp_until)
    face_pool = load_pool(args.images, args.cache, args.pool)
    cap = min(len(face_pool), len(slug_assets)) if slug_assets else 0
    durations, _ = cap_durations_for_unique_pool(durations, cap or len(durations))

    print(
        f"poster-pair slots={len(durations)} textless_slug_variants={len(slug_assets)} "
        f"face_pool={len(face_pool)}",
        file=sys.stderr,
    )

    if args.dry_run:
        print(json.dumps({
            "slots": len(durations),
            "textless_slug_variants": len(slug_assets),
            "face_pool": len(face_pool),
        }, indent=2))
        return 0

    if not slug_assets:
        print("error: no textless slug posters — mc fetch-posters match-films --force", file=sys.stderr)
        return 1

    if args.output:
        out_path = args.output
    elif args.no_number:
        out_path = ROOT / "exports" / "reels" / f"{DEFAULT_STEM}.mp4"
    else:
        out_path = numbered_path(DEFAULT_STEM)

    report = render_poster_pair_reel(
        face_pool, poster_deck, durations, out_path, args.seed, args.ramp_until, args.iterations,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())