#!/usr/bin/env python3
"""Reproduce match-cut letterbox/stripe artifact reel from film-grab stills.

1 minute default, 2 images/sec ramping to 3 images/sec (linear).
Uses alignImageFull geometry + MediaPipe eyes + mpeg4 encode (like insta_reel).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import tempfile
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
DEFAULT_OUT = Path.home() / "Downloads" / "insta_reel_artifact_60s.mp4"

CANVAS_W, CANVAS_H = 540, 960
TARGET_EYE_DIST = 0.35
TARGET_EYE_Y = 0.4


def compute_durations(
    total_sec: float,
    start_rate: float,
    end_rate: float,
) -> list[float]:
    """Linear rate ramp: rate(t) = start + (end-start)*t/total."""
    durations: list[float] = []
    t = 0.0
    while t < total_sec - 1e-9:
        rate = start_rate + (end_rate - start_rate) * (t / total_sec)
        dt = 1.0 / max(rate, 1e-6)
        if t + dt > total_sec:
            dt = total_sec - t
        durations.append(dt)
        t += dt
    # Numeric drift fix
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


def eye_points_from_face(landmarks, w: int, h: int) -> tuple[tuple[float, float], tuple[float, float]] | None:
    # Face landmarker indices: outer eye corners
    li, ri = 33, 263
    if len(landmarks) <= max(li, ri):
        return None
    l, r = landmarks[li], landmarks[ri]
    return (l.x * w, l.y * h), (r.x * w, r.y * h)


def create_face_landmarker() -> vision.FaceLandmarker:
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(ensure_model())),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.4,
    )
    return vision.FaceLandmarker.create_from_options(options)


def fallback_eyes(w: int, h: int) -> tuple[tuple[float, float], tuple[float, float]]:
    """Center-third guess when no face — still produces letterbox artifacts."""
    cx, cy = w * 0.5, h * 0.38
    span = min(w, h) * 0.12
    return (cx - span, cy), (cx + span, cy)


def align_image_full(
    img_bgr: np.ndarray,
    left: tuple[float, float],
    right: tuple[float, float],
    cw: int = CANVAS_W,
    ch: int = CANVAS_H,
) -> np.ndarray:
    """Mirror match-cut alignImageFull — wide still in 9:16 → letterbox stripes."""
    h, w = img_bgr.shape[:2]
    ecx = (left[0] + right[0]) / 2.0
    ecy = (left[1] + right[1]) / 2.0
    dist = math.hypot(right[0] - left[0], right[1] - left[1])
    angle = math.atan2(right[1] - left[1], right[0] - left[0])

    target_dist = cw * TARGET_EYE_DIST
    target_cx, target_cy = cw / 2.0, ch * TARGET_EYE_Y

    eye_scale = target_dist / max(dist, 1.0)
    sw, sh = w * eye_scale, h * eye_scale
    fit = min(cw / sw, ch / sh, 1.0)
    final_scale = eye_scale * fit

    cos_a = math.cos(-angle)
    sin_a = math.sin(-angle)
    s = final_scale

    t1 = np.array([[1, 0, -ecx], [0, 1, -ecy], [0, 0, 1]], dtype=np.float64)
    sc = np.array([[s, 0, 0], [0, s, 0], [0, 0, 1]], dtype=np.float64)
    rot = np.array([[cos_a, -sin_a, 0], [sin_a, cos_a, 0], [0, 0, 1]], dtype=np.float64)
    t2 = np.array([[1, 0, target_cx], [0, 1, target_cy], [0, 0, 1]], dtype=np.float64)
    m3 = t2 @ rot @ sc @ t1
    m = m3[:2, :]

    # INTER_LINEAR keeps fringe stripes; mpeg4 will amplify
    return cv2.warpAffine(
        img_bgr,
        m,
        (cw, ch),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )


def render_reel(
    images: list[Path],
    durations: list[float],
    out_path: Path,
    seed: int = 42,
) -> dict:
    n = len(durations)
    if len(images) < n:
        raise RuntimeError(f"need {n} images, found {len(images)}")

    rng = random.Random(seed)
    picks = rng.sample(images, n)

    landmarker = create_face_landmarker()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reel-artifact-") as tmp:
        tmp_path = Path(tmp)
        concat_lines: list[str] = []
        stats = {"faces": 0, "fallback": 0}

        for i, (img_path, dur) in enumerate(zip(picks, durations)):
            frame_path = tmp_path / f"frame_{i:04d}.png"
            bgr = cv2.imread(str(img_path))
            if bgr is None:
                stats["fallback"] += 1
                bgr = np.zeros((800, 1920, 3), dtype=np.uint8)
                eyes = fallback_eyes(1920, 800)
            else:
                h, w = bgr.shape[:2]
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                mp_img = mp_image.Image(image_format=mp_image.ImageFormat.SRGB, data=rgb)
                res = landmarker.detect(mp_img)
                if res.face_landmarks:
                    eyes = eye_points_from_face(res.face_landmarks[0], w, h)
                    stats["faces"] += 1
                else:
                    eyes = fallback_eyes(w, h)
                    stats["fallback"] += 1
                if eyes is None:
                    eyes = fallback_eyes(w, h)
                    stats["fallback"] += 1

            aligned = align_image_full(bgr, eyes[0], eyes[1])
            cv2.imwrite(str(frame_path), aligned)
            concat_lines.append(f"file '{frame_path}'")
            concat_lines.append(f"duration {dur:.6f}")

        # concat demuxer requires last file repeated without duration
        concat_lines.append(f"file '{tmp_path / f'frame_{n-1:04d}.png'}'")
        concat_file = tmp_path / "concat.txt"
        concat_file.write_text("\n".join(concat_lines) + "\n")

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ]
        subprocess.run(cmd, check=True)

    landmarker.close()
    return {
        "frames": n,
        "duration_sec": sum(durations),
        "start_rate": 1 / durations[0] if durations else 0,
        "end_rate": 1 / durations[-1] if durations else 0,
        "output": str(out_path),
        **stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Artifact reel from film-grab stills")
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--start-rate", type=float, default=2.0, help="Images/sec at t=0")
    parser.add_argument("--end-rate", type=float, default=3.0, help="Images/sec at t=end")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    images = collect_images(args.images)
    durations = compute_durations(args.duration, args.start_rate, args.end_rate)
    print(
        f"frames={len(durations)} duration={sum(durations):.2f}s "
        f"rate {args.start_rate}→{args.end_rate} img/s images_pool={len(images)}",
        file=sys.stderr,
    )
    if args.dry_run:
        print(json.dumps({"frame_count": len(durations), "durations_sample": durations[:5]}, indent=2))
        return 0

    if len(images) < len(durations):
        print(f"error: need {len(durations)} images, have {len(images)}", file=sys.stderr)
        return 1

    report = render_reel(images, durations, args.output, seed=args.seed)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())