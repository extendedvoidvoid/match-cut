#!/usr/bin/env python3
"""Face extreme close-up over paysage (no people) — same 1→30 fps ramp as closeup."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from mediapipe.tasks.python.vision.core import image as mp_image

from closeup import (
    HEAD_ZOOM_END_FRAC,
    HEAD_ZOOM_START_FRAC,
    BodyPart,
    PartAnchor,
    anchor_for_still,
    create_hand_landmarker,
    draw_renderable_still,
    head_zoom_frac,
)
from render import (
    CANVAS_H,
    CANVAS_W,
    DEFAULT_CACHE,
    DEFAULT_IMAGES,
    QualifiedImage,
    UniqueDeck,
    cap_durations_for_unique_pool,
    collect_images,
    compute_durations,
    create_face_landmarker,
    expand_oval_from_eyes,
    film_meta_from_path,
    filter_existing,
    head_oval_points,
    load_pool,
    scan_qualified,
    warp_head_mask,
)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PAYAGE_CACHE = SCRIPT_DIR / "paysage.jsonl"
DEFAULT_OUT = (
    Path(__file__).resolve().parents[2]
    / "exports"
    / "reels"
    / "insta_reel_paysage_1-30_60s.mp4"
)
MASK_FEATHER = 5


@dataclass
class PaysageImage:
    path: str
    film_slug: str
    film_title: str


def scan_paysage(
    images: list[Path],
    cache_path: Path,
    rescan: bool,
) -> list[PaysageImage]:
    if cache_path.exists() and not rescan:
        loaded: list[PaysageImage] = []
        for line in cache_path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            loaded.append(PaysageImage(d["path"], d["film_slug"], d["film_title"]))
        print(f"loaded {len(loaded)} paysage from cache", file=sys.stderr)
        return loaded

    landmarker = create_face_landmarker(max_faces=3)
    paysages: list[PaysageImage] = []
    try:
        print(f"scanning {len(images)} stills for paysage (0 faces)…", file=sys.stderr)
        for i, path in enumerate(images, 1):
            if i % 200 == 0:
                print(f"  scanned {i}/{len(images)} paysage={len(paysages)}", file=sys.stderr)
            bgr = cv2.imread(str(path))
            if bgr is None:
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            mp_img = mp_image.Image(image_format=mp_image.ImageFormat.SRGB, data=rgb)
            res = landmarker.detect(mp_img)
            if res.face_landmarks:
                continue
            slug, title = film_meta_from_path(str(path))
            paysages.append(PaysageImage(str(path), slug, title))
    finally:
        landmarker.close()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w") as f:
        for p in paysages:
            f.write(json.dumps(asdict(p), separators=(",", ":")) + "\n")
    print(f"paysage: {len(paysages)} / {len(images)}", file=sys.stderr)
    return paysages


def filter_existing_paysage(pool: list[PaysageImage]) -> list[PaysageImage]:
    return [p for p in pool if Path(p.path).is_file()]


class PaysageDeck:
    """Shuffled paysage pool — each path at most once."""

    def __init__(self, items: list[PaysageImage], seed: int) -> None:
        import random

        self._items = items[:]
        random.Random(seed).shuffle(self._items)
        self._idx = 0
        self.used_paths: set[str] = set()

    def draw(self) -> PaysageImage | None:
        while self._idx < len(self._items):
            p = self._items[self._idx]
            self._idx += 1
            if p.path in self.used_paths:
                continue
            self.used_paths.add(p.path)
            return p
        return None


def align_cover(bgr: np.ndarray) -> np.ndarray:
    """Cover-fill 9:16 canvas (landscape background)."""
    h, w = bgr.shape[:2]
    scale = max(CANVAS_W / w, CANVAS_H / h)
    nw, nh = max(1, int(math.ceil(w * scale))), max(1, int(math.ceil(h * scale)))
    resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x0 = max(0, (nw - CANVAS_W) // 2)
    y0 = max(0, (nh - CANVAS_H) // 2)
    crop = resized[y0 : y0 + CANVAS_H, x0 : x0 + CANVAS_W]
    if crop.shape[0] != CANVAS_H or crop.shape[1] != CANVAS_W:
        crop = cv2.resize(crop, (CANVAS_W, CANVAS_H), interpolation=cv2.INTER_LINEAR)
    return crop


def align_face_matrix(
    bgr: np.ndarray,
    anchor: PartAnchor,
    target_frac: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Warp face close-up; return canvas image + 3×3 transform for head mask."""
    h, w = bgr.shape[:2]
    target_px = min(CANVAS_W, CANVAS_H) * target_frac
    feature_scale = target_px / max(anchor.span, 1.0)
    sw, sh = w * feature_scale, h * feature_scale
    canvas_scale = max(CANVAS_W / sw, CANVAS_H / sh)
    s = feature_scale * canvas_scale

    cos_a = math.cos(-anchor.angle)
    sin_a = math.sin(-anchor.angle)
    cx, cy = CANVAS_W / 2.0, CANVAS_H / 2.0

    t1 = np.array([[1, 0, -anchor.cx], [0, 1, -anchor.cy], [0, 0, 1]], dtype=np.float64)
    sc = np.array([[s, 0, 0], [0, s, 0], [0, 0, 1]], dtype=np.float64)
    rot = np.array([[cos_a, -sin_a, 0], [sin_a, cos_a, 0], [0, 0, 1]], dtype=np.float64)
    t2 = np.array([[1, 0, cx], [0, 1, cy], [0, 0, 1]], dtype=np.float64)
    m3 = t2 @ rot @ sc @ t1
    warped = cv2.warpAffine(
        bgr, m3[:2, :], (CANVAS_W, CANVAS_H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return warped, m3


def composite_face_on_paysage(
    face_bgr: np.ndarray,
    paysage_bgr: np.ndarray,
    head_oval: tuple[tuple[float, float], ...],
    left: tuple[float, float],
    right: tuple[float, float],
    matrix: np.ndarray,
) -> np.ndarray:
    """Head oval = face; everything else = paysage background."""
    bg = align_cover(paysage_bgr)
    oval = expand_oval_from_eyes(head_oval, left, right) if head_oval else ()
    mask = warp_head_mask(oval, matrix).astype(np.float32)
    if mask.any() and MASK_FEATHER > 0:
        k = MASK_FEATHER * 2 + 1
        mask = cv2.GaussianBlur(mask, (k, k), 0)
    mask3 = mask[:, :, None]
    fg = face_bgr.astype(np.float32)
    out = bg.astype(np.float32) * (1.0 - mask3) + fg * mask3
    return np.clip(out, 0, 255).astype(np.uint8)


def resolve_head_oval(
    q: QualifiedImage,
    bgr: np.ndarray,
    face_lm,
) -> tuple[tuple[float, float], ...]:
    if q.head_oval:
        return q.head_oval
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    mp_img = mp_image.Image(image_format=mp_image.ImageFormat.SRGB, data=rgb)
    res = face_lm.detect(mp_img)
    if not res.face_landmarks:
        return ()
    return expand_oval_from_eyes(
        head_oval_points(res.face_landmarks[0], w, h), q.left, q.right,
    )


def render_paysage_reel(
    face_pool: list[QualifiedImage],
    paysage_pool: list[PaysageImage],
    durations: list[float],
    out_path: Path,
    seed: int,
    ramp_until: float = 30.0,
    iterations_path: Path | None = None,
) -> dict:
    n = len(durations)
    face_pool = filter_existing(face_pool)
    paysage_pool = filter_existing_paysage(paysage_pool)
    face_deck = UniqueDeck(face_pool, seed)
    paysage_deck = PaysageDeck(paysage_pool, seed + 997)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pad = max(4, len(str(n)))

    face_lm = create_face_landmarker(max_faces=1)
    hand_lm = create_hand_landmarker()
    total_sec = sum(durations)
    log_lines = [
        "# match-cut paysage reel — extreme face over landscape (no people)",
        f"# seed={seed}  frames={n}  ramp_until={ramp_until}s  total={total_sec:.1f}s",
        "# policy: each face + each paysage used once — no repetition",
        f"# zoom {HEAD_ZOOM_START_FRAC}→{HEAD_ZOOM_END_FRAC} after ramp",
        "",
    ]
    t = 0.0
    render_durations: list[float] = []
    rendered = 0

    try:
        with tempfile.TemporaryDirectory(prefix="reel-paysage-") as tmp:
            tmp_path = Path(tmp)
            concat_lines: list[str] = []

            deck_exhausted = False
            for i, dur in enumerate(durations):
                zoom_frac = head_zoom_frac(t, ramp_until, total_sec)

                face_hit: tuple[QualifiedImage, np.ndarray] | None = None
                resolved: tuple[BodyPart, PartAnchor] | None = None
                while True:
                    face_hit = draw_renderable_still(face_deck, face_lm)
                    if face_hit is None:
                        deck_exhausted = True
                        print(
                            f"warn: face deck exhausted at frame {i}/{n} "
                            f"({rendered} rendered) — stretching timing",
                            file=sys.stderr,
                        )
                        break
                    fq, fbgr = face_hit
                    resolved = anchor_for_still(
                        fbgr, fq, BodyPart.HEAD_EXTREME, face_lm, hand_lm,
                    )
                    if resolved is not None:
                        break
                if deck_exhausted:
                    break

                paysage = paysage_deck.draw()
                if paysage is None:
                    deck_exhausted = True
                    print(
                        f"warn: paysage deck exhausted at frame {i}/{n} "
                        f"({rendered} rendered) — stretching timing",
                        file=sys.stderr,
                    )
                    break

                assert face_hit is not None and resolved is not None
                fq, fbgr = face_hit
                part, anchor = resolved
                paysage_bgr = cv2.imread(paysage.path)
                if paysage_bgr is None:
                    raise RuntimeError(f"failed to read paysage {paysage.path}")

                oval = resolve_head_oval(fq, fbgr, face_lm)
                face_layer, m3 = align_face_matrix(fbgr, anchor, zoom_frac)
                frame = composite_face_on_paysage(
                    face_layer, paysage_bgr, oval, fq.left, fq.right, m3,
                )

                frame_path = tmp_path / f"frame_{rendered:0{pad}d}.png"
                cv2.imwrite(str(frame_path), frame)
                concat_lines.append(f"file '{frame_path}'")
                concat_lines.append(f"duration {dur:.6f}")
                render_durations.append(dur)

                fps = 1.0 / dur if dur > 0 else 0.0
                log_lines.append(
                    f"frame={rendered:04d}  face_film={fq.film_title!r}  "
                    f"face={Path(fq.path).stem}  paysage_film={paysage.film_title!r}  "
                    f"paysage={Path(paysage.path).stem}  t={t:.3f}s  fps={fps:.2f}  "
                    f"zoom={zoom_frac:.2f}"
                )
                t += dur
                rendered += 1

            if rendered == 0:
                raise RuntimeError("no renderable face+paysage pairs")

            if deck_exhausted and rendered < n:
                scale = total_sec / sum(render_durations)
                render_durations = [d * scale for d in render_durations]
                concat_lines = []
                for fi, dur in enumerate(render_durations):
                    concat_lines.append(f"file '{tmp_path / f'frame_{fi:0{pad}d}.png'}'")
                    concat_lines.append(f"duration {dur:.6f}")

            concat_lines.append(f"file '{tmp_path / f'frame_{rendered-1:0{pad}d}.png'}'")
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
        face_lm.close()
        hand_lm.close()

    iter_path = iterations_path or (out_path.parent / f"{out_path.stem}_iterations.txt")
    iter_path.write_text("\n".join(log_lines) + "\n")

    return {
        "mode": "paysage",
        "frames": rendered,
        "frames_requested": n,
        "duration_sec": sum(render_durations),
        "output": str(out_path),
        "iterations": str(iter_path),
        "face_pool_size": len(face_pool),
        "paysage_pool_size": len(paysage_pool),
        "faces_used": len(face_deck.used_paths),
        "paysages_used": len(paysage_deck.used_paths),
        "unique_stills": True,
        "ramp_until_sec": ramp_until,
        "head_zoom_frac": [HEAD_ZOOM_START_FRAC, HEAD_ZOOM_END_FRAC],
        "seed": seed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extreme face close-up composited over paysage (no people)",
    )
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--paysage-cache", type=Path, default=DEFAULT_PAYAGE_CACHE)
    parser.add_argument("--pool", choices=("all", "qualified"), default="all")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--start-rate", type=float, default=1.0)
    parser.add_argument("--end-rate", type=float, default=30.0)
    parser.add_argument("--ramp-until", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rescan", action="store_true", help="Rebuild face + paysage caches")
    parser.add_argument("--scan-paysage-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--iterations", type=Path, default=None)
    args = parser.parse_args()

    images = collect_images(args.images)
    durations = compute_durations(args.duration, args.start_rate, args.end_rate, args.ramp_until)

    if args.rescan and not args.scan_paysage_only:
        scan_qualified(images, args.cache, 8, True)

    paysage_pool = scan_paysage(
        images, args.paysage_cache, args.rescan or args.scan_paysage_only,
    )
    if args.scan_paysage_only:
        print(json.dumps({"paysage": len(filter_existing_paysage(paysage_pool))}, indent=2))
        return 0

    face_pool = load_pool(args.images, args.cache, args.pool)
    paysage_pool = filter_existing_paysage(paysage_pool)

    cap_pool = min(len(face_pool), len(paysage_pool))
    durations, capped = cap_durations_for_unique_pool(durations, cap_pool)
    if capped:
        print(
            f"warn: capped frames {len(durations)} to min(face,paysage)={cap_pool}",
            file=sys.stderr,
        )

    print(
        f"paysage frames={len(durations)} duration={sum(durations):.2f}s "
        f"rate {args.start_rate}→{args.end_rate} until {args.ramp_until}s "
        f"face_pool={len(face_pool)} paysage_pool={len(paysage_pool)}",
        file=sys.stderr,
    )

    if args.dry_run:
        print(json.dumps({
            "frames": len(durations),
            "face_pool": len(face_pool),
            "paysage_pool": len(paysage_pool),
            "cap_pool": cap_pool,
            "unique_stills": True,
        }, indent=2))
        return 0

    if not face_pool or not paysage_pool:
        print("error: need both face and paysage pools", file=sys.stderr)
        return 1

    report = render_paysage_reel(
        face_pool,
        paysage_pool,
        durations,
        args.output,
        args.seed,
        args.ramp_until,
        args.iterations,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())