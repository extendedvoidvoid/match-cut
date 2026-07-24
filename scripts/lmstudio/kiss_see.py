#!/usr/bin/env python3
"""SEE module — Qwen2.5-VL on sample thumbs → download_recommend per film.

Reads candidates_see.jsonl, downloads 1–N thumbs into .see-cache/,
calls LM Studio OpenAI-compatible vision API, writes see_scores.jsonl
+ candidates_brute.jsonl (SEE pass films).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "film-grab"
DEFAULT_BASE = os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:32768/v1")
DEFAULT_MODEL = os.environ.get("LM_STUDIO_MODEL_ID", "qwen_qwen2.5-vl-7b-instruct")

SCHEMA = {
    "type": "object",
    "properties": {
        "n_people": {"type": "integer"},
        "faces_close": {"type": "boolean"},
        "likely_kiss_or_near_kiss": {"type": "boolean"},
        "emotion_high": {"type": "boolean"},
        "download_recommend": {"type": "boolean"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": [
        "n_people",
        "faces_close",
        "likely_kiss_or_near_kiss",
        "emotion_high",
        "download_recommend",
        "confidence",
        "reason",
    ],
    "additionalProperties": False,
}


def image_data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def see_image(
    path: Path,
    *,
    base_url: str,
    model: str,
    temperature: float = 0.1,
    timeout: float = 180.0,
) -> dict:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You screen film stills for a kiss/high-emotion close-up reel. "
                    "download_recommend=true only if the frame likely has two people "
                    "with faces/mouths close (kiss, near-kiss, intimate lean-in). "
                    "Answer only via JSON schema."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Does this still show two people kissing or about to kiss "
                            "(faces/mouths close, high intimacy)? "
                            "Set download_recommend if the whole film gallery is worth bulk download "
                            "for a kiss montage."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_data_url(path)}},
                ],
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "KissSEE", "schema": SCHEMA, "strict": True},
        },
        "temperature": temperature,
        "max_tokens": 256,
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


def film_title_guess(slug: str) -> str:
    return slug.replace("-", " ").title()


GALLERY_RE = re.compile(
    r"https?://film-grab\.com/wp-content/uploads/photo-gallery/(?:thumb/)?[^\"'<>]+?\.jpe?g",
    re.I,
)
GALLERY_ID_RE = re.compile(r'gallery[_-]?id["\']?\s*[:=]\s*["\']?(\d+)', re.I)


def parse_gallery_urls(html: str) -> tuple[list[str], list[str]]:
    thumbs: list[str] = []
    fulls: list[str] = []
    seen: set[str] = set()
    for m in GALLERY_RE.finditer(html):
        u = m.group(0).split("?")[0]
        # spaces in filenames are valid on film-grab
        if u in seen:
            continue
        seen.add(u)
        if "/thumb/" in u:
            thumbs.append(u)
        else:
            fulls.append(u)
    return thumbs, fulls


def fetch_post_thumbs(post_url: str, n: int, dest_dir: Path) -> list[Path]:
    """Get up to n sample images from post HTML or BWG ajax (older galleries)."""
    headers = {
        "User-Agent": "match-cut-see/1.0",
        "Referer": post_url,
        "Accept": "text/html,*/*",
    }
    with httpx.Client(http2=False, headers=headers, timeout=45.0, follow_redirects=True) as c:
        r = c.get(post_url)
        r.raise_for_status()
        html = r.text
        thumbs, fulls = parse_gallery_urls(html)

        # Older posts load gallery via admin-ajax (gallery_id=…)
        if len(thumbs) + len(fulls) < n:
            gids = GALLERY_ID_RE.findall(html)
            for gid in dict.fromkeys(gids):  # unique preserve order
                try:
                    ar = c.post(
                        "https://film-grab.com/wp-admin/admin-ajax.php",
                        data={"action": "bwg_frontend_data", "gallery_id": gid},
                    )
                    if ar.status_code == 200 and ar.text:
                        t2, f2 = parse_gallery_urls(ar.text)
                        thumbs.extend(t2)
                        fulls.extend(f2)
                except Exception:
                    continue
                if len(thumbs) + len(fulls) >= n:
                    break

        # de-dupe preserve order
        def uniq(seq: list[str]) -> list[str]:
            out, s = [], set()
            for u in seq:
                if u not in s:
                    s.add(u)
                    out.append(u)
            return out

        thumbs, fulls = uniq(thumbs), uniq(fulls)
        pool = thumbs if len(thumbs) >= n else (thumbs + [u for u in fulls if u not in thumbs])
        if not pool:
            pool = fulls
        # Spread samples across gallery (first frames often title cards, not kisses)
        if len(pool) <= n:
            urls = list(pool)
        else:
            idxs = [int(round(i * (len(pool) - 1) / max(n - 1, 1))) for i in range(n)]
            urls = [pool[i] for i in idxs]

        dest_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for i, u in enumerate(urls[:n]):
            name = Path(urlparse(u).path).name.replace(" ", "_")
            dest = dest_dir / f"{i:02d}_{name}"
            if not dest.exists() or dest.stat().st_size == 0:
                rr = c.get(u)
                rr.raise_for_status()
                dest.write_bytes(rr.content)
            paths.append(dest)
        return paths


def film_pass(scores: list[dict]) -> bool:
    """Pass only on explicit kiss/recommend (not mere faces_close)."""
    if not scores:
        return False
    if any(s.get("download_recommend") for s in scores):
        return True
    if any(
        s.get("likely_kiss_or_near_kiss") and float(s.get("confidence") or 0) >= 0.5
        for s in scores
    ):
        return True
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="SEE samples with Qwen2.5-VL via LM Studio")
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--input", type=Path, default=None, help="candidates_see.jsonl")
    p.add_argument("--base-url", default=DEFAULT_BASE)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--samples", type=int, default=2)
    p.add_argument("--limit", type=int, default=0, help="Max films (0=all in SEE queue)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    out_dir = args.output.expanduser().resolve()
    in_path = (args.input or out_dir / "candidates_see.jsonl").expanduser().resolve()
    if not in_path.is_file():
        print(f"error: missing {in_path} — run ratio_gate first", file=sys.stderr)
        return 1

    films = [json.loads(l) for l in in_path.read_text().splitlines() if l.strip()]
    if args.limit > 0:
        films = films[: args.limit]

    # API smoke
    try:
        with httpx.Client(timeout=5.0) as c:
            mr = c.get(args.base_url.rstrip("/") + "/models")
            mr.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "error": "LM Studio API not reachable",
                    "base_url": args.base_url,
                    "hint": "mc lmstudio server-start && mc lmstudio load-vision",
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    if args.dry_run:
        print(json.dumps({"module": "acquire.see_sample_qwen", "films": len(films), "dry_run": True}, indent=2))
        return 0

    cache = out_dir / ".see-cache"
    scores_path = out_dir / "see_scores.jsonl"
    brute_path = out_dir / "candidates_brute.jsonl"
    scores_path.write_text("")
    brute_rows: list[dict] = []
    passed = 0
    failed = 0

    for i, film in enumerate(films, 1):
        slug = film["film_slug"]
        post = film["post_url"]
        n = int(film.get("see_samples") or args.samples)
        film_cache = cache / slug
        print(f"[{i}/{len(films)}] SEE {slug}", file=sys.stderr)
        try:
            paths = fetch_post_thumbs(post, n, film_cache)
        except Exception as exc:  # noqa: BLE001
            print(f"  warn fetch: {exc}", file=sys.stderr)
            failed += 1
            continue
        if not paths:
            print("  warn: no sample images", file=sys.stderr)
            failed += 1
            continue

        sample_scores: list[dict] = []
        for path in paths:
            try:
                sc = see_image(path, base_url=args.base_url, model=args.model)
                sc["image"] = str(path.relative_to(out_dir)) if path.is_relative_to(out_dir) else str(path)
                sample_scores.append(sc)
                print(
                    f"  {path.name}: kiss={sc.get('likely_kiss_or_near_kiss')} "
                    f"rec={sc.get('download_recommend')} c={sc.get('confidence')}",
                    file=sys.stderr,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  warn VL {path.name}: {exc}", file=sys.stderr)
                failed += 1

        ok = film_pass(sample_scores)
        row = {
            **film,
            "see_status": "pass" if ok else "reject",
            "see_scores": sample_scores,
            "see_pass": ok,
            "film_title": film_title_guess(slug),
        }
        with scores_path.open("a") as f:
            f.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
        if ok:
            passed += 1
            brute_rows.append(row)

    with brute_path.open("w") as f:
        for r in brute_rows:
            f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")

    summary = {
        "module": "acquire.see_sample_qwen",
        "films_seen": len(films),
        "passed": passed,
        "failed_or_empty": failed,
        "model": args.model,
        "base_url": args.base_url,
        "scores": str(scores_path),
        "brute_queue": str(brute_path),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
