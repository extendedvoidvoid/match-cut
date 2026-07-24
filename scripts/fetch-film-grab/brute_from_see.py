#!/usr/bin/env python3
"""BRUTE download full galleries for candidates_brute.jsonl (SEE pass films).

Uses post HTML + bwg_frontend_data ajax (same as kiss_see). Updates manifest.jsonl.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "film-grab"
GALLERY_RE = re.compile(
    r"https?://film-grab\.com/wp-content/uploads/photo-gallery/(?:thumb/)?[^\"'<>]+?\.jpe?g",
    re.I,
)
GALLERY_ID_RE = re.compile(r'gallery[_-]?id["\']?\s*[:=]\s*["\']?(\d+)', re.I)


def normalize_url(u: str) -> str:
    return u.split("?")[0]


def parse_full_urls(html: str) -> list[str]:
    fulls: list[str] = []
    seen: set[str] = set()
    for m in GALLERY_RE.finditer(html):
        u = normalize_url(m.group(0))
        if "/thumb/" in u:
            # prefer full path without thumb
            full = u.replace("/photo-gallery/thumb/", "/photo-gallery/")
            u = full
        if u in seen:
            continue
        seen.add(u)
        fulls.append(u)
    return fulls


def collect_gallery_urls(client: httpx.Client, post_url: str) -> list[str]:
    r = client.get(post_url)
    r.raise_for_status()
    html = r.text
    urls = parse_full_urls(html)
    if len(urls) < 5:
        for gid in dict.fromkeys(GALLERY_ID_RE.findall(html)):
            ar = client.post(
                "https://film-grab.com/wp-admin/admin-ajax.php",
                data={"action": "bwg_frontend_data", "gallery_id": gid},
            )
            if ar.status_code == 200:
                urls.extend(parse_full_urls(ar.text))
    # unique
    out, seen = [], set()
    for u in urls:
        if u not in seen and "/thumb/" not in u:
            seen.add(u)
            out.append(u)
    return out


def load_manifest(path: Path) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    if not path.exists():
        return entries
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        entries[d.get("url") or ""] = d
    return entries


def append_manifest(path: Path, entry: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Brute download SEE-pass film galleries")
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--input", type=Path, default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--delay", type=float, default=0.2)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    out_dir = args.output.expanduser().resolve()
    in_path = (args.input or out_dir / "candidates_brute.jsonl").expanduser().resolve()
    if not in_path.is_file():
        print(f"error: missing {in_path}", file=sys.stderr)
        return 1

    films = [json.loads(l) for l in in_path.read_text().splitlines() if l.strip()]
    if args.limit > 0:
        films = films[: args.limit]

    manifest_path = out_dir / "manifest.jsonl"
    manifest = load_manifest(manifest_path)
    headers = {
        "User-Agent": "match-cut-brute/1.0",
        "Accept": "*/*",
    }

    downloaded = 0
    skipped = 0
    failed = 0
    films_ok = 0

    with httpx.Client(http2=False, headers=headers, timeout=60.0, follow_redirects=True) as client:
        for i, film in enumerate(films, 1):
            slug = film["film_slug"]
            post = film["post_url"]
            print(f"[{i}/{len(films)}] BRUTE {slug}", file=sys.stderr)
            try:
                urls = collect_gallery_urls(client, post)
            except Exception as exc:  # noqa: BLE001
                print(f"  fail list: {exc}", file=sys.stderr)
                failed += 1
                continue
            print(f"  gallery urls={len(urls)}", file=sys.stderr)
            if args.dry_run:
                continue
            dest_dir = out_dir / slug
            dest_dir.mkdir(parents=True, exist_ok=True)
            ok_film = 0
            for u in urls:
                fname = Path(urlparse(u).path).name.replace(" ", "_")
                dest = dest_dir / fname
                key = u
                if dest.exists() and dest.stat().st_size > 0:
                    skipped += 1
                    continue
                try:
                    client.headers["Referer"] = post
                    rr = client.get(u)
                    rr.raise_for_status()
                    data = rr.content
                    dest.write_bytes(data)
                    entry = {
                        "url": u,
                        "film_slug": slug,
                        "filename": fname,
                        "status": "done",
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "post_url": post,
                        "film_title": film.get("film_title") or slug.replace("-", " ").title(),
                        "full_url": u,
                        "thumb_url": "",
                        "source": "brute_see",
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                        "previous_sha256": "",
                    }
                    if key not in manifest:
                        append_manifest(manifest_path, entry)
                        manifest[key] = entry
                    downloaded += 1
                    ok_film += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"  fail {fname}: {exc}", file=sys.stderr)
                    failed += 1
                import time

                time.sleep(args.delay)
            if ok_film or any(dest_dir.glob("*.jpg")):
                films_ok += 1
            print(f"  new={ok_film} dir={slug}", file=sys.stderr)

    summary = {
        "module": "acquire.brute_download",
        "films": len(films),
        "films_with_files": films_ok,
        "downloaded": downloaded,
        "skipped_existing": skipped,
        "failed": failed,
        "output": str(out_dir),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
