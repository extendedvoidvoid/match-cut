#!/usr/bin/env python3
"""Close-up reel — cycle centered zoom on hands, lips, eyes, nose. No overlays."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision
from mediapipe.tasks.python.vision.core import image as mp_image

from render import (
    CANVAS_H,
    CANVAS_W,
    FACE_OVAL_IDX,
    QualifiedImage,
    UniqueDeck,
    cap_durations_for_unique_pool,
    collect_images,
    compute_durations,
    create_face_landmarker,
    filter_existing,
    has_eye_lock,
    hydrate_qualified,
    load_pool,
)

HAND_MODEL_PATH = Path(__file__).resolve().parent / "hand_landmarker.task"
HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

LEFT_EYE_IDX = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161)
RIGHT_EYE_IDX = (362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384)
LIP_IDX = (
    61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 308,
    324, 318, 402, 317, 14, 87, 178, 88, 95,
)
NOSE_IDX = (1, 2, 98, 327, 4, 5, 195, 197)


class BodyPart(str, Enum):
    RIGHT_HAND = "right_hand"
    LEFT_HAND = "left_hand"
    LIPS = "lips"
    EYES = "eyes"
    NOSE = "nose"
    HEAD_EXTREME = "head_extreme"


PART_CYCLE = (
    BodyPart.RIGHT_HAND,
    BodyPart.LEFT_HAND,
    BodyPart.LIPS,
    BodyPart.EYES,
    BodyPart.NOSE,
)

# How large the feature should appear on canvas (fraction of min canvas dim)
PART_TARGET_FRAC = {
    BodyPart.RIGHT_HAND: 0.48,
    BodyPart.LEFT_HAND: 0.48,
    BodyPart.LIPS: 0.40,
    BodyPart.EYES: 0.36,
    BodyPart.NOSE: 0.30,
    BodyPart.HEAD_EXTREME: 0.82,
}

# Post-ramp head zoom ramps from this → HEAD_EXTREME frac over the hold segment
HEAD_ZOOM_START_FRAC = 0.58
HEAD_ZOOM_END_FRAC = 0.88

CENTER_X = CANVAS_W / 2.0
CENTER_Y = CANVAS_H / 2.0


@dataclass
class PartAnchor:
    cx: float
    cy: float
    span: float
    angle: float


def ensure_hand_model() -> Path:
    if HAND_MODEL_PATH.exists():
        return HAND_MODEL_PATH
    import urllib.request

    HAND_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading hand model → {HAND_MODEL_PATH}", file=sys.stderr)
    urllib.request.urlretrieve(HAND_MODEL_URL, HAND_MODEL_PATH)
    return HAND_MODEL_PATH


def create_hand_landmarker() -> vision.HandLandmarker:
    options = vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(ensure_hand_model())),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=2,
        min_hand_detection_confidence=0.35,
        min_hand_presence_confidence=0.35,
        min_tracking_confidence=0.35,
    )
    return vision.HandLandmarker.create_from_options(options)


def _lm_points(landmarks, indices: tuple[int, ...], w: int, h: int) -> list[tuple[float, float]]:
    pts = []
    for idx in indices:
        if idx >= len(landmarks):
            continue
        lm = landmarks[idx]
        pts.append((lm.x * w, lm.y * h))
    return pts


def _centroid_span_angle(pts: list[tuple[float, float]]) -> PartAnchor | None:
    if len(pts) < 2:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    w_span = max(xs) - min(xs)
    h_span = max(ys) - min(ys)
    span = max(w_span, h_span, 1.0)
    return PartAnchor(cx, cy, span, 0.0)


def anchor_from_face(
    landmarks,
    w: int,
    h: int,
    part: BodyPart,
    q: QualifiedImage,
) -> PartAnchor | None:
    if part == BodyPart.EYES:
        left, right = q.left, q.right
        cx = (left[0] + right[0]) / 2.0
        cy = (left[1] + right[1]) / 2.0
        span = math.hypot(right[0] - left[0], right[1] - left[1])
        angle = math.atan2(right[1] - left[1], right[0] - left[0])
        return PartAnchor(cx, cy, max(span, 1.0), angle)

    if part == BodyPart.LIPS:
        pts = _lm_points(landmarks, LIP_IDX, w, h)
        anchor = _centroid_span_angle(pts)
        if anchor and q.left and q.right:
            angle = math.atan2(q.right[1] - q.left[1], q.right[0] - q.left[0])
            anchor.angle = angle
        return anchor

    if part == BodyPart.NOSE:
        pts = _lm_points(landmarks, NOSE_IDX, w, h)
        anchor = _centroid_span_angle(pts)
        if anchor and q.left and q.right:
            angle = math.atan2(q.right[1] - q.left[1], q.right[0] - q.left[0])
            anchor.angle = angle
            eye_cx = (q.left[0] + q.right[0]) / 2.0
            eye_cy = (q.left[1] + q.right[1]) / 2.0
            anchor.span = max(anchor.span, math.hypot(anchor.cx - eye_cx, anchor.cy - eye_cy) * 0.65)
        return anchor

    return None


def anchor_from_head(
    landmarks,
    w: int,
    h: int,
    q: QualifiedImage,
) -> PartAnchor | None:
    if q.head_oval:
        pts = list(q.head_oval)
    else:
        pts = _lm_points(landmarks, FACE_OVAL_IDX, w, h)
    anchor = _centroid_span_angle(pts)
    if anchor is None:
        return None
    left, right = q.left, q.right
    anchor.angle = math.atan2(right[1] - left[1], right[0] - left[0])
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    anchor.span = max(max(xs) - min(xs), max(ys) - min(ys), anchor.span)
    return anchor


def anchor_from_hands(
    hand_result: vision.HandLandmarkerResult,
    w: int,
    h: int,
    part: BodyPart,
) -> PartAnchor | None:
    if not hand_result.hand_landmarks:
        return None

    want_left = part == BodyPart.LEFT_HAND
    best: PartAnchor | None = None
    best_score = -1.0

    for i, hand_lms in enumerate(hand_result.hand_landmarks):
        handed = "Unknown"
        if hand_result.handedness and i < len(hand_result.handedness):
            cats = hand_result.handedness[i]
            if cats:
                handed = cats[0].category_name

        is_left = handed == "Left"
        if want_left != is_left:
            continue

        pts = [(lm.x * w, lm.y * h) for lm in hand_lms]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
        score = span * (hand_result.handedness[i][0].score if hand_result.handedness else 0.5)
        if score > best_score:
            best_score = score
            wrist, index = pts[0], pts[5] if len(pts) > 5 else pts[0]
            angle = math.atan2(index[1] - wrist[1], index[0] - wrist[0])
            best = PartAnchor(cx, cy, span, angle)

    return best


def detect_part_anchor(
    bgr: np.ndarray,
    q: QualifiedImage,
    part: BodyPart,
    face_lm: vision.FaceLandmarker,
    hand_lm: vision.HandLandmarker,
) -> PartAnchor | None:
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    mp_img = mp_image.Image(image_format=mp_image.ImageFormat.SRGB, data=rgb)

    if part in (BodyPart.RIGHT_HAND, BodyPart.LEFT_HAND):
        hres = hand_lm.detect(mp_img)
        anchor = anchor_from_hands(hres, w, h, part)
        if anchor:
            return anchor
        return None

    fres = face_lm.detect(mp_img)
    if not fres.face_landmarks:
        return None
    return anchor_from_face(fres.face_landmarks[0], w, h, part, q)


def align_closeup(
    bgr: np.ndarray,
    anchor: PartAnchor,
    part: BodyPart,
    target_frac: float | None = None,
) -> np.ndarray:
    """Center feature on canvas and scale up (cover 9:16)."""
    h, w = bgr.shape[:2]
    frac = target_frac if target_frac is not None else PART_TARGET_FRAC[part]
    target_px = min(CANVAS_W, CANVAS_H) * frac
    feature_scale = target_px / max(anchor.span, 1.0)
    sw, sh = w * feature_scale, h * feature_scale
    canvas_scale = max(CANVAS_W / sw, CANVAS_H / sh)
    s = feature_scale * canvas_scale

    cos_a = math.cos(-anchor.angle)
    sin_a = math.sin(-anchor.angle)

    t1 = np.array([[1, 0, -anchor.cx], [0, 1, -anchor.cy], [0, 0, 1]], dtype=np.float64)
    sc = np.array([[s, 0, 0], [0, s, 0], [0, 0, 1]], dtype=np.float64)
    rot = np.array([[cos_a, -sin_a, 0], [sin_a, cos_a, 0], [0, 0, 1]], dtype=np.float64)
    t2 = np.array([[1, 0, CENTER_X], [0, 1, CENTER_Y], [0, 0, 1]], dtype=np.float64)
    m = (t2 @ rot @ sc @ t1)[:2, :]

    return cv2.warpAffine(
        bgr, m, (CANVAS_W, CANVAS_H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def draw_renderable_still(
    deck: UniqueDeck,
    face_lm: vision.FaceLandmarker,
) -> tuple[QualifiedImage, np.ndarray] | None:
    """One deck pull per attempt — skip stills that cannot eye-lock."""
    while True:
        q = deck.draw()
        if q is None:
            return None
        if not has_eye_lock(q):
            hydrated = hydrate_qualified(q, face_lm)
            if hydrated is None:
                continue
            q = hydrated
        bgr = cv2.imread(q.path)
        if bgr is not None:
            return q, bgr


def anchor_for_still(
    bgr: np.ndarray,
    q: QualifiedImage,
    part: BodyPart,
    face_lm: vision.FaceLandmarker,
    hand_lm: vision.HandLandmarker,
) -> tuple[BodyPart, PartAnchor] | None:
    """Detect part on this still; fall back to eyes on the same image."""
    if part == BodyPart.HEAD_EXTREME:
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        mp_img = mp_image.Image(image_format=mp_image.ImageFormat.SRGB, data=rgb)
        if q.head_oval:
            anchor = anchor_from_head([], w, h, q)
        else:
            fres = face_lm.detect(mp_img)
            if not fres.face_landmarks:
                anchor = None
            else:
                anchor = anchor_from_head(fres.face_landmarks[0], w, h, q)
        if anchor:
            return part, anchor
        part = BodyPart.EYES

    anchor = detect_part_anchor(bgr, q, part, face_lm, hand_lm)
    if anchor:
        return part, anchor
    eyes = detect_part_anchor(bgr, q, BodyPart.EYES, face_lm, hand_lm)
    if eyes:
        return BodyPart.EYES, eyes
    return None


def head_zoom_frac(t: float, ramp_until: float, total_sec: float) -> float:
    if t < ramp_until:
        return HEAD_ZOOM_START_FRAC
    hold = max(total_sec - ramp_until, 1e-6)
    p = min(1.0, (t - ramp_until) / hold)
    return HEAD_ZOOM_START_FRAC + (HEAD_ZOOM_END_FRAC - HEAD_ZOOM_START_FRAC) * p


def render_closeup_reel(
    pool: list[QualifiedImage],
    durations: list[float],
    out_path: Path,
    seed: int,
    ramp_until: float = 30.0,
    iterations_path: Path | None = None,
) -> dict:
    n = len(durations)
    pool = filter_existing(pool)
    deck = UniqueDeck(pool, seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pad = max(4, len(str(n)))

    face_lm = create_face_landmarker(max_faces=1)
    hand_lm = create_hand_landmarker()
    total_sec = sum(durations)
    log_lines = [
        "# match-cut closeup reel iterations",
        f"# seed={seed}  frames={n}  ramp_until={ramp_until}s  total={total_sec:.1f}s",
        "# policy: each still used once — no repetition",
        "# phase1 (t<ramp): cycle right_hand,left_hand,lips,eyes,nose",
        f"# phase2 (t>={ramp_until}s): extreme head zoom {HEAD_ZOOM_START_FRAC}→{HEAD_ZOOM_END_FRAC}",
        "",
    ]
    t = 0.0
    render_durations: list[float] = []
    rendered = 0

    try:
        with tempfile.TemporaryDirectory(prefix="reel-closeup-") as tmp:
            tmp_path = Path(tmp)
            concat_lines: list[str] = []

            deck_exhausted = False
            for i, dur in enumerate(durations):
                post_ramp = t >= ramp_until - 1e-9
                zoom_frac: float | None = None
                want_part = (
                    BodyPart.HEAD_EXTREME if post_ramp
                    else PART_CYCLE[i % len(PART_CYCLE)]
                )
                if post_ramp:
                    zoom_frac = head_zoom_frac(t, ramp_until, total_sec)

                hit: tuple[QualifiedImage, np.ndarray] | None = None
                resolved: tuple[BodyPart, PartAnchor] | None = None
                while True:
                    hit = draw_renderable_still(deck, face_lm)
                    if hit is None:
                        deck_exhausted = True
                        print(
                            f"warn: deck exhausted at frame {i}/{n} "
                            f"({rendered} rendered) — stretching timing",
                            file=sys.stderr,
                        )
                        break
                    q, bgr = hit
                    resolved = anchor_for_still(bgr, q, want_part, face_lm, hand_lm)
                    if resolved is not None:
                        break
                if deck_exhausted:
                    break
                assert hit is not None and resolved is not None
                q, bgr = hit
                part, anchor = resolved
                frame = align_closeup(bgr, anchor, part, target_frac=zoom_frac)
                frame_path = tmp_path / f"frame_{rendered:0{pad}d}.png"
                cv2.imwrite(str(frame_path), frame)
                concat_lines.append(f"file '{frame_path}'")
                concat_lines.append(f"duration {dur:.6f}")
                render_durations.append(dur)

                fps = 1.0 / dur if dur > 0 else 0.0
                scale = zoom_frac if zoom_frac is not None else PART_TARGET_FRAC[part]
                phase = "post_ramp" if post_ramp else "ramp"
                log_lines.append(
                    f"frame={rendered:04d}  phase={phase}  part={part.value}  film={q.film_title!r}  "
                    f"image={Path(q.path).stem}  t={t:.3f}s  fps={fps:.2f}  "
                    f"span={anchor.span:.1f}px  scale_target={scale:.2f}"
                )
                t += dur
                rendered += 1

            if rendered == 0:
                raise RuntimeError("no renderable stills in pool")

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
        "mode": "closeup",
        "frames": rendered,
        "frames_requested": n,
        "duration_sec": sum(render_durations),
        "output": str(out_path),
        "iterations": str(iter_path),
        "pool_size": len(pool),
        "unique_stills": True,
        "stills_used": len(deck.used_paths),
        "part_cycle": [p.value for p in PART_CYCLE],
        "ramp_until_sec": ramp_until,
        "head_zoom_frac": [HEAD_ZOOM_START_FRAC, HEAD_ZOOM_END_FRAC],
        "seed": seed,
    }


def main() -> int:
    import argparse

    from render import DEFAULT_CACHE, DEFAULT_IMAGES, scan_qualified  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Close-up body-part reel (no text)")
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--pool",
        choices=("all", "qualified"),
        default="all",
        help="all=every film-grab still (no repeats); qualified=face-pass cache only",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "exports" / "reels" / "insta_reel_closeup_1-30_60s.mp4",
    )
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--start-rate", type=float, default=1.0)
    parser.add_argument("--end-rate", type=float, default=30.0)
    parser.add_argument(
        "--rate",
        type=float,
        default=None,
        metavar="N",
        help="Constant img/s (sets start=end=N, no crescendo). Capped at 30.",
    )
    parser.add_argument(
        "--ramp-until",
        type=float,
        default=30.0,
        help="Seconds to ramp 1→30 fps; after this, hold 30fps + extreme head zoom",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rescan", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--iterations", type=Path, default=None)
    args = parser.parse_args()

    if args.rate is not None:
        r = min(float(args.rate), 30.0)
        if float(args.rate) > 30.0:
            print(f"warn: --rate capped to 30 (got {args.rate})", file=sys.stderr)
        args.start_rate = r
        args.end_rate = r

    durations = compute_durations(args.duration, args.start_rate, args.end_rate, args.ramp_until)

    if args.rescan:
        scan_qualified(collect_images(args.images), args.cache, 8, True)

    pool = load_pool(args.images, args.cache, args.pool)
    durations, capped = cap_durations_for_unique_pool(durations, len(pool))
    if capped:
        print(
            f"warn: capped frames {len(durations)} to pool size {len(pool)} (no repetition)",
            file=sys.stderr,
        )

    print(
        f"closeup frames={len(durations)} duration={sum(durations):.2f}s "
        f"rate {args.start_rate}→{args.end_rate} until {args.ramp_until}s "
        f"pool={args.pool} unique={len(pool)}",
        file=sys.stderr,
    )

    pool = filter_existing(pool)
    if args.dry_run:
        print(json.dumps({
            "frames": len(durations),
            "pool_size": len(pool),
            "unique_stills": True,
        }, indent=2))
        return 0

    if not pool:
        print("error: no images in pool", file=sys.stderr)
        return 1

    report = render_closeup_reel(
        pool,
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