#!/usr/bin/env python3
"""Fetch TMDB keywords per film slug → cache (principal meta fallback).

IMDb has richer categorized keywords; free dumps lack them. TMDB
`GET /movie/{id}/keywords` is the practical proxy.

Writes:
  assets/film-grab/keywords/{slug}.json
  assets/film-grab/keywords_index.jsonl
  assets/film-grab/keywords_df.json   # document frequency for IDF
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "film-grab"
sys.path.insert(0, str(ROOT / "scripts" / "fetch-posters"))

from kw_taxonomy import annotate_keywords, normalize_kw  # noqa: E402
from tmdb_client import TMDBClient, load_tmdb_key, slug_to_title  # noqa: E402

YEAR_RE = re.compile(r"^(?P<title>.+?)-(?P<year>19\d{2}|20\d{2})$")


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def slug_candidates(out_dir: Path) -> list[dict]:
    """Union of ranked / tags / read / posts_by_genre / films."""
    by: dict[str, dict] = {}
    for name in (
        "candidates_ranked.jsonl",
        "candidates_brute.jsonl",
        "candidates_tags.jsonl",
        "candidates_read.jsonl",
        "posts_by_genre.jsonl",
        "films.jsonl",
    ):
        for r in load_jsonl(out_dir / name):
            slug = r.get("film_slug")
            if not slug:
                continue
            if slug not in by:
                by[slug] = {
                    "film_slug": slug,
                    "film_title": r.get("film_title") or slug_to_title(slug),
                    "post_url": r.get("post_url"),
                    "year": r.get("year"),
                    "on_disk": bool(r.get("on_disk")),
                }
            else:
                if not by[slug].get("film_title") and r.get("film_title"):
                    by[slug]["film_title"] = r["film_title"]
                if not by[slug].get("post_url") and r.get("post_url"):
                    by[slug]["post_url"] = r["post_url"]
                if not by[slug].get("year") and r.get("year"):
                    by[slug]["year"] = r["year"]
    # on_disk from filesystem
    for p in out_dir.iterdir():
        if p.is_dir() and not p.name.startswith(".") and p.name not in (
            "keywords",
            "pools",
            "see-cache",
        ):
            if any(p.glob("*.jpg")):
                if p.name not in by:
                    by[p.name] = {
                        "film_slug": p.name,
                        "film_title": slug_to_title(p.name),
                        "post_url": None,
                        "year": None,
                        "on_disk": True,
                    }
                else:
                    by[p.name]["on_disk"] = True
    return sorted(by.values(), key=lambda x: x["film_slug"])


def parse_year_from_slug(slug: str) -> tuple[str, int | None]:
    m = YEAR_RE.match(slug)
    if m:
        return m.group("title").replace("-", " "), int(m.group("year"))
    return slug.replace("-", " "), None


def resolve_movie(client: TMDBClient, title: str, year: int | None) -> dict | None:
    hit = client.search_movie(title, year)
    if hit:
        return hit
    if year:
        return client.search_movie(title, None)
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch TMDB keywords for film-grab slugs")
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--limit", type=int, default=0, help="0 = all candidates")
    p.add_argument("--only-not-on-disk", action="store_true")
    p.add_argument("--force", action="store_true", help="refetch even if cache exists")
    p.add_argument("--slugs", type=str, default="", help="comma-separated slug filter")
    p.add_argument("--delay", type=float, default=0.3)
    args = p.parse_args()

    out_dir = args.output.expanduser().resolve()
    kw_dir = out_dir / "keywords"
    kw_dir.mkdir(parents=True, exist_ok=True)

    rows = slug_candidates(out_dir)
    if args.only_not_on_disk:
        rows = [r for r in rows if not r.get("on_disk")]
    if args.slugs:
        want = {s.strip() for s in args.slugs.split(",") if s.strip()}
        rows = [r for r in rows if r["film_slug"] in want]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    api_key = load_tmdb_key()
    client = TMDBClient(api_key, delay=args.delay)

    index: list[dict] = []
    df: dict[str, int] = {}
    stats = {
        "module": "acquire.fetch_tmdb_keywords",
        "requested": len(rows),
        "ok": 0,
        "empty": 0,
        "miss": 0,
        "cached": 0,
        "error": 0,
    }

    for i, r in enumerate(rows, 1):
        slug = r["film_slug"]
        cache_path = kw_dir / f"{slug}.json"
        if cache_path.is_file() and not args.force:
            try:
                rec = json.loads(cache_path.read_text())
            except json.JSONDecodeError:
                rec = None
            if rec and rec.get("keywords") is not None:
                stats["cached"] += 1
                index.append(_index_row(rec))
                for k in rec.get("keywords") or []:
                    n = k.get("norm") or normalize_kw(k.get("name", ""))
                    if n:
                        df[n] = df.get(n, 0) + 1
                continue

        title = r.get("film_title") or slug_to_title(slug)
        year = r.get("year")
        if not year or (isinstance(year, int) and year > 2030):
            # film-grab post year often wrong; prefer slug suffix
            _, y2 = parse_year_from_slug(slug)
            year = y2
        search_title, y_slug = parse_year_from_slug(slug)
        # prefer human title without year pollution
        q_title = title
        if re.search(r"\b(19|20)\d{2}\b", title) is None and y_slug:
            pass
        try:
            movie = resolve_movie(client, q_title, year if isinstance(year, int) else y_slug)
            if not movie and search_title != q_title:
                movie = resolve_movie(client, search_title, y_slug)
        except Exception as e:
            stats["error"] += 1
            print(f"  ERR {slug}: {e}", file=sys.stderr)
            continue

        if not movie:
            stats["miss"] += 1
            rec = {
                "film_slug": slug,
                "film_title": title,
                "tmdb_id": None,
                "tmdb_title": None,
                "keywords": [],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "status": "tmdb_miss",
            }
            cache_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
            index.append(_index_row(rec))
            if i % 25 == 0 or i == len(rows):
                print(f"  [{i}/{len(rows)}] miss={stats['miss']} ok={stats['ok']}", file=sys.stderr)
            continue

        tmdb_id = int(movie["id"])
        data = client._get(f"/movie/{tmdb_id}/keywords")
        raw = (data or {}).get("keywords") or []
        annotated = annotate_keywords(raw)
        rec = {
            "film_slug": slug,
            "film_title": title,
            "tmdb_id": tmdb_id,
            "tmdb_title": movie.get("title"),
            "tmdb_release_date": movie.get("release_date"),
            "keywords": annotated,
            "n_keywords": len(annotated),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok" if annotated else "empty",
            "source": "tmdb",
        }
        cache_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
        index.append(_index_row(rec))
        for k in annotated:
            n = k["norm"]
            df[n] = df.get(n, 0) + 1
        if annotated:
            stats["ok"] += 1
        else:
            stats["empty"] += 1
        if i % 25 == 0 or i == len(rows):
            print(
                f"  [{i}/{len(rows)}] ok={stats['ok']} empty={stats['empty']} "
                f"miss={stats['miss']} cached={stats['cached']}",
                file=sys.stderr,
            )

    # rewrite full index from disk for consistency when partial runs
    if not args.slugs and (not args.limit or args.limit <= 0) and not args.only_not_on_disk:
        index = []
        df = {}
        for path in sorted(kw_dir.glob("*.json")):
            try:
                rec = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            index.append(_index_row(rec))
            for k in rec.get("keywords") or []:
                n = k.get("norm") or normalize_kw(k.get("name", ""))
                if n:
                    df[n] = df.get(n, 0) + 1

    index_path = out_dir / "keywords_index.jsonl"
    with index_path.open("w") as f:
        for row in sorted(index, key=lambda x: x.get("film_slug") or ""):
            f.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")

    df_path = out_dir / "keywords_df.json"
    df_path.write_text(
        json.dumps(
            {
                "n_docs": len([r for r in index if r.get("n_keywords")]),
                "df": dict(sorted(df.items(), key=lambda x: (-x[1], x[0]))),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )

    stats["index"] = str(index_path)
    stats["df"] = str(df_path)
    stats["n_docs"] = len([r for r in index if r.get("n_keywords")])
    stats["unique_keywords"] = len(df)
    # sample high-signal plot details
    sample = []
    for row in index:
        if row.get("n_keywords", 0) >= 5:
            sample.append(
                {
                    "slug": row["film_slug"],
                    "n": row["n_keywords"],
                    "cats": row.get("by_category"),
                }
            )
            if len(sample) >= 8:
                break
    stats["sample"] = sample
    print(json.dumps(stats, indent=2))
    return 0


def _index_row(rec: dict) -> dict:
    kws = rec.get("keywords") or []
    cats: dict[str, int] = {}
    norms = []
    for k in kws:
        cat = k.get("category") or "other"
        cats[cat] = cats.get(cat, 0) + 1
        norms.append(k.get("norm") or normalize_kw(k.get("name", "")))
    return {
        "film_slug": rec.get("film_slug"),
        "film_title": rec.get("film_title"),
        "tmdb_id": rec.get("tmdb_id"),
        "tmdb_title": rec.get("tmdb_title"),
        "n_keywords": len(kws),
        "by_category": cats,
        "keywords_norm": norms,
        "status": rec.get("status"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
