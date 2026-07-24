#!/usr/bin/env python3
"""Pass C — VL kiss labels via OpenRouter / Mistral (or LiteLLM proxy).

Merges into classifications.jsonl. Never deletes images.
Default: only kiss_candidate (multi-face) rows from Pass A.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGES = ROOT / "assets" / "film-grab"
DEFAULT_CLASS = DEFAULT_IMAGES / "classifications.jsonl"
SECRETS = Path.home() / ".secrets"


def load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_openrouter_key() -> str | None:
    env = load_env_file(SECRETS / "openrouter.env")
    if env.get("OPENROUTER_API_KEY"):
        return env["OPENROUTER_API_KEY"]
    # json fallback
    jp = SECRETS / "openrouter-gemini-key.json"
    if jp.exists():
        try:
            data = json.loads(jp.read_text())
            for k in ("api_key", "OPENROUTER_API_KEY", "key"):
                if data.get(k):
                    return str(data[k])
        except json.JSONDecodeError:
            pass
    return os.environ.get("OPENROUTER_API_KEY")


def load_mistral_key() -> str | None:
    env = load_env_file(SECRETS / "mistral.env")
    return env.get("MISTRAL_API_KEY") or os.environ.get("MISTRAL_API_KEY")


def load_nvidia_key() -> str | None:
    env = load_env_file(SECRETS / "nvidia.env")
    return env.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY")


def load_classifications(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out[d["image_id"]] = d
    return out


def write_classifications(path: Path, by_id: dict[str, dict]) -> None:
    rows = sorted(by_id.values(), key=lambda r: r.get("image_id", ""))
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")


def b64_image(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return mime, base64.b64encode(raw).decode("ascii")


KISS_PROMPT = """You label film stills for a VJ archive.
Answer ONLY valid JSON (no markdown):
{"has_kiss": true|false, "confidence": 0.0-1.0, "reason": "short phrase"}

has_kiss=true only if two (or more) people are clearly kissing / mouths locked in a kiss.
Not: almost-kiss, hug only, one person, profile near without contact, or unclear.
"""


def call_openrouter(
    *,
    api_key: str,
    model: str,
    mime: str,
    b64: str,
    timeout: float,
) -> dict:
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": KISS_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 120,
        # Some OR accounts pin a dead default provider (e.g. z-ai); force usable ones
        "provider": {
            "order": ["OpenAI", "Azure", "Google", "Together", "Fireworks"],
            "allow_fallbacks": True,
            "ignore": ["z-ai"],
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/extendedvoidvoid/match-cut",
        "X-Title": "match-cut-classify-pass-c",
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    return parse_json_content(content)


def call_nvidia(
    *,
    api_key: str,
    model: str,
    mime: str,
    b64: str,
    timeout: float,
) -> dict:
    """NVIDIA NIM OpenAI-compatible chat (vision models)."""
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": KISS_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 120,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    return parse_json_content(content)


def call_mistral(
    *,
    api_key: str,
    model: str,
    mime: str,
    b64: str,
    timeout: float,
) -> dict:
    url = "https://api.mistral.ai/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": KISS_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 120,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    return parse_json_content(content)


def call_litellm_proxy(
    *,
    base_url: str,
    model: str,
    mime: str,
    b64: str,
    timeout: float,
) -> dict:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": KISS_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 120,
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    return parse_json_content(content)


def parse_json_content(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    # find first { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            hk = data.get("has_kiss")
            if isinstance(hk, str):
                hk = hk.lower() in ("true", "yes", "1")
            return {
                "has_kiss": bool(hk),
                "confidence": float(data.get("confidence", 0.5)),
                "reason": str(data.get("reason", ""))[:200],
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    # fallback freeform
    low = text.lower()
    if "has_kiss" in low and "true" in low:
        return {"has_kiss": True, "confidence": 0.55, "reason": text[:200]}
    if "kiss" in low and "not" not in low and "no " not in low:
        # ambiguous — prefer false unless explicit
        pass
    return {"has_kiss": False, "confidence": 0.4, "reason": text[:200] or "parse_fallback"}


def main() -> int:
    p = argparse.ArgumentParser(description="Pass C VL has_kiss on kiss candidates")
    p.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    p.add_argument("--classifications", type=Path, default=DEFAULT_CLASS)
    p.add_argument(
        "--provider",
        choices=("nvidia", "openrouter", "mistral", "litellm"),
        default="nvidia",
    )
    p.add_argument(
        "--model",
        default="",
        help="Provider model id (defaults per provider)",
    )
    p.add_argument("--litellm-url", default="http://127.0.0.1:4000")
    p.add_argument("--limit", type=int, default=0, help="Max candidates (0=all)")
    p.add_argument("--delay", type=float, default=0.4)
    p.add_argument("--timeout", type=float, default=90.0)
    p.add_argument("--force", action="store_true", help="Re-label even if has_kiss set")
    p.add_argument(
        "--also-lips",
        action="store_true",
        help="Include single-face lips_visible closeups as candidates",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    root = args.images.expanduser().resolve()
    class_path = args.classifications.expanduser().resolve()
    by_id = load_classifications(class_path)

    candidates: list[dict] = []
    for row in by_id.values():
        labels = row.get("labels") or {}
        if labels.get("has_kiss") is not None and not args.force:
            continue
        if labels.get("kiss_candidate"):
            candidates.append(row)
            continue
        if args.also_lips and labels.get("lips_visible") and labels.get("closeup"):
            candidates.append(row)

    candidates.sort(key=lambda r: r.get("image_id", ""))
    if args.limit > 0:
        candidates = candidates[: args.limit]

    model = args.model
    if not model:
        model = {
            "nvidia": "meta/llama-3.2-11b-vision-instruct",
            "openrouter": "openai/gpt-4o-mini",
            "mistral": "pixtral-12b-2409",
            "litellm": "openrouter-2026-07-17",
        }[args.provider]

    print(
        f"pass-c: candidates={len(candidates)} provider={args.provider} model={model}",
        file=sys.stderr,
    )
    if args.dry_run:
        print(json.dumps({"candidates": len(candidates), "model": model}, indent=2))
        return 0

    or_key = load_openrouter_key()
    mi_key = load_mistral_key()
    nv_key = load_nvidia_key()
    if args.provider == "openrouter" and not or_key:
        print("error: OPENROUTER_API_KEY missing (~/.secrets/openrouter.env)", file=sys.stderr)
        return 1
    if args.provider == "mistral" and not mi_key:
        print("error: MISTRAL_API_KEY missing", file=sys.stderr)
        return 1
    if args.provider == "nvidia" and not nv_key:
        print("error: NVIDIA_API_KEY missing (~/.secrets/nvidia.env)", file=sys.stderr)
        return 1

    labeled = 0
    kisses = 0
    errors = 0
    for i, row in enumerate(candidates, 1):
        image_id = row["image_id"]
        path = root / image_id
        if not path.is_file():
            # path field may be absolute
            alt = Path(row.get("path", ""))
            path = alt if alt.is_file() else path
        if not path.is_file():
            print(f"warn: missing {image_id}", file=sys.stderr)
            errors += 1
            continue
        try:
            mime, b64 = b64_image(path)
            if args.provider == "openrouter":
                result = call_openrouter(
                    api_key=or_key or "", model=model, mime=mime, b64=b64, timeout=args.timeout
                )
            elif args.provider == "mistral":
                result = call_mistral(
                    api_key=mi_key or "", model=model, mime=mime, b64=b64, timeout=args.timeout
                )
            elif args.provider == "nvidia":
                result = call_nvidia(
                    api_key=nv_key or "", model=model, mime=mime, b64=b64, timeout=args.timeout
                )
            else:
                result = call_litellm_proxy(
                    base_url=args.litellm_url, model=model, mime=mime, b64=b64, timeout=args.timeout
                )
        except Exception as exc:  # noqa: BLE001
            print(f"warn: {image_id}: {exc}", file=sys.stderr)
            errors += 1
            time.sleep(args.delay)
            continue

        labels = dict(row.get("labels") or {})
        labels["has_kiss"] = result["has_kiss"]
        labels["kiss_confidence"] = result["confidence"]
        labels["kiss_reason"] = result["reason"]
        row["labels"] = labels
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        prev_src = row.get("source", "mediapipe")
        if "vl" not in prev_src:
            row["source"] = f"{prev_src}+vl-{args.provider}"
        row["vl_model"] = model
        by_id[image_id] = row
        labeled += 1
        if result["has_kiss"]:
            kisses += 1
        print(
            f"[{i}/{len(candidates)}] {image_id} kiss={result['has_kiss']} "
            f"c={result['confidence']:.2f} {result['reason']!r}",
            file=sys.stderr,
        )
        if i % 10 == 0:
            write_classifications(class_path, by_id)
        time.sleep(args.delay)

    write_classifications(class_path, by_id)
    # global kiss count
    total_kiss = sum(1 for r in by_id.values() if (r.get("labels") or {}).get("has_kiss") is True)
    report = {
        "candidates": len(candidates),
        "labeled": labeled,
        "kisses_this_run": kisses,
        "has_kiss_total": total_kiss,
        "errors": errors,
        "provider": args.provider,
        "model": model,
        "output": str(class_path),
    }
    print(json.dumps(report, indent=2))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
