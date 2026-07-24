#!/usr/bin/env python3
"""LOCAL LM Studio Qwen: label empty stills (n_faces==0) as nature|city|interior|other.

Optimizations (M3 Max / Qwen2.5-VL):
  - max edge 320px JPEG q=72 (smaller payload, faster VL)
  - max_tokens 96, temperature 0.1
  - skip already labeled scene_type
  - periodic merge + stats JSON for later reuse

Usage:
  mc lmstudio load-vision
  python3 scripts/lmstudio/scene_empty.py --limit 50   # smoke
  python3 scripts/lmstudio/scene_empty.py              # all empties
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLS = ROOT / "assets" / "film-grab" / "classifications.jsonl"
DEFAULT_NUMBERS = ROOT / "assets" / "film-grab" / "scene_empty_numbers.json"
DEFAULT_AUDIT = ROOT / "assets" / "film-grab" / "scene_empty_audit.jsonl"
DEFAULT_BASE = os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:32768/v1")
DEFAULT_MODEL = os.environ.get("LM_STUDIO_MODEL_ID", "qwen_qwen2.5-vl-7b-instruct")

# Optimized defaults
MAX_EDGE = 320
JPEG_QUALITY = 72
MAX_TOKENS = 96
TEMPERATURE = 0.1
SAVE_EVERY = 25

SCHEMA = {
    "type": "object",
    "properties": {
        "scene_type": {
            "type": "string",
            "enum": ["nature", "city", "interior", "other"],
        },
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["scene_type", "confidence", "reason"],
    "additionalProperties": False,
}

SYSTEM = (
    "You classify film stills with NO people visible for establishing shots. "
    "nature = landscape, sea, forest, sky, rural outdoors, wildlife without people. "
    "city = streets, buildings, skyline, traffic, urban exteriors without people. "
    "interior = indoors, rooms, empty architecture interiors. "
    "other = abstract, props, text cards, unclear. "
    "Answer only via JSON schema."
)


def load_jsonl(path: Path) -> dict[str, dict]:
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


def write_jsonl(path: Path, by_id: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(by_id.values(), key=lambda r: r.get("image_id", ""))
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")


def encode_image_small(path: Path, max_edge: int = MAX_EDGE, quality: int = JPEG_QUALITY) -> str:
    from PIL import Image

    im = Image.open(path)
    im = im.convert("RGB")
    w, h = im.size
    scale = min(1.0, max_edge / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def classify_scene(
    path: Path,
    *,
    base_url: str,
    model: str,
    timeout: float,
    max_edge: int,
) -> dict:
    data_url = encode_image_small(path, max_edge=max_edge)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Classify this empty establishing still (assume no people). "
                            "scene_type = nature | city | interior | other."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "SceneEmpty", "schema": SCHEMA, "strict": True},
        },
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    url = base_url.rstrip("/") + "/chat/completions"
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload, headers={"Authorization": "Bearer lm-studio"})
        r.raise_for_status()
        data = r.json()
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    text = str(content).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def compute_numbers(by_id: dict[str, dict]) -> dict:
    zero = 0
    labeled = 0
    counts: Counter[str] = Counter()
    confs: list[float] = []
    for row in by_id.values():
        labs = row.get("labels") or {}
        if (labs.get("n_faces") or 0) != 0:
            continue
        zero += 1
        st = labs.get("scene_type")
        if st:
            labeled += 1
            counts[st] += 1
            try:
                confs.append(float(labs.get("scene_confidence") or 0))
            except (TypeError, ValueError):
                pass
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "empty_total": zero,
        "empty_labeled": labeled,
        "empty_unlabeled": zero - labeled,
        "scene_type_counts": dict(counts),
        "pct_of_empty": {
            k: round(100.0 * v / labeled, 2) if labeled else 0.0 for k, v in counts.items()
        },
        "mean_confidence": round(sum(confs) / len(confs), 3) if confs else None,
        "params": {
            "max_edge": MAX_EDGE,
            "jpeg_quality": JPEG_QUALITY,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "model": DEFAULT_MODEL,
        },
        "unit_note": "establishing unit uses 2 empty; can split nature vs city later",
        "paths": {
            "classifications": str(DEFAULT_CLS),
            "audit": str(DEFAULT_AUDIT),
            "numbers": str(DEFAULT_NUMBERS),
        },
    }


def save_numbers(by_id: dict[str, dict], path: Path, extra: dict | None = None) -> dict:
    nums = compute_numbers(by_id)
    if extra:
        nums["run"] = extra
    # also write human snapshot
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nums, indent=2) + "\n")
    # permanent history append
    hist = path.with_name("scene_empty_numbers_history.jsonl")
    with hist.open("a") as f:
        f.write(json.dumps(nums, separators=(",", ":")) + "\n")
    return nums


def main() -> int:
    p = argparse.ArgumentParser(description="Qwen scene_type on empty stills via LM Studio")
    p.add_argument("--classifications", type=Path, default=DEFAULT_CLS)
    p.add_argument("--base-url", default=DEFAULT_BASE)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--limit", type=int, default=0, help="Max new labels (0=all unlabeled empties)")
    p.add_argument("--max-edge", type=int, default=MAX_EDGE)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--numbers", type=Path, default=DEFAULT_NUMBERS)
    p.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="Relabel even if scene_type set")
    args = p.parse_args()

    cls_path = args.classifications.expanduser().resolve()
    by_id = load_jsonl(cls_path)

    # LM smoke
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(args.base_url.rstrip("/") + "/models")
            r.raise_for_status()
            ids = [m.get("id") for m in r.json().get("data", [])]
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "error": "LM Studio not reachable",
                    "base_url": args.base_url,
                    "hint": "mc lmstudio server-start && mc lmstudio load-vision",
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    todo: list[dict] = []
    for row in by_id.values():
        labs = row.get("labels") or {}
        if (labs.get("n_faces") or 0) != 0:
            continue
        if labs.get("scene_type") and not args.force:
            continue
        image_id = row.get("image_id") or ""
        # skip SEE thumbs / cache — only real film-grab stills
        if ".see-cache" in image_id or "see-cache" in str(row.get("path") or ""):
            continue
        path = Path(row.get("path") or "")
        if not path.is_file():
            rel = image_id
            if rel:
                path = ROOT / "assets" / "film-grab" / rel
        if not path.is_file():
            continue
        # normalize path for later
        row["path"] = str(path)
        todo.append(row)

    todo.sort(key=lambda r: r.get("image_id") or "")
    if args.limit > 0:
        todo = todo[: args.limit]

    print(
        f"scene-empty: todo={len(todo)} model={args.model} max_edge={args.max_edge} "
        f"models_api={ids}",
        file=sys.stderr,
    )
    if args.dry_run:
        nums = save_numbers(by_id, args.numbers.expanduser().resolve(), {"dry_run": True, "todo": len(todo)})
        print(json.dumps(nums, indent=2))
        return 0

    done = 0
    errors = 0
    t0 = time.perf_counter()
    audit_path = args.audit.expanduser().resolve()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()

    for i, row in enumerate(todo, 1):
        image_id = row.get("image_id")
        path = Path(row.get("path") or "")
        if not path.is_file():
            path = ROOT / "assets" / "film-grab" / (image_id or "")
        try:
            sc = classify_scene(
                path,
                base_url=args.base_url,
                model=args.model,
                timeout=args.timeout,
                max_edge=args.max_edge,
            )
            st = sc.get("scene_type") or "other"
            if st not in ("nature", "city", "interior", "other"):
                st = "other"
            conf = float(sc.get("confidence") or 0)
            # clamp weird conf like 100
            if conf > 1.0:
                conf = conf / 100.0 if conf <= 100 else 1.0
            labs = dict(row.get("labels") or {})
            labs["scene_type"] = st
            labs["scene_confidence"] = round(conf, 3)
            labs["scene_reason"] = str(sc.get("reason") or "")[:200]
            row["labels"] = labs
            # track modules
            mods = labs.get("modules")
            if not isinstance(mods, list):
                mods = []
            tag = "classify.scene_empty@1.0"
            if tag not in mods:
                mods.append(tag)
            labs["modules"] = mods
            row["updated_at"] = datetime.now(timezone.utc).isoformat()
            # keep mediapipe source; note qwen scene
            src = row.get("source") or "mediapipe"
            if "qwen-scene" not in src:
                row["source"] = f"{src}+qwen-scene" if src else "qwen-scene"
            by_id[image_id] = row
            counts[st] += 1
            done += 1
            with audit_path.open("a") as af:
                af.write(
                    json.dumps(
                        {
                            "image_id": image_id,
                            "scene_type": st,
                            "confidence": conf,
                            "reason": labs["scene_reason"],
                            "ts": row["updated_at"],
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            print(
                f"  [{i}/{len(todo)}] {st} c={conf:.2f} {image_id}",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"  [{i}/{len(todo)}] ERR {image_id}: {exc}", file=sys.stderr)

        if i % SAVE_EVERY == 0 or i == len(todo):
            write_jsonl(cls_path, by_id)
            elapsed = time.perf_counter() - t0
            rate = done / elapsed if elapsed > 0 else 0
            save_numbers(
                by_id,
                args.numbers.expanduser().resolve(),
                {
                    "done_this_run": done,
                    "errors": errors,
                    "todo": len(todo),
                    "elapsed_sec": round(elapsed, 1),
                    "images_per_sec": round(rate, 3),
                    "eta_sec_remaining": round((len(todo) - i) / rate, 1) if rate > 0 else None,
                    "counts_this_run": dict(counts),
                    "model": args.model,
                    "base_url": args.base_url,
                    "max_edge": args.max_edge,
                },
            )

    write_jsonl(cls_path, by_id)
    elapsed = time.perf_counter() - t0
    nums = save_numbers(
        by_id,
        args.numbers.expanduser().resolve(),
        {
            "done_this_run": done,
            "errors": errors,
            "todo": len(todo),
            "elapsed_sec": round(elapsed, 1),
            "images_per_sec": round(done / elapsed, 3) if elapsed else 0,
            "counts_this_run": dict(counts),
            "model": args.model,
            "finished": True,
        },
    )
    print(json.dumps(nums, indent=2))
    return 0 if errors == 0 or done > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
