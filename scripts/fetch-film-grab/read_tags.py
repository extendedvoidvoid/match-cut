#!/usr/bin/env python3
"""ONLINE meta only — film-grab WP tags (kiss/couple/…) → candidates_tags.jsonl.

No vision. Fast HTML + wp-json tag search.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "film-grab"
BASE = "https://film-grab.com"
POST_RE = re.compile(r"https?://film-grab\.com/\d{4}/\d{2}/\d{2}/([^/\"'?#]+)/?", re.I)

# Tag slugs / search seeds for couple-kiss prior
DEFAULT_TAG_SLUGS = (
    "kiss",
    "couple",
    "couple-kissing",
    "couple-holding-hands",
    "boyfriend-girlfriend-relationship",
    "first-kiss",
    "female-female-kiss",
    "gay-couple",
)
DEFAULT_SEARCHES = ("kiss", "couple", "kissing")


def normalize_post_url(url: str) -> str:
    u = url.split("?")[0].rstrip("/") + "/"
    if u.startswith("/"):
        u = BASE + u
    return u


def slug_from_url(url: str) -> str:
    return urlparse(url).path.strip("/").split("/")[-1].lower()


def extract_posts(html: str) -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    for m in POST_RE.finditer(html):
        url = normalize_post_url(m.group(0))
        slug = m.group(1).lower()
        if slug in ("page", "genre", "category", "tag"):
            continue
        found[url] = slug
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
        href = m.group(1)
        full = href if href.startswith("http") else BASE + href
        pm = POST_RE.search(full)
        if not pm:
            continue
        url = normalize_post_url(pm.group(0))
        slug = pm.group(1).lower()
        if slug in ("page", "genre", "category", "tag"):
            continue
        found[url] = slug
    return list(found.items())


def max_tag_page(html: str, slug: str) -> int:
    max_p = 1
    pat = re.compile(rf"/tag/{re.escape(slug)}/page/(\d+)/?")
    for m in pat.finditer(html):
        max_p = max(max_p, int(m.group(1)))
    return max_p


def on_disk(out_dir: Path) -> set[str]:
    return {p.name for p in out_dir.iterdir() if p.is_dir() and any(p.glob("*.jpg"))}


def main() -> int:
    p = argparse.ArgumentParser(description="READ film-grab tags (meta only, no vision)")
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--tags", default=",".join(DEFAULT_TAG_SLUGS))
    p.add_argument("--search", default=",".join(DEFAULT_SEARCHES), help="wp-json tag search seeds")
    p.add_argument("--delay", type=float, default=0.25)
    p.add_argument("--max-pages", type=int, default=5, help="max pages per tag slug")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    out_dir = args.output.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    disk = on_disk(out_dir)
    tag_slugs = [t.strip() for t in args.tags.split(",") if t.strip()]
    searches = [s.strip() for s in args.search.split(",") if s.strip()]

    headers = {"User-Agent": "match-cut-read-tags/1.0", "Accept": "text/html,application/json"}
    by_slug: dict[str, dict] = {}

    with httpx.Client(http2=False, headers=headers, timeout=40.0, follow_redirects=True) as client:
        # Expand tag list via search
        found_slugs = list(tag_slugs)
        for q in searches:
            try:
                r = client.get(f"{BASE}/wp-json/wp/v2/tags", params={"search": q, "per_page": 30})
                if r.status_code == 200:
                    for t in r.json():
                        s = (t.get("slug") or "").lower()
                        if s and s not in found_slugs:
                            # keep only kiss/couple-ish
                            if any(k in s for k in ("kiss", "couple", "relationship", "boyfriend", "girlfriend")):
                                found_slugs.append(s)
            except Exception as exc:  # noqa: BLE001
                print(f"warn search {q}: {exc}", file=sys.stderr)
            import time

            time.sleep(args.delay)

        print(f"tag slugs to crawl: {len(found_slugs)}", file=sys.stderr)

        for slug in found_slugs:
            base_url = f"{BASE}/tag/{slug}/"
            try:
                r0 = client.get(base_url)
                if r0.status_code == 404:
                    print(f"  skip missing tag/{slug}", file=sys.stderr)
                    continue
                r0.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                print(f"warn tag {slug}: {exc}", file=sys.stderr)
                continue
            pages = min(max_tag_page(r0.text, slug), args.max_pages)
            pages = max(pages, 1)
            for page in range(1, pages + 1):
                url = base_url if page == 1 else f"{base_url}page/{page}/"
                try:
                    html = r0.text if page == 1 else client.get(url).text
                except Exception as exc:  # noqa: BLE001
                    print(f"warn {url}: {exc}", file=sys.stderr)
                    break
                posts = extract_posts(html)
                print(f"  tag/{slug} p{page}: {len(posts)} posts", file=sys.stderr)
                for post_url, film_slug in posts:
                    row = by_slug.get(film_slug)
                    if row is None:
                        row = {
                            "film_slug": film_slug,
                            "post_url": post_url,
                            "tags": [],
                            "genres": [],
                            "source": "tag",
                            "on_disk": film_slug in disk,
                            "discovered_at": datetime.now(timezone.utc).isoformat(),
                        }
                        by_slug[film_slug] = row
                    if slug not in row["tags"]:
                        row["tags"].append(slug)
                    row["on_disk"] = film_slug in disk
                import time

                time.sleep(args.delay)

    rows = sorted(by_slug.values(), key=lambda r: (-len(r.get("tags") or []), r["film_slug"]))
    out_path = out_dir / "candidates_tags.jsonl"
    if not args.dry_run:
        with out_path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")

    summary = {
        "module": "acquire.read_tags",
        "unique_films": len(rows),
        "on_disk": sum(1 for r in rows if r["on_disk"]),
        "not_on_disk": sum(1 for r in rows if not r["on_disk"]),
        "top_tags_hits": [
            {"slug": r["film_slug"], "tags": r["tags"], "on_disk": r["on_disk"]}
            for r in rows[:12]
        ],
        "output": str(out_path),
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
