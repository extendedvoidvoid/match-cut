#!/usr/bin/env python3
"""TMDB textless-only poster fetcher — include_image_language=null, rate-limited."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from tmdb_client import TMDBClient, load_tmdb_key, key_fingerprint, slug_to_title

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "movie-posters"
BULK_DIR = DEFAULT_OUT / "bulk"
SLUG_DIR = DEFAULT_OUT / "by-slug"
MANIFEST = DEFAULT_OUT / "manifest.jsonl"
SLUG_MAP = DEFAULT_OUT / "film_slug_map.jsonl"
FILM_GRAB = ROOT / "assets" / "film-grab"


@dataclass
class ManifestEntry:
    tmdb_id: int
    title: str
    poster_path: str
    local_path: str
    textless: bool
    source: str
    film_slug: str = ""
    status: str = "done"


def download_poster(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            r = client.get(url)
        if r.status_code != 200:
            return False
        dest.write_bytes(r.content)
        return True
    except Exception as exc:
        print(f"download failed {url}: {exc}", file=sys.stderr)
        return False


def poster_file_id(poster_path: str) -> str:
    return hashlib.sha1(poster_path.encode()).hexdigest()[:10]


def load_manifest_paths() -> set[str]:
    seen: set[str] = set()
    if not MANIFEST.exists():
        return seen
    for line in MANIFEST.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        seen.add(d.get("poster_path") or d.get("local_path", ""))
    return seen


def append_manifest(entry: ManifestEntry) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a") as f:
        f.write(json.dumps(asdict(entry), separators=(",", ":")) + "\n")


def film_grab_slugs(images_root: Path) -> list[str]:
    if not images_root.is_dir():
        return []
    return sorted(d.name for d in images_root.iterdir() if d.is_dir())


def cmd_match_films(args: argparse.Namespace) -> int:
    api_key = load_tmdb_key()
    client = TMDBClient(api_key, delay=args.delay)
    print(f"TMDB auth: {key_fingerprint(api_key)}", file=sys.stderr)
    slugs = film_grab_slugs(Path(args.film_grab))
    seen = load_manifest_paths()
    print(f"matching {len(slugs)} slugs → strict textless only (include_image_language=null)", file=sys.stderr)

    map_rows: list[dict] = []
    films_with_textless = 0
    total_variants = 0

    for slug in slugs:
        title = slug_to_title(slug)
        hit = client.search_movie(title)
        if not hit:
            print(f"  miss slug={slug!r}", file=sys.stderr)
            map_rows.append({"film_slug": slug, "film_title": title, "tmdb_id": None, "posters": []})
            continue

        movie_id = hit["id"]
        records = client.movie_textless_records(movie_id, hit.get("title", title))
        if not records:
            print(f"  no textless tmdb_id={movie_id} slug={slug}", file=sys.stderr)
            map_rows.append({
                "film_slug": slug, "film_title": title, "tmdb_id": movie_id, "posters": [],
            })
            continue

        poster_entries: list[dict] = []
        for i, rec in enumerate(records):
            if rec.poster_path in seen and not args.force:
                # still list in map if on disk
                fid = poster_file_id(rec.poster_path)
                dest = SLUG_DIR / f"{slug}_{fid}.jpg"
                if dest.is_file():
                    poster_entries.append({
                        "local_path": str(dest),
                        "poster_path": rec.poster_path,
                        "textless": True,
                    })
                continue
            fid = poster_file_id(rec.poster_path)
            dest = SLUG_DIR / f"{slug}_{fid}.jpg"
            if args.force or not dest.exists():
                if not download_poster(rec.poster_url, dest):
                    continue
            seen.add(rec.poster_path)
            append_manifest(ManifestEntry(
                rec.tmdb_id, rec.title, rec.poster_path, str(dest), True, "film-grab", slug,
            ))
            poster_entries.append({
                "local_path": str(dest),
                "poster_path": rec.poster_path,
                "textless": True,
            })
            total_variants += 1

        if poster_entries:
            films_with_textless += 1
            print(f"  ok {slug} → {records[0].title} textless={len(poster_entries)}", file=sys.stderr)
        map_rows.append({
            "film_slug": slug,
            "film_title": title,
            "tmdb_id": movie_id,
            "tmdb_title": records[0].title if records else "",
            "posters": poster_entries,
        })

    with SLUG_MAP.open("w") as f:
        for row in map_rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")

    print(json.dumps({
        "slugs": len(slugs),
        "films_with_textless": films_with_textless,
        "textless_variants": total_variants,
        "map": str(SLUG_MAP),
    }, indent=2))
    return 0 if films_with_textless else 1


def cmd_bulk(args: argparse.Namespace) -> int:
    api_key = load_tmdb_key()
    client = TMDBClient(api_key, delay=args.delay)
    print(f"TMDB auth: {key_fingerprint(api_key)}", file=sys.stderr)
    seen = load_manifest_paths()
    seen_movies: set[int] = set()
    if MANIFEST.exists():
        for line in MANIFEST.read_text().splitlines():
            if line.strip():
                seen_movies.add(json.loads(line)["tmdb_id"])

    on_disk = len(list(BULK_DIR.glob("*.jpg"))) if BULK_DIR.exists() else 0
    target = args.target
    print(f"bulk strict textless target={target} on_disk={on_disk}", file=sys.stderr)

    page = 1
    downloaded = 0

    while on_disk + downloaded < target:
        movies = client.discover_movies(page)
        if not movies:
            break
        for m in movies:
            if on_disk + downloaded >= target:
                break
            mid = m["id"]
            if mid in seen_movies:
                continue
            records = client.movie_textless_records(mid, m.get("title", ""))
            if not records:
                continue
            rec = records[0]
            if rec.poster_path in seen:
                continue
            fid = poster_file_id(rec.poster_path)
            dest = BULK_DIR / f"{mid}_{fid}.jpg"
            if dest.exists():
                seen_movies.add(mid)
                continue
            if not download_poster(rec.poster_url, dest):
                continue
            seen.add(rec.poster_path)
            seen_movies.add(mid)
            downloaded += 1
            append_manifest(ManifestEntry(
                mid, rec.title, rec.poster_path, str(dest), True, "bulk",
            ))
            if downloaded % 25 == 0:
                print(f"  bulk {downloaded} page={page} latest={rec.title!r}", file=sys.stderr)
        page += 1
        if page > 500:
            break

    final = len(list(BULK_DIR.glob("*.jpg"))) if BULK_DIR.exists() else 0
    print(json.dumps({"downloaded_this_run": downloaded, "on_disk": final, "target": target}, indent=2))
    return 0


def cmd_purge_typed(_: argparse.Namespace) -> int:
    """Remove manifest + disk entries where textless=false."""
    if not MANIFEST.exists():
        return 0
    kept: list[str] = []
    removed = 0
    for line in MANIFEST.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if not d.get("textless", False):
            p = Path(d.get("local_path", ""))
            if p.is_file():
                p.unlink()
            removed += 1
            continue
        kept.append(line)
    MANIFEST.write_text("\n".join(kept) + ("\n" if kept else ""))
    print(json.dumps({"removed_non_textless": removed, "kept": len(kept)}, indent=2))
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    pool_textless = 0
    pool_typed = 0
    if MANIFEST.exists():
        for line in MANIFEST.read_text().splitlines():
            if not line.strip():
                continue
            if json.loads(line).get("textless"):
                pool_textless += 1
            else:
                pool_typed += 1
    print(json.dumps({
        "manifest_textless": pool_textless,
        "manifest_typed": pool_typed,
        "bulk_files": len(list(BULK_DIR.glob("*.jpg"))) if BULK_DIR.exists() else 0,
        "slug_files": len(list(SLUG_DIR.glob("*.jpg"))) if SLUG_DIR.exists() else 0,
        "api": key_fingerprint(load_tmdb_key()),
    }, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TMDB strict textless poster fetcher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_match = sub.add_parser("match-films")
    p_match.add_argument("--delay", type=float, default=0.35)
    p_match.add_argument("--film-grab", default=str(FILM_GRAB))
    p_match.add_argument("--force", action="store_true")
    p_match.set_defaults(func=cmd_match_films)

    p_bulk = sub.add_parser("bulk")
    p_bulk.add_argument("--target", type=int, default=10000)
    p_bulk.add_argument("--delay", type=float, default=0.35)
    p_bulk.set_defaults(func=cmd_bulk)

    p_purge = sub.add_parser("purge-typed", help="Delete non-textless posters from disk+manifest")
    p_purge.set_defaults(func=cmd_purge_typed)

    p_st = sub.add_parser("status")
    p_st.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())