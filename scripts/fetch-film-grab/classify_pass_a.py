#!/usr/bin/env python3
"""Pass A — local MediaPipe labels for every film-grab still (keep-all, additive).

Writes/merges assets/film-grab/classifications.jsonl. Never deletes images.
Does not set has_kiss (Pass C / VL). Records n_faces, eye geometry, lips/hands,
and multi-face mouth-to-mouth distance (Hall intimate bands → kiss_geo).

Bands (mouth_dist_norm = mouth_dist / mean eye_dist):
  kiss_contact ≤0.5 | kiss_imminent ≤1.2 (kiss_geo) | intimate_far ≤2.4 | reject
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision
from mediapipe.tasks.python.vision.core import image as mp_image

ROOT = Path(__file__).resolve().parents[2]
REEL = ROOT / "scripts" / "reel-artifact"
DEFAULT_IMAGES = ROOT / "assets" / "film-grab"
DEFAULT_OUT = DEFAULT_IMAGES / "classifications.jsonl"
FACE_MODEL = REEL / "face_landmarker.task"
HAND_MODEL = REEL / "hand_landmarker.task"

LEFT_EYE_IDX = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161)
RIGHT_EYE_IDX = (362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384)
LIP_IDX = (
    61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 308,
    324, 318, 402, 317, 14, 87, 178, 88, 95,
)
# Mouth center: outer corners + upper/lower lip mid (MediaPipe FaceMesh)
MOUTH_CENTER_IDX = (61, 291, 0, 17, 13, 14)

# Hall intimate-close mapped to mouth_dist / mean(eye_dist); see plan §2
TAU_CONTACT = 0.5       # ~3 cm — kiss_strict / contact
TAU_IMMINENT = 1.2      # ~8 cm — kiss_geo (contact + future kiss)
TAU_INTIMATE_FAR = 2.4  # ~15 cm — beyond close intimate → reject

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


def ensure_model(path: Path, url: str) -> Path:
    if path.exists():
        return path
    import urllib.request

    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {path.name}…", file=sys.stderr)
    urllib.request.urlretrieve(url, path)
    return path


def load_classifications(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        key = d.get("image_id") or d.get("sha256")
        if key:
            out[key] = d
    return out


def write_classifications(path: Path, by_id: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(by_id.values(), key=lambda r: r.get("image_id", ""))
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")


def eye_center(landmarks, indices: tuple[int, ...], w: int, h: int) -> tuple[float, float] | None:
    xs, ys = [], []
    for idx in indices:
        if idx >= len(landmarks):
            return None
        lm = landmarks[idx]
        xs.append(lm.x * w)
        ys.append(lm.y * h)
    if not xs:
        return None
    return sum(xs) / len(xs), sum(ys) / len(ys)


def lip_span(landmarks, w: int, h: int) -> float | None:
    pts = []
    for idx in LIP_IDX:
        if idx >= len(landmarks):
            continue
        lm = landmarks[idx]
        pts.append((lm.x * w, lm.y * h))
    if len(pts) < 4:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def mouth_center(landmarks, w: int, h: int) -> tuple[float, float] | None:
    pts = []
    for idx in MOUTH_CENTER_IDX:
        if idx >= len(landmarks):
            continue
        lm = landmarks[idx]
        pts.append((lm.x * w, lm.y * h))
    if len(pts) < 2:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def face_eye_dist(landmarks, w: int, h: int) -> float | None:
    left = eye_center(landmarks, LEFT_EYE_IDX, w, h)
    right = eye_center(landmarks, RIGHT_EYE_IDX, w, h)
    if not left or not right:
        return None
    return math.hypot(right[0] - left[0], right[1] - left[1])


def mouth_pair_metrics(
    face_landmarks_list,
    w: int,
    h: int,
) -> dict:
    """Min mouth-to-mouth distance across face pairs; Hall-based bands."""
    mouths: list[tuple[float, float]] = []
    eye_dists: list[float] = []
    for lm in face_landmarks_list:
        mc = mouth_center(lm, w, h)
        ed = face_eye_dist(lm, w, h)
        if mc is None or ed is None or ed < 1e-3:
            continue
        mouths.append(mc)
        eye_dists.append(ed)

    out: dict = {
        "mouth_dist_min": None,
        "mouth_dist_norm": None,
        "mouth_band": None,
        "mouth_pair_indices": None,
        "kiss_geo": False,
        "kiss_strict": False,
    }
    if len(mouths) < 2:
        return out

    best_d = float("inf")
    best_ij = (0, 1)
    best_scale = 1.0
    for i in range(len(mouths)):
        for j in range(i + 1, len(mouths)):
            d = math.hypot(mouths[i][0] - mouths[j][0], mouths[i][1] - mouths[j][1])
            scale = (eye_dists[i] + eye_dists[j]) / 2.0
            if d < best_d:
                best_d = d
                best_ij = (i, j)
                best_scale = scale

    norm = best_d / max(best_scale, 1e-6)
    if norm <= TAU_CONTACT:
        band = "kiss_contact"
    elif norm <= TAU_IMMINENT:
        band = "kiss_imminent"
    elif norm <= TAU_INTIMATE_FAR:
        band = "intimate_far"
    else:
        band = "reject_kiss"

    out["mouth_dist_min"] = round(best_d, 2)
    out["mouth_dist_norm"] = round(norm, 4)
    out["mouth_band"] = band
    out["mouth_pair_indices"] = list(best_ij)
    out["kiss_strict"] = band == "kiss_contact"
    out["kiss_geo"] = band in ("kiss_contact", "kiss_imminent")
    return out


def collect_images(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.jpg") if p.is_file() and p.parent != root)


def classify_one(
    path: Path,
    root: Path,
    face_lm: vision.FaceLandmarker,
    hand_lm: vision.HandLandmarker | None,
) -> dict:
    rel = path.relative_to(root)
    image_id = str(rel).replace("\\", "/")
    raw = path.read_bytes()
    sha = __import__("hashlib").sha256(raw).hexdigest()
    bgr = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    now = datetime.now(timezone.utc).isoformat()

    base = {
        "image_id": image_id,
        "sha256": sha,
        "path": str(path.resolve()),
        "film_slug": path.parent.name,
        "filename": path.name,
        "source": "mediapipe",
        "model": "face_landmarker.task+hand_landmarker.task",
        "updated_at": now,
        "confidence": 1.0,
        "labels": {
            "n_faces": 0,
            "has_kiss": None,  # Pass C only
            "closeup": False,
            "lips_visible": False,
            "paysage": False,
            "body_parts": [],
            "eye_dist": None,
            "eyes_level": None,
            "n_hands": 0,
        },
    }

    if bgr is None:
        base["labels"]["error"] = "imread_failed"
        base["confidence"] = 0.0
        return base

    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    mp_img = mp_image.Image(image_format=mp_image.ImageFormat.SRGB, data=rgb)

    fres = face_lm.detect(mp_img)
    n_faces = len(fres.face_landmarks) if fres.face_landmarks else 0
    labels = base["labels"]
    labels["n_faces"] = n_faces
    labels["paysage"] = n_faces == 0

    body: list[str] = []
    if n_faces >= 1:
        lm = fres.face_landmarks[0]
        left = eye_center(lm, LEFT_EYE_IDX, w, h)
        right = eye_center(lm, RIGHT_EYE_IDX, w, h)
        if left and right:
            dist = math.hypot(right[0] - left[0], right[1] - left[1])
            labels["eye_dist"] = round(dist, 2)
            angle = abs(math.degrees(math.atan2(right[1] - left[1], right[0] - left[0])))
            labels["eyes_level"] = angle <= 25
            # big face on frame → closeup heuristic
            labels["closeup"] = dist >= min(w, h) * 0.12
            body.append("eyes")
        lip = lip_span(lm, w, h)
        if lip is not None and lip >= min(w, h) * 0.04:
            labels["lips_visible"] = True
            body.append("lips")
        body.append("face")

        # Multi-face: min mouth-to-mouth (Hall intimate bands)
        if n_faces >= 2:
            geo = mouth_pair_metrics(fres.face_landmarks, w, h)
            labels.update(geo)
            lips_any = labels.get("lips_visible")
            # Any face with visible lips boosts confidence in geo
            for lm_i in fres.face_landmarks[1:]:
                lip_i = lip_span(lm_i, w, h)
                if lip_i is not None and lip_i >= min(w, h) * 0.04:
                    lips_any = True
                    break
            labels["lips_visible"] = bool(lips_any)
            if lips_any:
                body.append("lips")

    n_hands = 0
    if hand_lm is not None:
        hres = hand_lm.detect(mp_img)
        n_hands = len(hres.hand_landmarks) if hres.hand_landmarks else 0
        labels["n_hands"] = n_hands
        if n_hands:
            body.append("hands")

    labels["body_parts"] = sorted(set(body))
    # kiss_candidate = multi-face; kiss_geo = mouth within τ_imminent
    labels["kiss_candidate"] = n_faces >= 2
    if n_faces < 2:
        labels.setdefault("kiss_geo", False)
        labels.setdefault("kiss_strict", False)
        labels.setdefault("mouth_band", None)
    return base


def merge_row(old: dict | None, new: dict) -> dict:
    """Merge: preserve manual/vl fields; refresh mediapipe labels (incl. mouth geo)."""
    if old is None:
        return new
    merged = dict(old)
    old_labels = dict(old.get("labels") or {})
    new_labels = dict(new.get("labels") or {})
    # Keep human/VL kiss if already set
    if old_labels.get("has_kiss") is not None and new_labels.get("has_kiss") is None:
        new_labels["has_kiss"] = old_labels["has_kiss"]
    for soft in ("kiss_confidence", "kiss_reason"):
        if old_labels.get(soft) is not None and new_labels.get(soft) is None:
            new_labels[soft] = old_labels[soft]
    old_src = old.get("source") or ""
    if "vl" in old_src or old_src in ("manual", "vl-litellm"):
        # preserve VL provenance while refreshing geometry
        if old_src.startswith("mediapipe"):
            merged["source"] = old_src
        else:
            merged["source"] = f"mediapipe+{old_src}"
        if old.get("vl_model"):
            merged["vl_model"] = old["vl_model"]
    else:
        merged["source"] = new["source"]
    merged["labels"] = {**old_labels, **new_labels}
    merged["model"] = new["model"]
    merged["updated_at"] = new["updated_at"]
    merged["sha256"] = new["sha256"]
    merged["path"] = new["path"]
    merged["image_id"] = new["image_id"]
    merged["film_slug"] = new["film_slug"]
    merged["filename"] = new["filename"]
    merged["confidence"] = new["confidence"]
    return merged


def needs_regeo(prev: dict | None) -> bool:
    """True if multi-face row missing mouth geometry fields."""
    if not prev:
        return False
    labs = prev.get("labels") or {}
    if (labs.get("n_faces") or 0) < 2:
        return False
    return labs.get("mouth_dist_norm") is None


def main() -> int:
    p = argparse.ArgumentParser(description="Pass A MediaPipe classify — keep all stills")
    p.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--limit", type=int, default=0, help="Max images (0=all)")
    p.add_argument("--skip-hands", action="store_true", help="Faster: face only")
    p.add_argument("--force", action="store_true", help="Reclassify even if sha256 matches")
    p.add_argument(
        "--regeo",
        action="store_true",
        help="Reclassify multi-face rows missing mouth_dist_norm (kiss geo upgrade)",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    root = args.images.expanduser().resolve()
    out_path = args.output.expanduser().resolve()
    images = collect_images(root)
    if args.limit > 0:
        images = images[: args.limit]

    existing = load_classifications(out_path)
    print(
        f"pass-a: {len(images)} images  existing_labels={len(existing)}  out={out_path}"
        f"  regeo={args.regeo}",
        file=sys.stderr,
    )
    if args.dry_run:
        print(json.dumps({"images": len(images), "existing": len(existing)}, indent=2))
        return 0

    face_lm = vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model(FACE_MODEL, FACE_MODEL_URL))),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=5,
            min_face_detection_confidence=0.4,
            min_face_presence_confidence=0.4,
            min_tracking_confidence=0.4,
        )
    )
    hand_lm = None
    if not args.skip_hands:
        hand_lm = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(ensure_model(HAND_MODEL, HAND_MODEL_URL))),
                running_mode=vision.RunningMode.IMAGE,
                num_hands=2,
                min_hand_detection_confidence=0.35,
                min_hand_presence_confidence=0.35,
                min_tracking_confidence=0.35,
            )
        )

    done = 0
    skipped = 0
    kiss_cand = 0
    kiss_geo = 0
    kiss_strict = 0
    multi = 0
    zero = 0
    band_counts: dict[str, int] = {}
    try:
        for i, path in enumerate(images, 1):
            image_id = str(path.relative_to(root)).replace("\\", "/")
            prev = existing.get(image_id)
            if prev and not args.force:
                sha = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
                src = prev.get("source") or ""
                hash_ok = prev.get("sha256") == sha and src.startswith("mediapipe")
                if hash_ok and not (args.regeo and needs_regeo(prev)):
                    skipped += 1
                    labs = prev.get("labels") or {}
                    if labs.get("kiss_candidate"):
                        kiss_cand += 1
                    if labs.get("kiss_geo"):
                        kiss_geo += 1
                    if labs.get("kiss_strict"):
                        kiss_strict += 1
                    nf = labs.get("n_faces", 0)
                    if nf == 0:
                        zero += 1
                    elif nf >= 2:
                        multi += 1
                    b = labs.get("mouth_band")
                    if b:
                        band_counts[b] = band_counts.get(b, 0) + 1
                    continue

            row = classify_one(path, root, face_lm, hand_lm)
            existing[image_id] = merge_row(prev, row)
            done += 1
            labs = row["labels"]
            nf = labs["n_faces"]
            if nf == 0:
                zero += 1
            elif nf >= 2:
                multi += 1
            if labs.get("kiss_candidate"):
                kiss_cand += 1
            if labs.get("kiss_geo"):
                kiss_geo += 1
            if labs.get("kiss_strict"):
                kiss_strict += 1
            b = labs.get("mouth_band")
            if b:
                band_counts[b] = band_counts.get(b, 0) + 1

            if i % 100 == 0 or i == len(images):
                print(
                    f"  {i}/{len(images)} classified_new={done} skipped={skipped} "
                    f"multi_face={multi} kiss_geo={kiss_geo} kiss_strict={kiss_strict}",
                    file=sys.stderr,
                )
                write_classifications(out_path, existing)
    finally:
        face_lm.close()
        if hand_lm is not None:
            hand_lm.close()

    write_classifications(out_path, existing)
    summary = {
        "images_scanned": len(images),
        "classified_new_or_updated": done,
        "skipped_unchanged": skipped,
        "total_in_file": len(existing),
        "multi_face": multi,
        "zero_face": zero,
        "kiss_candidates": kiss_cand,
        "kiss_geo": kiss_geo,
        "kiss_strict": kiss_strict,
        "mouth_bands": band_counts,
        "tau": {
            "contact": TAU_CONTACT,
            "imminent": TAU_IMMINENT,
            "intimate_far": TAU_INTIMATE_FAR,
        },
        "output": str(out_path),
        "policy": "keep_all — additive labels only; kiss_geo = mouth_dist_norm<=1.2",
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
