#!/usr/bin/env python3
"""Qwen VL poster typography QC via LM Studio OpenAI-compatible API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SLUG_DIR = ROOT / "assets" / "movie-posters" / "by-slug"
QC_OUT = ROOT / "assets" / "movie-posters" / "qc.jsonl"

SCHEMA = {
    "type": "object",
    "properties": {
        "has_typography": {"type": "boolean"},
        "text_detected": {"type": "string"},
        "confidence": {"type": "number"},
        "verdict": {"type": "string", "enum": ["textless", "typed", "uncertain"]},
    },
    "required": ["has_typography", "text_detected", "confidence", "verdict"],
    "additionalProperties": False,
}


def image_data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def qc_poster(
    path: Path,
    *,
    base_url: str,
    model: str,
    temperature: float = 0.1,
    timeout: float = 120.0,
) -> dict:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict movie-poster inspector. "
                    "Textless = no title, credits, taglines, logos with words, or any readable letters. "
                    "Answer only via JSON schema."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Does this poster contain ANY typography or readable text? "
                            "Be strict — watermarks, titles, actor names count as typed."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_data_url(path)}},
                ],
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "PosterQC", "schema": SCHEMA, "strict": True},
        },
        "temperature": temperature,
        "max_tokens": 256,
    }
    url = base_url.rstrip("/") + "/chat/completions"
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload, headers={"Authorization": "Bearer lm-studio"})
    r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"]
    result = json.loads(raw)
    result["path"] = str(path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="LM Studio poster typography QC")
    parser.add_argument("image", nargs="?", type=Path, help="Poster image path")
    parser.add_argument("--base-url", default=os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:32768/v1"))
    parser.add_argument("--model", default=os.environ.get("LM_STUDIO_MODEL_ID", "qwen_qwen2.5-vl-7b-instruct"))
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("LM_STUDIO_TEMPERATURE", "0.1")))
    parser.add_argument("--batch", action="store_true", help="QC all by-slug posters")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    paths: list[Path] = []
    if args.batch:
        paths = sorted(SLUG_DIR.glob("*.jpg"))
        if args.limit:
            paths = paths[: args.limit]
    elif args.image:
        paths = [args.image]
    else:
        paths = sorted(SLUG_DIR.glob("*.jpg"))[:1]

    if not paths:
        print("error: no images", file=sys.stderr)
        return 1

    QC_OUT.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for p in paths:
        if not p.is_file():
            continue
        print(f"qc {p.name}…", file=sys.stderr)
        try:
            row = qc_poster(
                p, base_url=args.base_url, model=args.model, temperature=args.temperature,
            )
            results.append(row)
            print(json.dumps(row, indent=2))
        except Exception as exc:
            print(f"fail {p}: {exc}", file=sys.stderr)
            return 1

    if args.batch and results:
        with QC_OUT.open("w") as f:
            for row in results:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
        typed = sum(1 for r in results if r.get("verdict") == "typed")
        print(json.dumps({
            "qc_file": str(QC_OUT),
            "checked": len(results),
            "typed": typed,
            "textless": sum(1 for r in results if r.get("verdict") == "textless"),
        }, indent=2), file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())