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
DEFAULT_OUT = Path.home() / "Downloads" / "insta_reel_extend_12-24_60s.mp4"
DEFAULT_VJ_ITERATIONS = SCRIPT_DIR / "vj_iterations.txt"
TYPEWRITER_FONT = Path("/System/Library/Fonts/Supplemental/Courier New.ttf")
PHI = (1.0 + math.sqrt(5.0)) / 2.0

CANVAS_W, CANVAS_H = 540, 960
# Fixed eye anchor — every frame lands here (match-cut defaults)
EYE_TARGET_X = CANVAS_W / 2.0
EYE_TARGET_Y = CANVAS_H * 0.4
EYE_TARGET_DIST = CANVAS_W * 0.35

LEFT_EYE_IDX = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161)
RIGHT_EYE_IDX = (362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384)
FACE_OVAL_IDX = (
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109,
)
HEAD_MASK_EXPAND = 1.12  # keep a little hair/forehead inside the clear zone


@dataclass
class QualifiedImage:
    path: str
    left: tuple[float, float]
    right: tuple[float, float]
    eye_dist: float
    head_oval: tuple[tuple[float, float], ...] = ()
    film_slug: str = ""
    film_title: str = ""


@dataclass
class VjFrameParams:
    smear_saturation: float = 1.0
    smear_hue_shift: int = 0
    eye_dist_mult: float = 1.0
    film_title: str = ""
    fps: float = 12.0
    frame_index: int = 0
    time_sec: float = 0.0
    overlay: bool = True


def film_meta_from_path(path: str) -> tuple[str, str]:
    slug = Path(path).parent.name
    return slug, slug.replace("-", " ").title()


def random_vj_params(
    rng: random.Random,
    frame_index: int,
    time_sec: float,
    fps: float,
    film_title: str,
) -> VjFrameParams:
    big_eyes = rng.random() < 0.28
    return VjFrameParams(
        smear_saturation=rng.uniform(0.45, 2.35),
        smear_hue_shift=rng.randint(-14, 14),
        eye_dist_mult=rng.uniform(1.55, 2.75) if big_eyes else 1.0,
        film_title=film_title,
        fps=fps,
        frame_index=frame_index,
        time_sec=time_sec,
        overlay=True,
    )


def vj_math_lines(frame_index: int, fps: float, time_sec: float) -> tuple[str, str]:
    phi_n = frame_index * PHI
    harmonic = math.sin(frame_index * math.pi / 12.0)
    line1 = f"{fps:.1f} fps"
    line2 = f"phi*{frame_index:04d}={phi_n:.3f} sin={harmonic:+.3f} T={time_sec:.3f}s"
    return line1, line2


def compute_durations(
    total_sec: float,
    start_rate: float,
    end_rate: float,
    ramp_until: float | None = None,
) -> list[float]:
    """Linear ramp start→end over ramp_until (default: total_sec), then hold end_rate."""
    ramp_sec = total_sec if ramp_until is None else min(ramp_until, total_sec)
    durations: list[float] = []
    t = 0.0
    while t < total_sec - 1e-9:
        if t < ramp_sec:
            rate = start_rate + (end_rate - start_rate) * (t / ramp_sec)
        else:
            rate = end_rate
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


def head_oval_points(landmarks, w: int, h: int) -> tuple[tuple[float, float], ...]:
    pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in FACE_OVAL_IDX if i < len(landmarks)]
    if len(pts) < 3:
        return ()
    arr = np.array(pts, dtype=np.float32)
    hull = cv2.convexHull(arr)
    return tuple((float(p[0][0]), float(p[0][1])) for p in hull)


def expand_oval_from_eyes(
    oval: tuple[tuple[float, float], ...],
    left: tuple[float, float],
    right: tuple[float, float],
    scale: float = HEAD_MASK_EXPAND,
) -> tuple[tuple[float, float], ...]:
    if not oval:
        return oval
    ecx = (left[0] + right[0]) / 2.0
    ecy = (left[1] + right[1]) / 2.0
    return tuple(
        (ecx + (x - ecx) * scale, ecy + (y - ecy) * scale) for x, y in oval
    )


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
    oval = expand_oval_from_eyes(head_oval_points(lm, w, h), left, right)
    slug, title = film_meta_from_path(str(path))
    return QualifiedImage(str(path), left, right, dist, oval, slug, title)


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
            oval = tuple(tuple(p) for p in d["head_oval"]) if d.get("head_oval") else ()
            slug, title = d.get("film_slug"), d.get("film_title")
            if not slug or not title:
                slug, title = film_meta_from_path(d["path"])
            loaded.append(
                QualifiedImage(
                    d["path"],
                    tuple(d["left"]),
                    tuple(d["right"]),
                    d["eye_dist"],
                    oval,
                    slug,
                    title,
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

    print(f"qualified: {len(qualified)} / {len(images)}", file=sys.stderr)
    return qualified


def warp_head_mask(
    head_oval: tuple[tuple[float, float], ...],
    matrix: np.ndarray,
) -> np.ndarray:
    """Face-oval polygon on canvas after the same eye-lock warp."""
    if not head_oval:
        return np.zeros((CANVAS_H, CANVAS_W), dtype=bool)
    pts = np.array(head_oval, dtype=np.float32).reshape(-1, 1, 2)
    warped = cv2.transform(pts, matrix[:2, :])
    mask = np.zeros((CANVAS_H, CANVAS_W), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.round(warped).astype(np.int32), 255)
    return mask.astype(bool)


def smear_outside_mask(rgb: np.ndarray, region: np.ndarray) -> np.ndarray:
    """Smear boundary colors into every pixel outside region (head silhouette)."""
    if not region.any():
        return rgb

    out = rgb.copy()
    h, w = out.shape[:2]
    filled = region.copy()
    y_grid = np.arange(h)[:, None]
    x_grid = np.arange(w)[None, :]

    col_has = region.any(axis=0)
    first_y = np.argmax(region, axis=0)
    last_y = h - 1 - np.argmax(region[::-1, :], axis=0)
    edge_top = out[first_y, np.arange(w)]
    edge_bot = out[last_y, np.arange(w)]
    for c in range(3):
        plane = out[:, :, c]
        top_c = edge_top[:, c][None, :]
        bot_c = edge_bot[:, c][None, :]
        top_mask = (y_grid < first_y[None, :]) & col_has[None, :]
        bot_mask = (y_grid > last_y[None, :]) & col_has[None, :]
        plane[top_mask] = np.broadcast_to(top_c, (h, w))[top_mask]
        plane[bot_mask] = np.broadcast_to(bot_c, (h, w))[bot_mask]
    filled |= (y_grid < first_y[None, :]) & col_has[None, :]
    filled |= (y_grid > last_y[None, :]) & col_has[None, :]

    active = filled
    row_has = active.any(axis=1)
    first_x = np.argmax(active, axis=1)
    last_x = w - 1 - np.argmax(active[:, ::-1], axis=1)
    for c in range(3):
        plane = out[:, :, c]
        left_c = out[np.arange(h), first_x, c][:, None]
        right_c = out[np.arange(h), last_x, c][:, None]
        left_mask = (x_grid < first_x[:, None]) & row_has[:, None]
        right_mask = (x_grid > last_x[:, None]) & row_has[:, None]
        plane[left_mask] = np.broadcast_to(left_c, (h, w))[left_mask]
        plane[right_mask] = np.broadcast_to(right_c, (h, w))[right_mask]

    return out


def tint_smear_region(
    rgb: np.ndarray,
    head_mask: np.ndarray,
    saturation: float,
    hue_shift: int,
) -> np.ndarray:
    if saturation == 1.0 and hue_shift == 0:
        return rgb
    outside = ~head_mask
    if not outside.any():
        return rgb
    hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[outside, 1] = np.clip(hsv[outside, 1] * saturation, 0, 255)
    if hue_shift:
        hsv[outside, 0] = (hsv[outside, 0] + hue_shift) % 180
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def fill_outside_head(
    bgra: np.ndarray,
    head_mask: np.ndarray,
    smear_saturation: float = 1.0,
    smear_hue_shift: int = 0,
) -> np.ndarray:
    """Keep the head clear; smear colors into everything else on the 9:16 canvas."""
    opaque = bgra[:, :, 3] > 0
    if not opaque.any() and not head_mask.any():
        return bgra

    rgb = bgra[:, :, :3].copy()
    smeared = smear_outside_mask(rgb, head_mask)
    keep = head_mask & opaque
    rgb[~keep] = smeared[~keep]
    rgb = tint_smear_region(rgb, head_mask, smear_saturation, smear_hue_shift)

    out = bgra.copy()
    out[:, :, :3] = rgb
    out[:, :, 3] = 255
    return out


def draw_typewriter_overlay(bgr: np.ndarray, params: VjFrameParams) -> np.ndarray:
    if not params.overlay or not params.film_title:
        return bgr
    from PIL import Image, ImageDraw, ImageFont

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil)
    font_path = TYPEWRITER_FONT if TYPEWRITER_FONT.exists() else None
    title_font = ImageFont.truetype(str(font_path), 22) if font_path else ImageFont.load_default()
    meta_font = ImageFont.truetype(str(font_path), 16) if font_path else ImageFont.load_default()
    w, h = pil.size
    margin = 14
    fps_line, math_line = vj_math_lines(params.frame_index, params.fps, params.time_sec)

    draw.text((margin, h - margin - 52), params.film_title.upper(), fill=(235, 235, 220), font=title_font)
    tw = draw.textlength(math_line, font=meta_font)
    draw.text((w - margin - tw, h - margin - 36), fps_line, fill=(220, 220, 200), font=meta_font)
    draw.text((w - margin - tw, h - margin - 16), math_line, fill=(200, 200, 180), font=meta_font)

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def resolve_head_oval(
    q: QualifiedImage,
    landmarker: vision.FaceLandmarker | None,
) -> tuple[tuple[float, float], ...]:
    if q.head_oval:
        return q.head_oval
    if landmarker is None:
        return ()
    bgr = cv2.imread(q.path)
    if bgr is None:
        return ()
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    mp_img = mp_image.Image(image_format=mp_image.ImageFormat.SRGB, data=rgb)
    res = landmarker.detect(mp_img)
    if not res.face_landmarks:
        return ()
    return expand_oval_from_eyes(
        head_oval_points(res.face_landmarks[0], w, h), q.left, q.right,
    )


def align_to_fixed_eyes(
    img_bgr: np.ndarray,
    left: tuple[float, float],
    right: tuple[float, float],
    fill: str = "extend",
    head_oval: tuple[tuple[float, float], ...] = (),
    vj: VjFrameParams | None = None,
) -> np.ndarray:
    """Eye-lock, fit whole frame, smear colors outside the head region."""
    h, w = img_bgr.shape[:2]
    ecx = (left[0] + right[0]) / 2.0
    ecy = (left[1] + right[1]) / 2.0
    dist = math.hypot(right[0] - left[0], right[1] - left[1])
    angle = math.atan2(right[1] - left[1], right[0] - left[0])

    eye_mult = vj.eye_dist_mult if vj else 1.0
    eye_scale = (EYE_TARGET_DIST * eye_mult) / max(dist, 1.0)
    sw, sh = w * eye_scale, h * eye_scale
    if fill == "cover":
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
        bgra,
        m,
        (CANVAS_W, CANVAS_H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )

    if fill in ("extend", "fit", "color"):
        head_mask = warp_head_mask(head_oval, m)
        sat = vj.smear_saturation if vj else 1.0
        hue = vj.smear_hue_shift if vj else 0
        warped = fill_outside_head(warped, head_mask, sat, hue)

    out = cv2.cvtColor(warped, cv2.COLOR_BGRA2BGR)
    if vj:
        out = draw_typewriter_overlay(out, vj)
    return out


def filter_existing(qualified: list[QualifiedImage]) -> list[QualifiedImage]:
    return [q for q in qualified if Path(q.path).is_file()]


def load_pool(
    images_root: Path,
    cache_path: Path,
    mode: str = "all",
) -> list[QualifiedImage]:
    """Load render pool. mode=all → every on-disk still (3000); qualified → cache pass only."""
    cache_by_path: dict[str, QualifiedImage] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            oval = tuple(tuple(p) for p in d["head_oval"]) if d.get("head_oval") else ()
            slug, title = d.get("film_slug"), d.get("film_title")
            if not slug or not title:
                slug, title = film_meta_from_path(d["path"])
            cache_by_path[d["path"]] = QualifiedImage(
                d["path"], tuple(d["left"]), tuple(d["right"]), d["eye_dist"], oval, slug, title,
            )

    if mode == "qualified":
        return filter_existing(list(cache_by_path.values()))

    pool: list[QualifiedImage] = []
    for path in collect_images(images_root):
        p = str(path)
        if p in cache_by_path:
            pool.append(cache_by_path[p])
        else:
            slug, title = film_meta_from_path(p)
            pool.append(QualifiedImage(p, (0.0, 0.0), (0.0, 0.0), 0.0, (), slug, title))
    return filter_existing(pool)


def has_eye_lock(q: QualifiedImage) -> bool:
    return q.eye_dist > 0 and q.left != (0.0, 0.0) and q.right != (0.0, 0.0)


def hydrate_qualified(
    q: QualifiedImage,
    landmarker: vision.FaceLandmarker,
) -> QualifiedImage | None:
    if has_eye_lock(q) and q.head_oval:
        return q
    fresh = analyze_image(Path(q.path), landmarker)
    return fresh


def cap_durations_for_unique_pool(
    durations: list[float],
    pool_size: int,
) -> tuple[list[float], bool]:
    """Never repeat stills: cap frame count to pool size, stretch timing to keep duration."""
    if len(durations) <= pool_size:
        return durations, False
    capped = durations[:pool_size]
    total = sum(durations)
    scale = total / sum(capped)
    return [d * scale for d in capped], True


class UniqueDeck:
    """Shuffled pool — each image path used at most once per render."""

    def __init__(self, items: list[QualifiedImage], seed: int) -> None:
        self._items = items[:]
        random.Random(seed).shuffle(self._items)
        self._idx = 0
        self.used_paths: set[str] = set()

    def __len__(self) -> int:
        return len(self._items) - self._idx

    def draw(self) -> QualifiedImage | None:
        while self._idx < len(self._items):
            q = self._items[self._idx]
            self._idx += 1
            if q.path in self.used_paths:
                continue
            self.used_paths.add(q.path)
            return q
        return None


def iteration_line(
    frame_index: int,
    q: QualifiedImage,
    params: VjFrameParams | None,
    duration: float,
) -> str:
    stem = Path(q.path).stem
    if params is None:
        return (
            f"frame={frame_index:04d}  film={q.film_title!r}  image={stem}  "
            f"dur={duration:.4f}s  eyes=1.00x  sat=1.00"
        )
    _, math_line = vj_math_lines(params.frame_index, params.fps, params.time_sec)
    return (
        f"frame={frame_index:04d}  film={q.film_title!r}  image={stem}  "
        f"t={params.time_sec:.3f}s  fps={params.fps:.2f}  dur={duration:.4f}s  "
        f"sat={params.smear_saturation:.2f}  hue={params.smear_hue_shift:+d}  "
        f"eyes={params.eye_dist_mult:.2f}x  {math_line}"
    )


def write_vj_pool_iterations(
    path: Path,
    qualified: list[QualifiedImage],
    frame_count: int,
    durations: list[float],
) -> None:
    lines = [
        "# match-cut VJ pool — qualified iterations (filter pass)",
        "# filter: 1 face, visible level eyes, on-disk film-grab still",
        "# render variations when --vj:",
        "#   A smear_saturation random [0.45, 2.35] + hue shift [-14, 14]",
        "#   B big_eyes random 28% @ [1.55, 2.75]x inter-eye scale",
        "#   C typewriter overlay: film title + fps + phi/sin/T math",
        "# policy: each still used once — no repetition",
        f"# pool={len(qualified)}  reel_frames={frame_count}  reel_duration={sum(durations):.2f}s",
        "",
        "[qualified_pool]",
    ]
    for i, q in enumerate(qualified):
        lines.append(
            f"pool={i:04d}  film={q.film_title!r}  slug={q.film_slug}  "
            f"image={Path(q.path).name}  eye_dist={q.eye_dist:.1f}px"
        )
    lines.extend(["", "[reel_timeline_slots]", ""])
    t = 0.0
    for i, dur in enumerate(durations):
        fps = 1.0 / dur if dur > 0 else 0.0
        lines.append(f"slot={i:04d}  t={t:.3f}s  dur={dur:.4f}s  fps={fps:.2f}")
        t += dur
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def write_vj_render_iterations(
    path: Path,
    picks: list[QualifiedImage],
    params_list: list[VjFrameParams | None],
    durations: list[float],
    seed: int,
    vj: bool,
) -> None:
    lines = [
        "# match-cut VJ render iterations",
        f"# seed={seed}  vj={'on' if vj else 'off'}  frames={len(picks)}",
        "# policy: each still used once — no repetition",
        "# variations: A=saturate_smear B=big_eyes C=typewriter_overlay",
        "",
    ]
    t = 0.0
    for i, (q, dur) in enumerate(zip(picks, durations)):
        p = params_list[i] if i < len(params_list) else None
        if p and p.time_sec == 0.0 and t > 0:
            p = VjFrameParams(**{**p.__dict__, "time_sec": t})
        lines.append(iteration_line(i, q, p, dur))
        t += dur
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def pick_frames(pool: list[QualifiedImage], n: int, seed: int) -> list[QualifiedImage]:
    """Sample n unique stills — repetition is never allowed."""
    if not pool:
        raise RuntimeError("no images in pool")
    if n > len(pool):
        raise RuntimeError(
            f"need {n} unique frames but pool has {len(pool)} — "
            "lower --duration / --end-rate or use --pool all",
        )
    return random.Random(seed).sample(pool, n)


def draw_renderable(
    deck: UniqueDeck,
    landmarker: vision.FaceLandmarker,
) -> QualifiedImage | None:
    """Consume stills until one passes single-face eye lock — each path at most once."""
    while True:
        q = deck.draw()
        if q is None:
            return None
        if has_eye_lock(q):
            return q
        hydrated = hydrate_qualified(q, landmarker)
        if hydrated is not None:
            return hydrated


def render_reel(
    qualified: list[QualifiedImage],
    durations: list[float],
    out_path: Path,
    seed: int,
    fill: str = "extend",
    vj: bool = False,
    vj_iterations_path: Path | None = None,
) -> dict:
    n = len(durations)
    pool = filter_existing(qualified)
    deck = UniqueDeck(pool, seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pad = max(4, len(str(n)))
    rng = random.Random(seed + 17)
    picks: list[QualifiedImage] = []
    render_durations: list[float] = []
    vj_params: list[VjFrameParams | None] = []
    t = 0.0

    landmarker = create_face_landmarker(max_faces=1)
    oval_cache: dict[str, tuple[tuple[float, float], ...]] = {}

    try:
        with tempfile.TemporaryDirectory(prefix="reel-artifact-") as tmp:
            tmp_path = Path(tmp)
            concat_lines: list[str] = []

            deck_exhausted = False
            for i, dur in enumerate(durations):
                q: QualifiedImage | None = None
                bgr = None
                while True:
                    q = draw_renderable(deck, landmarker)
                    if q is None:
                        deck_exhausted = True
                        print(
                            f"warn: deck exhausted at frame {i}/{n} "
                            f"({len(picks)} renderable) — stretching timing",
                            file=sys.stderr,
                        )
                        break
                    bgr = cv2.imread(q.path)
                    if bgr is not None:
                        break
                if deck_exhausted:
                    break
                assert q is not None and bgr is not None
                fps = 1.0 / dur if dur > 0 else 0.0
                params = (
                    random_vj_params(rng, len(picks), t, fps, q.film_title) if vj else None
                )
                picks.append(q)
                render_durations.append(dur)
                vj_params.append(params)
                if q.path not in oval_cache:
                    oval_cache[q.path] = resolve_head_oval(q, landmarker)
                aligned = align_to_fixed_eyes(
                    bgr, q.left, q.right, fill=fill,
                    head_oval=oval_cache[q.path], vj=params,
                )
                t += dur
                frame_path = tmp_path / f"frame_{len(picks)-1:0{pad}d}.png"
                cv2.imwrite(str(frame_path), aligned)
                concat_lines.append(f"file '{frame_path}'")
                concat_lines.append(f"duration {dur:.6f}")

            if not picks:
                raise RuntimeError("no renderable stills in pool")

            rendered = len(picks)
            total_sec = sum(durations)
            if rendered < n:
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
        landmarker.close()

    iter_path = vj_iterations_path or (out_path.parent / f"{out_path.stem}_iterations.txt")
    write_vj_render_iterations(iter_path, picks, vj_params, render_durations, seed, vj)

    return {
        "frames": len(picks),
        "frames_requested": n,
        "duration_sec": sum(render_durations),
        "output": str(out_path),
        "vj_iterations": str(iter_path),
        "eye_target": {"x": EYE_TARGET_X, "y": EYE_TARGET_Y, "dist_px": EYE_TARGET_DIST},
        "pool_size": len(pool),
        "stills_used": len(deck.used_paths),
        "unique_stills": True,
        "fill": fill,
        "vj": vj,
        "seed": seed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Artifact reel — single face, fixed eye coords")
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--start-rate", type=float, default=12.0)
    parser.add_argument("--end-rate", type=float, default=24.0)
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
        help="Seconds to ramp start-rate→end-rate, then hold end-rate (default 30)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=int(__import__("os").environ.get("MATCHCUT_PARALLEL_JOBS", "8")))
    parser.add_argument("--rescan", action="store_true", help="Rebuild qualified cache")
    parser.add_argument("--select-only", action="store_true", help="Only scan/filter, no render")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--fill",
        choices=("extend", "fit", "color", "black", "cover"),
        default="extend",
        help="extend=smear colors outside head to fill 9:16 (default); black=letterbox; cover=crop",
    )
    parser.add_argument(
        "--fill-debug",
        type=Path,
        metavar="IMAGE",
        help="Render one frame PNG with extend fill (qualified image path or stem)",
    )
    parser.add_argument(
        "--vj",
        action="store_true",
        help="VJ mode: random smear saturation, big eyes, typewriter overlays",
    )
    parser.add_argument(
        "--vj-iterations",
        type=Path,
        default=None,
        help="Write iteration manifest (default: scripts/reel-artifact/vj_iterations.txt or beside output)",
    )
    parser.add_argument(
        "--pool",
        choices=("all", "qualified"),
        default="all",
        help="all=every film-grab still (no repeats); qualified=face-pass cache only",
    )
    args = parser.parse_args()

    if args.rate is not None:
        r = min(float(args.rate), 30.0)
        if float(args.rate) > 30.0:
            print(f"warn: --rate capped to 30 (got {args.rate})", file=sys.stderr)
        args.start_rate = r
        args.end_rate = r

    images = collect_images(args.images)
    durations = compute_durations(
        args.duration, args.start_rate, args.end_rate, args.ramp_until,
    )

    if args.rescan:
        scan_qualified(images, args.cache, args.workers, True)

    pool = load_pool(args.images, args.cache, args.pool)
    durations, capped = cap_durations_for_unique_pool(durations, len(pool))
    if capped:
        print(
            f"warn: capped frames {len(durations)} to pool size {len(pool)} (no repetition)",
            file=sys.stderr,
        )
    need = len(durations)

    print(
        f"frames={need} duration={sum(durations):.2f}s "
        f"rate {args.start_rate}→{args.end_rate} until {args.ramp_until}s "
        f"pool={args.pool} unique={len(pool)}",
        file=sys.stderr,
    )

    qualified = pool if args.pool == "all" else scan_qualified(images, args.cache, args.workers, False)

    if args.fill_debug is not None:
        qualified = filter_existing(qualified)
        needle = str(args.fill_debug)
        match = next(
            (q for q in qualified if needle in q.path or Path(q.path).stem == needle),
            None,
        )
        if match is None:
            print(f"error: no qualified image matching {args.fill_debug}", file=sys.stderr)
            return 1
        bgr = cv2.imread(match.path)
        if bgr is None:
            print(f"error: failed to read {match.path}", file=sys.stderr)
            return 1
        landmarker = create_face_landmarker(max_faces=1)
        try:
            oval = resolve_head_oval(match, landmarker)
            vj_params = (
                random_vj_params(random.Random(args.seed), 0, 0.0, 12.0, match.film_title)
                if args.vj
                else None
            )
            out = align_to_fixed_eyes(
                bgr, match.left, match.right, fill=args.fill,
                head_oval=oval, vj=vj_params,
            )
        finally:
            landmarker.close()
        out_path = Path.home() / "Downloads" / f"fill_debug_{Path(match.path).stem}.png"
        cv2.imwrite(str(out_path), out)
        print(json.dumps({"output": str(out_path), "source": match.path}, indent=2))
        return 0

    iter_path = args.vj_iterations or DEFAULT_VJ_ITERATIONS

    if args.dry_run or args.select_only:
        qualified_existing = filter_existing(qualified)
        write_vj_pool_iterations(iter_path, qualified_existing, need, durations)
        print(json.dumps({
            "frame_count": need,
            "qualified": len(qualified_existing),
            "eye_target": {"x": EYE_TARGET_X, "y": EYE_TARGET_Y},
            "cache": str(args.cache),
            "vj_iterations": str(iter_path),
            "vj_variations": {
                "A": "smear_saturation [0.45, 2.35] + hue [-14, 14]",
                "B": "big_eyes 28% @ [1.55, 2.75]x",
                "C": "typewriter film_title + fps + phi/sin/T",
            },
        }, indent=2))
        return 0 if len(qualified_existing) >= need else 1

    pool = filter_existing(qualified)
    if not pool:
        print("error: no images in pool", file=sys.stderr)
        return 1

    report = render_reel(
        pool,
        durations,
        args.output,
        args.seed,
        fill=args.fill,
        vj=args.vj,
        vj_iterations_path=args.vj_iterations,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())