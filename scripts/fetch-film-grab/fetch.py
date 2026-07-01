#!/usr/bin/env python3
"""Film-grab.com image fetcher — asyncio httpx, sitemap discovery, resumable manifest.

Optimized for M3 Max (MATCHCUT_PARALLEL_JOBS=8). Techniques: WP sitemap crawl,
semaphore-limited HTTP/2 downloads, JSONL manifest dedup/resume, exponential backoff.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import inspect
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, urlunparse

import httpx
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

BASE = "https://film-grab.com"
# Jetpack sitemap (2026): sitemap.xml → sitemap-index-1.xml → sitemap-{1..N}.xml
SITEMAP_ROOTS = (
    f"{BASE}/sitemap.xml",
    f"{BASE}/sitemap-index-1.xml",
)
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "film-grab"
MANIFEST_NAME = "manifest.jsonl"
INVENTORY_NAME = "inventory.csv"
STATE_NAME = "state.json"
QUALIFIED_CACHE = ROOT / "scripts" / "reel-artifact" / "qualified.jsonl"

GALLERY_IMG_RE = re.compile(
    r"https?://film-grab\.com/wp-content/uploads/photo-gallery/[^\"'\s>]+\.jpg",
    re.I,
)
POST_PATH_RE = re.compile(r"^/\d{4}/\d{2}/\d{2}/")

DISCOVER_PATHS = [
    Path.home() / "projects" / "match-cut" / "assets" / "film-grab",
    Path.home() / "Downloads" / "film-grab",
    Path.home() / "Desktop" / "film-grab",
    Path.home() / "Pictures" / "film-grab",
    Path.home() / "projects" / "possession-essay" / "assets" / "film-grab",
    Path.home() / "projects" / "pedagogia" / "assets" / "film-grab",
]


@dataclass
class ImageEntry:
    url: str
    film_slug: str
    filename: str
    status: str = "pending"  # pending | done | failed
    bytes: int = 0
    sha256: str = ""


def normalize_url(url: str) -> str:
    parsed = urlparse(url.split("?")[0])
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def is_full_gallery_image(url: str) -> bool:
    path = urlparse(normalize_url(url)).path
    return "/photo-gallery/" in path and "/thumb/" not in path


def slug_from_post_url(post_url: str) -> str:
    path = urlparse(post_url).path.strip("/")
    return path.split("/")[-1] or "unknown"


def filename_from_url(url: str) -> str:
    return Path(urlparse(url).path).name


def load_manifest(path: Path) -> dict[str, ImageEntry]:
    entries: dict[str, ImageEntry] = {}
    if not path.exists():
        return entries
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            entry = ImageEntry(**data)
            entries[normalize_url(entry.url)] = entry
    return entries


def append_manifest(path: Path, entry: ImageEntry) -> None:
    with path.open("a") as f:
        f.write(json.dumps(asdict(entry), separators=(",", ":")) + "\n")


def rewrite_manifest(path: Path, entries: dict[str, ImageEntry]) -> None:
    with path.open("w") as f:
        for entry in entries.values():
            f.write(json.dumps(asdict(entry), separators=(",", ":")) + "\n")


def compact_manifest(out_dir: Path) -> tuple[int, int, dict[str, ImageEntry]]:
    """Collapse legacy duplicate paths; prefer on-disk file, then done status."""
    manifest_path = out_dir / MANIFEST_NAME
    entries = load_manifest(manifest_path)
    before = len(entries)

    by_path: dict[tuple[str, str], ImageEntry] = {}
    for entry in entries.values():
        key = (entry.film_slug, entry.filename)
        dest = out_dir / entry.film_slug / entry.filename
        current = by_path.get(key)
        if current is None:
            by_path[key] = entry
            continue
        current_on_disk = dest.exists() and dest.stat().st_size > 0
        if current_on_disk and entry.status == "done":
            by_path[key] = entry
        elif entry.status == "done" and current.status != "done":
            by_path[key] = entry

    compact = {normalize_url(e.url): e for e in by_path.values()}
    rewrite_manifest(manifest_path, compact)
    return before, len(compact), compact


def count_local_images(root: Path) -> int:
    if not root.exists():
        return 0
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    return sum(1 for p in root.rglob("*") if p.suffix.lower() in exts and p.is_file())


def discover_existing() -> list[tuple[Path, int]]:
    found: list[tuple[Path, int]] = []
    for p in DISCOVER_PATHS:
        if p.exists():
            found.append((p, count_local_images(p)))
    return found


@retry(stop=stop_after_attempt(4), wait=wait_exponential_jitter(initial=1, max=20))
async def fetch_text(client: httpx.AsyncClient, url: str, *, allow_404: bool = False) -> str:
    r = await client.get(url, follow_redirects=True)
    if allow_404 and r.status_code == 404:
        return ""
    r.raise_for_status()
    return r.text


def _sitemap_locs(xml: str) -> list[str]:
    root = ET.fromstring(xml)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [el.text.strip() for el in root.findall(".//sm:loc", ns) if el.text]


def _is_sitemap_index(xml: str) -> bool:
    return "<sitemapindex" in xml[:800]


async def sitemap_post_urls(client: httpx.AsyncClient) -> list[str]:
    queue: list[str] = list(SITEMAP_ROOTS)
    seen: set[str] = set()
    leaf_sitemaps: list[str] = []

    while queue:
        sm_url = queue.pop(0)
        if sm_url in seen:
            continue
        seen.add(sm_url)
        try:
            xml = await fetch_text(client, sm_url, allow_404=True)
        except httpx.HTTPError as exc:
            print(f"warn: sitemap {sm_url}: {exc}", file=sys.stderr)
            continue
        if not xml:
            continue

        if _is_sitemap_index(xml):
            for loc in _sitemap_locs(xml):
                if loc not in seen:
                    queue.append(loc)
            continue

        leaf_sitemaps.append(sm_url)

    if not leaf_sitemaps:
        raise RuntimeError("no film-grab sitemaps found (tried Jetpack + WordPress paths)")

    urls: list[str] = []
    for sm_url in leaf_sitemaps:
        try:
            xml = await fetch_text(client, sm_url)
            for loc in _sitemap_locs(xml):
                if POST_PATH_RE.search(urlparse(loc).path):
                    urls.append(loc)
        except httpx.HTTPError as exc:
            print(f"warn: sitemap {sm_url}: {exc}", file=sys.stderr)

    # Newest posts first (YYYY/MM/DD in path)
    return sorted(set(urls), reverse=True)


async def images_from_post(client: httpx.AsyncClient, post_url: str) -> list[str]:
    html = await fetch_text(client, post_url)
    found = {
        normalize_url(m.group(0))
        for m in GALLERY_IMG_RE.finditer(html)
        if is_full_gallery_image(m.group(0))
    }

    # Fallback DOM parse (some pages use relative paths)
    tree = HTMLParser(html)
    for node in tree.css("a[href]"):
        href = node.attributes.get("href", "")
        if "/photo-gallery/" in href and href.endswith(".jpg") and "/thumb/" not in href:
            url = normalize_url(href if href.startswith("http") else BASE + href)
            if is_full_gallery_image(url):
                found.add(url)
    return sorted(found)


async def plan_manifest(
    out_dir: Path,
    target_total: int,
    max_films: int | None,
    rate_delay: float,
) -> dict[str, ImageEntry]:
    manifest_path = out_dir / MANIFEST_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = load_manifest(manifest_path)

    headers = {
        "User-Agent": "match-cut-film-grab/1.0 (+https://github.com/extendedvoidvoid/match-cut)",
        "Accept": "text/html,application/xml",
    }
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    timeout = httpx.Timeout(30.0, connect=15.0)

    async with httpx.AsyncClient(http2=True, headers=headers, limits=limits, timeout=timeout) as client:
        posts = await sitemap_post_urls(client)
        if max_films:
            posts = posts[:max_films]
        print(f"posts in sitemap: {len(posts)}", file=sys.stderr)

        used_paths: set[tuple[str, str]] = set()
        for film_dir in out_dir.iterdir():
            if not film_dir.is_dir():
                continue
            for img in film_dir.glob("*.jpg"):
                used_paths.add((film_dir.name, img.name))
        need = max(0, target_total - len(used_paths))

        for i, post_url in enumerate(posts, 1):
            if need <= 0:
                break
            slug = slug_from_post_url(post_url)
            try:
                imgs = await images_from_post(client, post_url)
            except httpx.HTTPError as exc:
                print(f"warn: {post_url}: {exc}", file=sys.stderr)
                await asyncio.sleep(rate_delay)
                continue

            added = 0
            for url in imgs:
                key = normalize_url(url)
                if key in entries:
                    continue
                fname = filename_from_url(key)
                dest_key = (slug, fname)
                if dest_key in used_paths:
                    continue
                entry = ImageEntry(
                    url=key,
                    film_slug=slug,
                    filename=fname,
                )
                entries[key] = entry
                used_paths.add(dest_key)
                append_manifest(manifest_path, entry)
                added += 1
                need -= 1
                if need <= 0:
                    break

            if added:
                print(f"[{i}/{len(posts)}] {slug}: +{added} images", file=sys.stderr)
            await asyncio.sleep(rate_delay)

    return entries


@retry(stop=stop_after_attempt(5), wait=wait_exponential_jitter(initial=0.5, max=30))
async def download_one(
    client: httpx.AsyncClient,
    entry: ImageEntry,
    out_dir: Path,
) -> ImageEntry:
    dest = out_dir / entry.film_slug / entry.filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        data = dest.read_bytes()
        entry.status = "done"
        entry.bytes = len(data)
        entry.sha256 = hashlib.sha256(data).hexdigest()
        return entry

    async with client.stream("GET", entry.url, follow_redirects=True) as resp:
        resp.raise_for_status()
        data = await resp.aread()

    dest.write_bytes(data)
    entry.status = "done"
    entry.bytes = len(data)
    entry.sha256 = hashlib.sha256(data).hexdigest()
    return entry


async def download_manifest(
    out_dir: Path,
    workers: int,
    rate_delay: float,
) -> None:
    manifest_path = out_dir / MANIFEST_NAME
    entries = load_manifest(manifest_path)
    pending = [e for e in entries.values() if e.status != "done"]

    if not pending:
        print("nothing pending in manifest", file=sys.stderr)
        return

    sem = asyncio.Semaphore(workers)
    headers = {"User-Agent": "match-cut-film-grab/1.0"}
    limits = httpx.Limits(max_connections=workers + 4, max_keepalive_connections=workers)
    timeout = httpx.Timeout(60.0, connect=20.0)

    async with httpx.AsyncClient(http2=True, headers=headers, limits=limits, timeout=timeout) as client:
        async def worker(entry: ImageEntry) -> None:
            async with sem:
                try:
                    updated = await download_one(client, entry, out_dir)
                    entries[normalize_url(updated.url)] = updated
                    print(f"ok {updated.film_slug}/{updated.filename}", file=sys.stderr)
                except Exception as exc:  # noqa: BLE001
                    entry.status = "failed"
                    entries[normalize_url(entry.url)] = entry
                    print(f"fail {entry.url}: {exc}", file=sys.stderr)
                await asyncio.sleep(rate_delay)

        await asyncio.gather(*(worker(e) for e in pending))

    rewrite_manifest(manifest_path, entries)
    done = sum(1 for e in entries.values() if e.status == "done")
    failed = sum(1 for e in entries.values() if e.status == "failed")
    print(f"done={done} failed={failed} total={len(entries)}", file=sys.stderr)


def audit_health(out_dir: Path) -> dict[str, object]:
    manifest_path = out_dir / MANIFEST_NAME
    entries = load_manifest(manifest_path) if manifest_path.exists() else {}
    paths: set[tuple[str, str]] = set()
    status_counts: dict[str, int] = {}
    missing = 0
    for entry in entries.values():
        status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
        paths.add((entry.film_slug, entry.filename))
        dest = out_dir / entry.film_slug / entry.filename
        if entry.status == "done" and (not dest.exists() or dest.stat().st_size == 0):
            missing += 1

    on_disk = count_local_images(out_dir)
    film_dirs = sum(1 for p in out_dir.iterdir() if p.is_dir()) if out_dir.exists() else 0

    return {
        "output_dir": str(out_dir),
        "on_disk": on_disk,
        "film_dirs": film_dirs,
        "manifest_lines": sum(1 for _ in manifest_path.open()) if manifest_path.exists() else 0,
        "manifest_unique_urls": len(entries),
        "manifest_unique_paths": len(paths),
        "manifest_dup_paths": max(0, len(entries) - len(paths)),
        "status": status_counts,
        "missing_done_files": missing,
        "sitemap_roots": list(SITEMAP_ROOTS),
        "discover_paths": [str(p) for p in DISCOVER_PATHS],
        "api_keys": {
            "context7_local": bool(os.environ.get("CONTEXT7_API_KEY")),
            "film_grab_output": os.environ.get("FILM_GRAB_OUTPUT", str(DEFAULT_OUT)),
        },
        "fallbacks": {
            "sitemap": "Jetpack sitemap.xml → recursive index → leaf urlsets",
            "image_parse": "regex gallery URLs, then selectolax <a href> DOM fallback",
            "download": "skip existing file on disk; tenacity retry on network errors",
            "thumbs": "skip /thumb/ paths (full-res only)",
        },
    }


async def probe_links() -> dict[str, str]:
    results: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for url in (*SITEMAP_ROOTS, f"{BASE}/"):
            try:
                r = await client.head(url)
                results[url] = str(r.status_code)
            except httpx.HTTPError as exc:
                results[url] = f"error: {exc}"
    return results


def cmd_health(args: argparse.Namespace) -> int:
    out_dir = Path(args.output).expanduser().resolve()
    report = audit_health(out_dir)
    print(json.dumps(report, indent=2))
    issues = 0
    if report["manifest_dup_paths"]:
        issues += 1
        print("issue: manifest has duplicate paths — run `compact`", file=sys.stderr)
    if report["missing_done_files"]:
        issues += 1
        print("issue: done entries missing on disk — run `download`", file=sys.stderr)
    if not report["on_disk"]:
        issues += 1
        print("issue: no images on disk", file=sys.stderr)
    return 1 if issues else 0


async def cmd_health_online(args: argparse.Namespace) -> int:
    code = cmd_health(args)
    links = await probe_links()
    print("link_probe:", json.dumps(links, indent=2))
    for url, status in links.items():
        if not str(status).startswith("2"):
            print(f"warn: {url} -> {status}", file=sys.stderr)
            code = 1
    return code


def cmd_compact(args: argparse.Namespace) -> int:
    out_dir = Path(args.output).expanduser().resolve()
    before, after, _ = compact_manifest(out_dir)
    on_disk = count_local_images(out_dir)
    print(f"compacted manifest: {before} -> {after} urls | on disk: {on_disk}")
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    out_dir = Path(args.output).expanduser().resolve()
    before, after, entries = compact_manifest(out_dir)

    # Re-mark pending for failed entries so download can retry
    retried = 0
    for key, entry in list(entries.items()):
        if entry.status == "failed":
            entry.status = "pending"
            entries[key] = entry
            retried += 1
    if retried:
        rewrite_manifest(out_dir / MANIFEST_NAME, entries)

    pending = sum(1 for e in entries.values() if e.status == "pending")
    on_disk = count_local_images(out_dir)
    print(f"cleanup: manifest {before} -> {after} | failed->pending: {retried} | pending: {pending} | on_disk: {on_disk}")
    if pending and args.retry:
        return asyncio.run(cmd_download(args))
    return 0


def load_qualified_paths() -> set[str]:
    paths: set[str] = set()
    if not QUALIFIED_CACHE.exists():
        return paths
    with QUALIFIED_CACHE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            paths.add(str(Path(data["path"]).resolve()))
    return paths


def load_inventory_marks(csv_path: Path) -> dict[str, dict[str, str]]:
    """Preserve user columns when regenerating inventory."""
    marks: dict[str, dict[str, str]] = {}
    if not csv_path.exists():
        return marks
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("local_path") or row.get("image_id", "")
            if key:
                marks[key] = {
                    "marked_delete": row.get("marked_delete", ""),
                    "notes": row.get("notes", ""),
                }
    return marks


def cmd_inventory(args: argparse.Namespace) -> int:
    out_dir = Path(args.output).expanduser().resolve()
    manifest_path = out_dir / MANIFEST_NAME
    csv_path = Path(args.csv).expanduser().resolve() if args.csv else out_dir / INVENTORY_NAME

    entries = load_manifest(manifest_path)
    qualified = load_qualified_paths()
    preserved = load_inventory_marks(csv_path)
    generated_at = datetime.now(timezone.utc).isoformat()

    rows: list[dict[str, str]] = []
    seen_paths: set[tuple[str, str]] = set()

    for entry in entries.values():
        dest = out_dir / entry.film_slug / entry.filename
        path_key = (entry.film_slug, entry.filename)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)

        exists = dest.is_file() and dest.stat().st_size > 0
        local_path = str(dest.resolve()) if exists else str(dest)
        image_id = f"{entry.film_slug}/{entry.filename}"
        prev = preserved.get(local_path) or preserved.get(image_id, {})

        size = ""
        sha = entry.sha256 or ""
        if exists:
            st = dest.stat()
            size = str(st.st_size)
            if not sha:
                sha = hashlib.sha256(dest.read_bytes()).hexdigest()

        rows.append({
            "image_id": image_id,
            "film_slug": entry.film_slug,
            "filename": entry.filename,
            "local_path": local_path,
            "source_url": entry.url,
            "bytes": size or str(entry.bytes or ""),
            "sha256": sha,
            "manifest_status": entry.status,
            "on_disk": "yes" if exists else "no",
            "qualified_reel": "yes" if local_path in qualified else "no",
            "marked_delete": prev.get("marked_delete", ""),
            "notes": prev.get("notes", ""),
            "inventory_generated_at": generated_at,
        })

    rows.sort(key=lambda r: (r["film_slug"], r["filename"]))

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "image_id",
        "film_slug",
        "filename",
        "local_path",
        "source_url",
        "bytes",
        "sha256",
        "manifest_status",
        "on_disk",
        "qualified_reel",
        "marked_delete",
        "notes",
        "inventory_generated_at",
    ]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    on_disk = sum(1 for r in rows if r["on_disk"] == "yes")
    print(f"inventory: {len(rows)} rows | on_disk={on_disk} | {csv_path}")
    return 0


def cmd_discover(_: argparse.Namespace) -> int:
    found = discover_existing()
    if not found:
        print("No film-grab image folders found.")
        print("Default output:", DEFAULT_OUT)
        return 1
    for path, count in found:
        print(f"{path}\t{count} images")
    return 0


async def cmd_plan(args: argparse.Namespace) -> int:
    out_dir = Path(args.output).expanduser().resolve()
    await plan_manifest(out_dir, args.target, args.max_films, args.delay)
    total = len(load_manifest(out_dir / MANIFEST_NAME))
    on_disk = count_local_images(out_dir)
    print(f"manifest entries: {total} | on disk: {on_disk} | dir: {out_dir}")
    return 0


async def cmd_download(args: argparse.Namespace) -> int:
    out_dir = Path(args.output).expanduser().resolve()
    await download_manifest(out_dir, args.workers, args.delay)
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    out_dir = Path(args.output).expanduser().resolve()
    existing = count_local_images(out_dir)
    need = max(0, args.target - existing)
    print(f"on disk: {existing} | need: {need} | target: {args.target}", file=sys.stderr)
    if need > 0:
        await plan_manifest(out_dir, args.target, args.max_films, args.delay)
        await download_manifest(out_dir, args.workers, args.delay)
    else:
        print("target already met")
    final = count_local_images(out_dir)
    print(f"final on disk: {final}")
    return 0 if final >= args.target else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch film-grab.com gallery images")
    parser.add_argument(
        "--output",
        default=os.environ.get("FILM_GRAB_OUTPUT", str(DEFAULT_OUT)),
        help="Output directory (default: assets/film-grab)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("MATCHCUT_PARALLEL_JOBS", "8")),
        help="Parallel download workers",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=float(os.environ.get("FILM_GRAB_DELAY", "0.35")),
        help="Seconds between requests (rate limit)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_disc = sub.add_parser("discover", help="Scan common paths for existing film-grab images")
    p_disc.set_defaults(func=cmd_discover)

    p_plan = sub.add_parser("plan", help="Crawl sitemap and append image URLs to manifest")
    p_plan.add_argument("--target", type=int, default=3000, help="Total unique images on disk to plan toward")
    p_plan.add_argument("--max-films", type=int, default=None, help="Cap films scanned")
    p_plan.set_defaults(func=cmd_plan)

    p_dl = sub.add_parser("download", help="Download pending manifest entries")
    p_dl.set_defaults(func=cmd_download)

    p_run = sub.add_parser("run", help="discover gap → plan → download until target total on disk")
    p_run.add_argument("--target", type=int, default=3000, help="Total images on disk")
    p_run.add_argument("--max-films", type=int, default=None)
    p_run.set_defaults(func=cmd_run)

    p_health = sub.add_parser("health", help="Audit folders, manifest, keys, fallbacks (local)")
    p_health.set_defaults(func=cmd_health)

    p_health_net = sub.add_parser("health-online", help="health + probe film-grab.com links")
    p_health_net.set_defaults(func=cmd_health_online)

    p_compact = sub.add_parser("compact", help="Deduplicate manifest by on-disk path")
    p_compact.set_defaults(func=cmd_compact)

    p_cleanup = sub.add_parser("cleanup", help="compact manifest, reset failed->pending, optional retry")
    p_cleanup.add_argument("--retry", action="store_true", help="Download pending after cleanup")
    p_cleanup.set_defaults(func=cmd_cleanup)

    p_inv = sub.add_parser("inventory", help="Write inventory.csv (track downloads; preserve marked_delete)")
    p_inv.add_argument(
        "--csv",
        default=None,
        help=f"CSV path (default: <output>/{INVENTORY_NAME})",
    )
    p_inv.set_defaults(func=cmd_inventory)

    args = parser.parse_args()
    fn = args.func
    if inspect.iscoroutinefunction(fn):
        return asyncio.run(fn(args))
    return fn(args)


if __name__ == "__main__":
    raise SystemExit(main())