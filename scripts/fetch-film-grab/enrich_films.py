#!/usr/bin/env python3
"""Enrich films.jsonl + manifest post_url from Firecrawl map / posts_local.jsonl.

Uses home-IP httpx for post HTML (metadata + full gallery URLs). Never deletes images.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "film-grab"
BASE = "https://film-grab.com"
GALLERY_IMG_RE = re.compile(
    r"https?://film-grab\.com/wp-content/uploads/photo-gallery/[^\"'\s>]+\.jpg",
    re.I,
)


def normalize_url(url: str) -> str:
    p = urlparse(url.split("?")[0])
    return f"{p.scheme}://{p.netloc}{p.path}"


def is_full(url: str) -> bool:
    path = urlparse(normalize_url(url)).path
    return "/photo-gallery/" in path and "/thumb/" not in path


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict], key: str = "film_slug") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: r.get(key, ""))
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")


@retry(stop=stop_after_attempt(4), wait=wait_exponential_jitter(initial=1, max=15))
async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, follow_redirects=True)
    r.raise_for_status()
    return r.text


def parse_post(html: str, post_url: str, film_slug: str) -> dict:
    tree = HTMLParser(html)
    title = ""
    h1 = tree.css_first("h1")
    if h1 and h1.text(strip=True):
        title = h1.text(strip=True)
    if not title:
        t = tree.css_first("title")
        if t:
            title = t.text(strip=True).split("|")[0].split("–")[0].strip()

    full_urls: list[str] = []
    thumb_urls: list[str] = []
    seen: set[str] = set()
    for m in GALLERY_IMG_RE.finditer(html):
        u = normalize_url(m.group(0))
        if u in seen:
            continue
        seen.add(u)
        if is_full(u):
            full_urls.append(u)
        elif "/thumb/" in u:
            thumb_urls.append(u)

    # DOM fallback
    for node in tree.css("a[href]"):
        href = node.attributes.get("href", "")
        if "/photo-gallery/" not in href or not href.endswith(".jpg"):
            continue
        u = normalize_url(href if href.startswith("http") else BASE + href)
        if u in seen:
            continue
        seen.add(u)
        if is_full(u):
            full_urls.append(u)
        elif "/thumb/" in u:
            thumb_urls.append(u)

    # year from path
    year = None
    parts = urlparse(post_url).path.strip("/").split("/")
    if parts and parts[0].isdigit() and len(parts[0]) == 4:
        year = int(parts[0])

    return {
        "film_slug": film_slug,
        "film_title": title or film_slug.replace("-", " ").title(),
        "post_url": post_url,
        "year": year,
        "director": None,
        "tags": [],
        "image_count_on_page_full": len(full_urls),
        "image_count_on_page_thumb": len(thumb_urls),
        "full_gallery_urls": full_urls,
        "thumb_gallery_urls": thumb_urls,
        "source": "httpx+firecrawl_map",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def enrich_all(
    out_dir: Path,
    *,
    delay: float,
    limit: int,
    dry_run: bool,
) -> dict:
    posts_path = out_dir / "posts_local.jsonl"
    if not posts_path.exists():
        posts_path = out_dir / "posts.jsonl"
    posts = load_jsonl(posts_path)
    # only local film dirs
    local = {p.name for p in out_dir.iterdir() if p.is_dir()}
    posts = [p for p in posts if p.get("film_slug") in local]
    if limit > 0:
        posts = posts[:limit]

    films_by = {r["film_slug"]: r for r in load_jsonl(out_dir / "films.jsonl")}
    headers = {
        "User-Agent": "match-cut-film-grab/1.1 (+https://github.com/extendedvoidvoid/match-cut)",
        "Accept": "text/html",
    }
    enriched = 0
    failed = 0
    full_url_total = 0

    if dry_run:
        return {"posts": len(posts), "dry_run": True}

    async with httpx.AsyncClient(http2=True, headers=headers, timeout=30.0) as client:
        for i, post in enumerate(posts, 1):
            slug = post["film_slug"]
            url = post["post_url"]
            try:
                html = await fetch_html(client, url)
                meta = parse_post(html, url, slug)
                # preserve image_count from disk if present
                prev = films_by.get(slug, {})
                if prev.get("image_count"):
                    meta["image_count"] = prev["image_count"]
                else:
                    meta["image_count"] = sum(1 for _ in (out_dir / slug).glob("*.jpg"))
                films_by[slug] = meta
                full_url_total += meta["image_count_on_page_full"]
                enriched += 1
                print(
                    f"[{i}/{len(posts)}] {slug}: full={meta['image_count_on_page_full']} "
                    f"thumb={meta['image_count_on_page_thumb']} title={meta['film_title']!r}",
                    file=sys.stderr,
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"warn: {slug} {url}: {exc}", file=sys.stderr)
            await asyncio.sleep(delay)

    write_jsonl(out_dir / "films.jsonl", list(films_by.values()))

    # Patch manifest post_url / film_title / full_url hints (no deletes)
    man_path = out_dir / "manifest.jsonl"
    if man_path.exists():
        from fetch import (  # type: ignore
            enrich_entry_urls,
            entry_from_dict,
            is_thumb_url,
            load_manifest,
            rewrite_manifest,
        )

        # load via relative import fails when run as script — inline patch
        entries = {}
        for line in man_path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            entries.setdefault(d["url"], d)

        patched = 0
        for d in entries.values():
            slug = d.get("film_slug", "")
            meta = films_by.get(slug)
            if not meta:
                continue
            if not d.get("post_url"):
                d["post_url"] = meta.get("post_url", "")
                patched += 1
            if meta.get("film_title"):
                d["film_title"] = meta["film_title"]
            u = d.get("url", "")
            if "/thumb/" in u:
                d.setdefault("thumb_url", u)
                full = u.replace("/photo-gallery/thumb/", "/photo-gallery/")
                d.setdefault("full_url", full)
            else:
                d.setdefault("full_url", u)
            if not d.get("source"):
                d["source"] = "legacy"

        with man_path.open("w") as f:
            for d in entries.values():
                f.write(json.dumps(d, separators=(",", ":"), ensure_ascii=False) + "\n")
    else:
        patched = 0

    return {
        "posts": len(posts),
        "enriched": enriched,
        "failed": failed,
        "full_urls_seen_on_pages": full_url_total,
        "manifest_rows_patched": patched,
        "films_jsonl": str(out_dir / "films.jsonl"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Enrich film meta from posts_local.jsonl (home IP)")
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--delay", type=float, default=0.35)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    out = args.output.expanduser().resolve()
    report = asyncio.run(
        enrich_all(out, delay=args.delay, limit=args.limit, dry_run=args.dry_run)
    )
    print(json.dumps(report, indent=2))
    return 0 if report.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
