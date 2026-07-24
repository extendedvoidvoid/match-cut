#!/usr/bin/env python3
"""READ module — scrape film-grab genre category pages → ranked candidates.

Writes assets/film-grab/posts_by_genre.jsonl (+ ranked candidates).
Never downloads gallery JPGs (that is brute_download after SEE).
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
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "film-grab"
BASE = "https://film-grab.com"
POST_RE = re.compile(r"https?://film-grab\.com/\d{4}/\d{2}/\d{2}/([^/\"'?#]+)/?", re.I)

DEFAULT_GENRES = ("romance", "drama", "musical")

GENRE_SCORE = {
    "romance": 3,
    "drama": 2,
    "musical": 2,
    "comedy": 1,
    "action": -2,
    "war": -2,
    "horror": -2,
    "thriller": -1,
    "sci-fi": -1,
}

KW_BOOST = re.compile(
    r"\b(love|romance|romantic|affair|wedding|desire|passion|kiss|amour|heart)\b",
    re.I,
)
KW_DEMOTE = re.compile(
    r"\b(zombie|war|battlefield|apocalypse|slash|gore|martial)\b",
    re.I,
)


def slug_from_post_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.split("/")[-1] or "unknown"


def normalize_post_url(url: str) -> str:
    u = url.split("?")[0].rstrip("/") + "/"
    if u.startswith("/"):
        u = BASE + u
    return u


@retry(stop=stop_after_attempt(4), wait=wait_exponential_jitter(initial=0.5, max=12))
async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, follow_redirects=True)
    r.raise_for_status()
    return r.text


def extract_posts(html: str) -> list[tuple[str, str]]:
    """Return list of (post_url, film_slug) via regex (no selectolax)."""
    found: dict[str, str] = {}
    for m in POST_RE.finditer(html):
        url = normalize_post_url(m.group(0))
        slug = m.group(1).lower()
        if slug in ("page", "genre", "category"):
            continue
        found[url] = slug
    # relative hrefs
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
        href = m.group(1)
        full = href if href.startswith("http") else BASE + href
        pm = POST_RE.search(full)
        if not pm:
            continue
        url = normalize_post_url(pm.group(0))
        slug = pm.group(1).lower()
        if slug in ("page", "genre", "category"):
            continue
        found[url] = slug
    return sorted(found.items(), key=lambda x: x[1])


def max_page_from_html(html: str, genre: str) -> int:
    max_p = 1
    pat = re.compile(rf"/category/genre/{re.escape(genre)}/page/(\d+)/?")
    for m in pat.finditer(html):
        max_p = max(max_p, int(m.group(1)))
    return max_p


def read_score(slug: str, genres: list[str]) -> int:
    score = 0
    for g in genres:
        score += GENRE_SCORE.get(g, 0)
    if KW_BOOST.search(slug.replace("-", " ")):
        score += 1
    if KW_DEMOTE.search(slug.replace("-", " ")):
        score -= 2
    return score


def on_disk_slugs(out_dir: Path) -> set[str]:
    return {p.name for p in out_dir.iterdir() if p.is_dir() and any(p.glob("*.jpg"))}


async def discover_genre(
    out_dir: Path,
    genres: list[str],
    *,
    delay: float,
    max_pages: int,
    dry_run: bool,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "match-cut-film-grab/1.2 (+https://github.com/extendedvoidvoid/match-cut)",
        "Accept": "text/html",
    }
    disk = on_disk_slugs(out_dir)
    # slug → row
    by_slug: dict[str, dict] = {}

    async with httpx.AsyncClient(http2=True, headers=headers, timeout=30.0) as client:
        for genre in genres:
            base_url = f"{BASE}/category/genre/{genre}/"
            try:
                html0 = await fetch_html(client, base_url)
            except Exception as exc:  # noqa: BLE001
                print(f"warn: genre {genre}: {exc}", file=sys.stderr)
                continue
            pages = min(max_page_from_html(html0, genre), max_pages if max_pages > 0 else 10**9)
            pages = max(pages, 1)
            print(f"genre={genre} pages≤{pages}", file=sys.stderr)

            for page in range(1, pages + 1):
                url = base_url if page == 1 else f"{base_url}page/{page}/"
                try:
                    html = html0 if page == 1 else await fetch_html(client, url)
                except Exception as exc:  # noqa: BLE001
                    print(f"warn: {url}: {exc}", file=sys.stderr)
                    break
                posts = extract_posts(html)
                print(f"  [{genre} p{page}] posts={len(posts)}", file=sys.stderr)
                for post_url, slug in posts:
                    row = by_slug.get(slug)
                    if row is None:
                        row = {
                            "film_slug": slug,
                            "post_url": post_url,
                            "genres": [],
                            "read_score": 0,
                            "on_disk": slug in disk,
                            "source": "genre_category",
                            "discovered_at": datetime.now(timezone.utc).isoformat(),
                        }
                        by_slug[slug] = row
                    if genre not in row["genres"]:
                        row["genres"].append(genre)
                    row["read_score"] = read_score(slug, row["genres"])
                    row["on_disk"] = slug in disk
                await asyncio.sleep(delay)

    rows = sorted(
        by_slug.values(),
        key=lambda r: (-r["read_score"], r["on_disk"], r["film_slug"]),
    )

    out_path = out_dir / "posts_by_genre.jsonl"
    cand_path = out_dir / "candidates_read.jsonl"
    if not dry_run:
        with out_path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")
        # not yet on disk, ranked for SEE
        with cand_path.open("w") as f:
            for r in rows:
                if not r["on_disk"]:
                    f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")

    not_disk = sum(1 for r in rows if not r["on_disk"])
    summary = {
        "module": "acquire.read_genre",
        "genres": genres,
        "total_unique_films": len(rows),
        "on_disk": len(rows) - not_disk,
        "not_on_disk": not_disk,
        "top_not_on_disk": [
            {"slug": r["film_slug"], "score": r["read_score"], "genres": r["genres"]}
            for r in rows
            if not r["on_disk"]
        ][:15],
        "output": str(out_path),
        "candidates": str(cand_path),
        "dry_run": dry_run,
    }
    print(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="READ film-grab genre pages → candidates")
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--genres",
        default="romance,drama,musical",
        help="Comma-separated film-grab genre slugs",
    )
    p.add_argument("--delay", type=float, default=0.35)
    p.add_argument("--max-pages", type=int, default=0, help="0=all pages")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    genres = [g.strip().lower() for g in args.genres.split(",") if g.strip()]
    if not genres:
        genres = list(DEFAULT_GENRES)
    asyncio.run(
        discover_genre(
            args.output.expanduser().resolve(),
            genres,
            delay=args.delay,
            max_pages=args.max_pages,
            dry_run=args.dry_run,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
