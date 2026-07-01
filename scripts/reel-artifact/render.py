#!/usr/bin/env python3
"""Artifact reel — single-person, visible eyes only; all eyes locked to same coords.

1 minute default, 2 images/sec → 3 images/sec (linear ramp).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision
from mediapipe.tasks.python.vision.core import image as mp_image

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_PATH = SCRIPT_DIR / "face_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
DEFAULT_IMAGES = ROOT / "assets" / "film-grab"
DEFAULT_CACHE = SCRIPT_DIR / "qualified.jsonl"
DEFAULT_OUT = Path.home() / "Downloads" / "insta_reel_artifact_60s.mp4"

CANVAS_W, CANVAS_H = 540, 960
# Fixed eye anchor — every frame lands here (match-cut defaults)
EYE_TARGET_X = CANVAS_W / 2.0
EYE_TARGET_Y = CANVAS_H * 0.4
EYE_TARGET_DIST = CANVAS_W * 0.35

LEFT_EYE_IDX = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161)
RIGHT_EYE_IDX = (362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384)


@dataclass
class QualifiedImage:
    path: str
    left: tuple[float, float]
    right: tuple[float, float]
    eye_dist: float


def compute_durations(total_sec: float, start_rate: float, end_rate: float) -> list[float]:
    durations: list[float] = []
    t = 0.0
    while t < total_sec - 1e-9:
        rate = start_rate + (end_rate - start_rate) * (t / total_sec)
        dt = 1.0 / max(rate, 1e-6)
        if t + dt > total_sec:
            dt = total_sec - t
        durations.append(dt)
        t += dt
    scale = total_sec / sum(durations)
    return [d * scale for d in durations]


def collect_images(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.jpg") if p.is_file())


def ensure_model() -> Path:
    if MODEL_PATH.exists():
        return MODEL_PATH
    import urllib.request

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading face model → {MODEL_PATH}", file=sys.stderr)
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


def create_face_landmarker(max_faces: int = 3) -> vision.FaceLandmarker:
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(ensure_model())),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=max_faces,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.FaceLandmarker.create_from_options(options)


def eye_center(landmarks, indices: tuple[int, ...], w: int, h: int) -> tuple[float, float] | None:
    xs, ys = [], []
    for idx in indices:
        if idx >= len(landmarks):
            return None
        lm = landmarks[idx]
        if not (0.0 <= lm.x <= 1.0 and 0.0 <= lm.y <= 1.0):
            return None
        xs.append(lm.x * w)
        ys.append(lm.y * h)
    if not xs:
        return None
    return sum(xs) / len(xs), sum(ys) / len(ys)


def validate_eyes(
    left: tuple[float, float],
    right: tuple[float, float],
    w: int,
    h: int,
) -> str | None:
    """Return None if valid, else rejection reason."""
    for x, y in (left, right):
        if x < 0 or x > w or y < 0 or y > h:
            return "eyes_out_of_bounds"

    dist = math.hypot(right[0] - left[0], right[1] - left[1])
    min_d = min(w, h) * 0.05
    max_d = max(w, h) * 0.55
    if dist < min_d:
        return "eyes_too_close"
    if dist > max_d:
        return "eyes_too_far"

    # Eyes should be roughly horizontal (both visible, not profile)
    angle_deg = abs(math.degrees(math.atan2(right[1] - left[1], right[0] - left[0])))
    if angle_deg > 25:
        return "eyes_not_level"

    # Left eye must be left of right eye
    if left[0] >= right[0]:
        return "eyes_swapped_or_profile"

    return None


def analyze_image(path: Path, landmarker: vision.FaceLandmarker) -> QualifiedImage | None:
    bgr = cv2.imread(str(path))
    if bgr is None:
        return None
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    mp_img = mp_image.Image(image_format=mp_image.ImageFormat.SRGB, data=rgb)
    res = landmarker.detect(mp_img)

    if not res.face_landmarks or len(res.face_landmarks) != 1:
        return None

    lm = res.face_landmarks[0]
    left = eye_center(lm, LEFT_EYE_IDX, w, h)
    right = eye_center(lm, RIGHT_EYE_IDX, w, h)
    if left is None or right is None:
        return None

    err = validate_eyes(left, right, w, h)
    if err:
        return None

    dist = math.hypot(right[0] - left[0], right[1] - left[1])
    return QualifiedImage(str(path), left, right, dist)


def scan_qualified(
    images: list[Path],
    cache_path: Path,
    workers: int,
    rescan: bool,
) -> list[QualifiedImage]:
    if cache_path.exists() and not rescan:
        loaded: list[QualifiedImage] = []
        for line in cache_path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            loaded.append(
                QualifiedImage(
                    d["path"],
                    tuple(d["left"]),
                    tuple(d["right"]),
                    d["eye_dist"],
                )
            )
        print(f"loaded {len(loaded)} qualified from cache", file=sys.stderr)
        return loaded

    qualified: list[QualifiedImage] = []
    print(f"scanning {len(images)} images for 1 face + visible eyes…", file=sys.stderr)
    landmarker = create_face_landmarker(max_faces=3)
    try:
        for i, path in enumerate(images, 1):
            if i % 200 == 0:
                print(f"  scanned {i}/{len(images)} qualified={len(qualified)}", file=sys.stderr)
            q = analyze_image(path, landmarker)
            if q:
                qualified.append(q)
    finally:
        landmarker.close()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w") as f:
        for q in qualified:
            f.write(json.dumps(asdict(q), separators=(",", ":")) + "\n")

    print(f"qualified: {len(qualified)} / {len(paths)}", file=sys.stderr)
    return qualified


def align_to_fixed_eyes(
    img_bgr: np.ndarray,
    left: tuple[float, float],
    right: tuple[float, float],
    fill: str = "fit",
) -> np.ndarray:
    """Eye-lock then fit (letterbox/trails) or cover (fill 9:16, crop sides)."""
    h, w = img_bgr.shape[:2]
    ecx = (left[0] + right[0]) / 2.0
    ecy = (left[1] + right[1]) / 2.0
    dist = math.hypot(right[0] - left[0], right[1] - left[1])
    angle = math.atan2(right[1] - left[1], right[0] - left[0])

    eye_scale = EYE_TARGET_DIST / max(dist, 1.0)
    sw, sh = w * eye_scale, h * eye_scale
    if fill == "cover":
        # Fill 9:16 — no letterbox, trails mostly gone
        canvas_scale = max(CANVAS_W / sw, CANVAS_H / sh)
    else:
        # Fit whole frame — letterbox stripes (artifact mode)
        canvas_scale = min(CANVAS_W / sw, CANVAS_H / sh, 1.0)
    s = eye_scale * canvas_scale

    cos_a = math.cos(-angle)
    sin_a = math.sin(-angle)

    t1 = np.array([[1, 0, -ecx], [0, 1, -ecy], [0, 0, 1]], dtype=np.float64)
    sc = np.array([[s, 0, 0], [0, s, 0], [0, 0, 1]], dtype=np.float64)
    rot = np.array([[cos_a, -sin_a, 0], [sin_a, cos_a, 0], [0, 0, 1]], dtype=np.float64)
    t2 = np.array([[1, 0, EYE_TARGET_X], [0, 1, EYE_TARGET_Y], [0, 0, 1]], dtype=np.float64)
    m = (t2 @ rot @ sc @ t1)[:2, :]

    return cv2.warpAffine(
        img_bgr,
        m,
        (CANVAS_W, CANVAS_H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )


def filter_existing(qualified: list[QualifiedImage]) -> list[QualifiedImage]:
    return [q for q in qualified if Path(q.path).is_file()]


def pick_frames(qualified: list[QualifiedImage], n: int, seed: int) -> list[QualifiedImage]:
    if not qualified:
        raise RuntimeError("no qualified images on disk")
    rng = random.Random(seed)
    if n <= len(qualified):
        return rng.sample(qualified, n)
    return rng.choices(qualified, k=n)


def render_reel(
    qualified: list[QualifiedImage],
    durations: list[float],
    out_path: Path,
    seed: int,
    fill: str = "fit",
) -> dict:
    n = len(durations)
    qualified = filter_existing(qualified)
    picks = pick_frames(qualified, n, seed)
    reused = n > len(qualified)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pad = max(4, len(str(n)))

    with tempfile.TemporaryDirectory(prefix="reel-artifact-") as tmp:
        tmp_path = Path(tmp)
        concat_lines: list[str] = []

        for i, (q, dur) in enumerate(zip(picks, durations)):
            bgr = cv2.imread(q.path)
            if bgr is None:
                raise RuntimeError(f"failed to read {q.path}")
            aligned = align_to_fixed_eyes(bgr, q.left, q.right, fill=fill)
            frame_path = tmp_path / f"frame_{i:0{pad}d}.png"
            cv2.imwrite(str(frame_path), aligned)
            concat_lines.append(f"file '{frame_path}'")
            concat_lines.append(f"duration {dur:.6f}")

        concat_lines.append(f"file '{tmp_path / f'frame_{n-1:0{pad}d}.png'}'")
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

    return {
        "frames": n,
        "duration_sec": sum(durations),
        "output": str(out_path),
        "eye_target": {"x": EYE_TARGET_X, "y": EYE_TARGET_Y, "dist_px": EYE_TARGET_DIST},
        "qualified_pool": len(qualified),
        "frames_reused": reused,
        "fill": fill,
        "seed": seed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Artifact reel — single face, fixed eye coords")
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--start-rate", type=float, default=2.0)
    parser.add_argument("--end-rate", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=int(__import__("os").environ.get("MATCHCUT_PARALLEL_JOBS", "8")))
    parser.add_argument("--rescan", action="store_true", help="Rebuild qualified cache")
    parser.add_argument("--select-only", action="store_true", help="Only scan/filter, no render")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--fill",
        choices=("fit", "cover"),
        default="fit",
        help="fit=letterbox trails (default); cover=fill 9:16 crop sides",
    )
    args = parser.parse_args()

    images = collect_images(args.images)
    durations = compute_durations(args.duration, args.start_rate, args.end_rate)
    need = len(durations)

    print(
        f"frames={need} duration={sum(durations):.2f}s "
        f"rate {args.start_rate}→{args.end_rate} pool={len(images)}",
        file=sys.stderr,
    )

    qualified = scan_qualified(images, args.cache, args.workers, args.rescan)

    if args.dry_run or args.select_only:
        print(json.dumps({
            "frame_count": need,
            "qualified": len(qualified),
            "eye_target": {"x": EYE_TARGET_X, "y": EYE_TARGET_Y},
            "cache": str(args.cache),
        }, indent=2))
        return 0 if len(qualified) >= need else 1

    qualified = filter_existing(qualified)
    if not qualified:
        print("error: no qualified images on disk", file=sys.stderr)
        return 1
    if len(qualified) < need:
        print(
            f"warn: need {need} frames, have {len(qualified)} unique — will reuse picks",
            file=sys.stderr,
        )

    report = render_reel(qualified, durations, args.output, args.seed, fill=args.fill)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())