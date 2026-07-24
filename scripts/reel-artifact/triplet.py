#!/usr/bin/env python3
"""Face extreme → paysage (no people) → textless poster. Equal thirds, 1→30 fps ramp."""

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
from paysage import PaysageImage, PaysageDeck, align_cover, align_face_matrix, scan_paysage
from render import (
    DEFAULT_CACHE,
    DEFAULT_IMAGES,
    UniqueDeck,
    cap_durations_for_unique_pool,
    collect_images,
    compute_durations,
    create_face_landmarker,
    filter_existing,
    load_pool,
)

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fetch-posters"))
from poster_pool import UniquePosterDeck, load_textless_pool  # noqa: E402

DEFAULT_STEM = "insta_reel_triplet_1-30_60s"
PAYAGE_CACHE = SCRIPT_DIR / "paysage.jsonl"


def render_triplet_reel(
    face_pool: list,
    paysage_pool: list[PaysageImage],
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
    paysage_deck = PaysageDeck(paysage_pool, seed + 503)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pad = max(4, len(str(n * 3)))

    face_lm = create_face_landmarker(max_faces=1)
    hand_lm = create_hand_landmarker()
    total_sec = sum(durations)
    log_lines = [
        "# match-cut triplet — face → paysage → textless poster (same film for poster)",
        f"# seed={seed}  slots={n}  ramp_until={ramp_until}s",
        "# unique: each face, each paysage, each poster_path once",
        "",
    ]
    t = 0.0
    render_durations: list[float] = []
    triplets = 0
    frames_written = 0

    try:
        with tempfile.TemporaryDirectory(prefix="reel-triplet-") as tmp:
            tmp_path = Path(tmp)
            concat_lines: list[str] = []
            exhausted = False

            for i, dur in enumerate(durations):
                third = dur / 3.0
                zoom_frac = head_zoom_frac(t, ramp_until, total_sec)

                hit = None
                resolved = None
                poster_asset = None
                paysage = None
                while True:
                    hit = draw_renderable_still(face_deck, face_lm)
                    if hit is None:
                        exhausted = True
                        break
                    fq, fbgr = hit
                    slug = Path(fq.path).parent.name
                    poster_asset = poster_deck.draw_for_slug(slug)
                    paysage = paysage_deck.draw()
                    if poster_asset is None or paysage is None:
                        continue
                    resolved = anchor_for_still(
                        fbgr, fq, BodyPart.HEAD_EXTREME, face_lm, hand_lm,
                    )
                    if resolved:
                        break
                if exhausted:
                    print(f"warn: exhausted at slot {i}/{n} ({triplets} triplets)", file=sys.stderr)
                    break
                assert hit and resolved and poster_asset and paysage

                fq, fbgr = hit
                _, anchor = resolved
                paysage_bgr = cv2.imread(paysage.path)
                poster_bgr = cv2.imread(poster_asset.path)
                if paysage_bgr is None or poster_bgr is None:
                    continue

                face_layer, _ = align_face_matrix(fbgr, anchor, zoom_frac)
                layers = (
                    ("face", face_layer),
                    ("paysage", align_cover(paysage_bgr)),
                    ("poster", align_cover(poster_bgr)),
                )
                for _, frame in layers:
                    fp = tmp_path / f"frame_{frames_written:0{pad}d}.png"
                    cv2.imwrite(str(fp), frame)
                    concat_lines.append(f"file '{fp}'")
                    concat_lines.append(f"duration {third:.6f}")
                    frames_written += 1

                log_lines.append(
                    f"triplet={triplets:04d}  face={Path(fq.path).stem}  "
                    f"paysage={Path(paysage.path).stem}  poster={Path(poster_asset.path).name}  "
                    f"t={t:.3f}s  zoom={zoom_frac:.2f}"
                )
                render_durations.append(dur)
                t += dur
                triplets += 1

            if triplets == 0:
                raise RuntimeError("no triplets rendered")

            if exhausted and triplets < n:
                scale = total_sec / sum(render_durations)
                third_scaled = [d * scale / 3.0 for d in render_durations]
                concat_lines = []
                fi = 0
                for td in third_scaled:
                    for _ in range(3):
                        concat_lines.append(f"file '{tmp_path / f'frame_{fi:0{pad}d}.png'}'")
                        concat_lines.append(f"duration {td:.6f}")
                        fi += 1
                render_durations = [d * scale for d in render_durations]

            concat_lines.append(f"file '{tmp_path / f'frame_{frames_written-1:0{pad}d}.png'}'")
            (tmp_path / "concat.txt").write_text("\n".join(concat_lines) + "\n")

            import subprocess
            subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", str(tmp_path / "concat.txt"),
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
        "mode": "triplet",
        "triplets": triplets,
        "frames": frames_written,
        "duration_sec": sum(render_durations),
        "output": str(out_path),
        "iterations": str(iter_path),
        "unique_faces": True,
        "unique_paysages": True,
        "unique_posters": True,
        "seed": seed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Face → paysage → textless poster")
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
    args = parser.parse_args()

    poster_pool = load_textless_pool()
    slug_posters = [a for a in poster_pool if a.film_slug]
    poster_deck = UniquePosterDeck(poster_pool, args.seed)

    images = collect_images(args.images)
    paysage_pool = scan_paysage(images, PAYAGE_CACHE, rescan=False)
    durations = compute_durations(args.duration, args.start_rate, args.end_rate, args.ramp_until)
    face_pool = load_pool(args.images, args.cache, args.pool)
    cap = min(len(face_pool), len(paysage_pool), len(slug_posters))
    durations, _ = cap_durations_for_unique_pool(durations, cap or len(durations))

    if args.dry_run:
        print(json.dumps({
            "slots": len(durations),
            "textless_variants": len(slug_posters),
            "paysage": len(paysage_pool),
            "faces": len(face_pool),
        }, indent=2))
        return 0

    if not slug_posters or not paysage_pool:
        print("error: need textless posters + paysage pool", file=sys.stderr)
        return 1

    out_path = args.output or (numbered_path(DEFAULT_STEM) if not args.no_number else ROOT / "exports" / "reels" / f"{DEFAULT_STEM}.mp4")
    report = render_triplet_reel(
        face_pool, paysage_pool, poster_deck, durations, out_path, args.seed, args.ramp_until,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())