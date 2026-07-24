#!/usr/bin/env python3
"""LOCAL rank v2 — genre + film-grab tags + TMDB keyword affinity → brute queue.

Principal signal: IMDb-style keyword affinity (via TMDB cache).
No fixed global keyword allow-list — intent seeds in config/intent_profiles.json.
No vision. Online meta only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "assets" / "film-grab"
DEFAULT_INTENT = ROOT / "config" / "intent_profiles.json"

from kw_taxonomy import (  # noqa: E402
    affinity_score,
    annotate_keywords,
    load_intent_profile,
    normalize_kw,
)


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def load_keyword_cache(out_dir: Path) -> dict[str, list[dict]]:
    """slug → annotated keywords."""
    by: dict[str, list[dict]] = {}
    kw_dir = out_dir / "keywords"
    if kw_dir.is_dir():
        for path in kw_dir.glob("*.json"):
            try:
                rec = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            slug = rec.get("film_slug") or path.stem
            by[slug] = rec.get("keywords") or []
    # fallback index norms only
    for r in load_jsonl(out_dir / "keywords_index.jsonl"):
        slug = r.get("film_slug")
        if not slug or slug in by:
            continue
        norms = r.get("keywords_norm") or []
        by[slug] = annotate_keywords(norms)
    return by


def load_df(out_dir: Path) -> tuple[dict[str, int], int]:
    path = out_dir / "keywords_df.json"
    if not path.is_file():
        return {}, 0
    data = json.loads(path.read_text())
    return dict(data.get("df") or {}), int(data.get("n_docs") or 0)


def tag_score(tags: list[str], tag_boost: dict[str, float]) -> float:
    """Once per boost key (no stack from kiss, gay-kiss, kiss-on-forehead…)."""
    s = 0.0
    hit_keys: set[str] = set()
    for t in tags:
        tl = t.lower()
        for key, w in tag_boost.items():
            if key in hit_keys:
                continue
            if key in tl:
                s += float(w)
                hit_keys.add(key)
    return s


def genre_score(genres: list[str], genre_bonus: dict[str, float]) -> float:
    s = 0.0
    for g in genres:
        s += float(genre_bonus.get(g.lower(), 0.0))
    return s


def score_row(
    r: dict,
    *,
    annotated: list[dict],
    profile: dict,
    df_map: dict[str, int],
    n_docs: int,
) -> tuple[float, dict]:
    seeds = list(profile.get("seeds") or [])
    demote = list(profile.get("demote_seeds") or [])
    # film-grab tags act as soft seeds (not global allow-list)
    for t in r.get("tags") or []:
        n = normalize_kw(t)
        if n and n not in seeds:
            seeds.append(n)

    aff, br = affinity_score(
        annotated,
        seeds=seeds,
        demote_seeds=demote,
        category_weights=profile.get("category_weights"),
        df_map=df_map,
        n_docs=n_docs,
    )
    g = genre_score(list(r.get("genres") or []), profile.get("genre_bonus") or {})
    t = tag_score(list(r.get("tags") or []), profile.get("tag_boost") or {})
    # weak title/slug seed match already covered if keywords empty: slug tokens vs seeds
    slug_aff = 0.0
    if not annotated:
        from kw_taxonomy import seed_match

        slug_aff = seed_match(normalize_kw(r.get("film_slug") or ""), seeds) * 0.5
        title_aff = seed_match(normalize_kw(r.get("film_title") or ""), seeds) * 0.5
        slug_aff = max(slug_aff, title_aff)

    disk_pen = -0.5 if r.get("on_disk") else 0.0
    total = aff * 1.4 + g + t + slug_aff + disk_pen
    return total, {
        "kw_affinity": round(aff, 4),
        "genre": round(g, 4),
        "tags": round(t, 4),
        "slug_fallback": round(slug_aff, 4),
        "disk_pen": disk_pen,
        "kw_breakdown": br,
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description="Rank meta candidates with keyword affinity (no vision)"
    )
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--top-k", type=int, default=30, help="BRUTE this many not-on-disk films")
    p.add_argument("--min-score", type=float, default=2.0)
    p.add_argument("--include-on-disk", action="store_true")
    p.add_argument("--intent", type=str, default=None)
    p.add_argument("--intent-config", type=Path, default=DEFAULT_INTENT)
    p.add_argument(
        "--require-keywords",
        action="store_true",
        help="drop rows with no keyword cache (strict principal mode)",
    )
    args = p.parse_args()

    out_dir = args.output.expanduser().resolve()
    try:
        profile = load_intent_profile(args.intent_config, args.intent)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2

    genre_rows = load_jsonl(out_dir / "candidates_read.jsonl")
    if not genre_rows:
        genre_rows = load_jsonl(out_dir / "posts_by_genre.jsonl")
    tag_rows = load_jsonl(out_dir / "candidates_tags.jsonl")
    kw_by = load_keyword_cache(out_dir)
    df_map, n_docs = load_df(out_dir)

    by: dict[str, dict] = {}
    for r in genre_rows:
        slug = r.get("film_slug")
        if not slug:
            continue
        by[slug] = {
            "film_slug": slug,
            "post_url": r.get("post_url"),
            "genres": list(r.get("genres") or []),
            "tags": list(r.get("tags") or []),
            "on_disk": bool(r.get("on_disk")),
            "source": r.get("source") or "genre",
            "film_title": r.get("film_title") or slug.replace("-", " ").title(),
        }
    for r in tag_rows:
        slug = r.get("film_slug")
        if not slug:
            continue
        if slug not in by:
            by[slug] = {
                "film_slug": slug,
                "post_url": r.get("post_url"),
                "genres": list(r.get("genres") or []),
                "tags": list(r.get("tags") or []),
                "on_disk": bool(r.get("on_disk")),
                "source": "tag",
                "film_title": r.get("film_title") or slug.replace("-", " ").title(),
            }
        else:
            for t in r.get("tags") or []:
                if t not in by[slug]["tags"]:
                    by[slug]["tags"].append(t)
            if not by[slug].get("post_url"):
                by[slug]["post_url"] = r.get("post_url")
            by[slug]["source"] = "genre+tag"

    # include keyword-only titles already cached (growth beyond genre/tag lists)
    for slug, kws in kw_by.items():
        if slug in by:
            continue
        disk = (out_dir / slug).is_dir() and any((out_dir / slug).glob("*.jpg"))
        by[slug] = {
            "film_slug": slug,
            "post_url": None,
            "genres": [],
            "tags": [],
            "on_disk": disk,
            "source": "keywords_only",
            "film_title": slug.replace("-", " ").title(),
        }

    ranked = []
    n_with_kw = 0
    for r in by.values():
        annotated = kw_by.get(r["film_slug"]) or []
        if annotated:
            n_with_kw += 1
        if args.require_keywords and not annotated:
            continue
        total, detail = score_row(
            r, annotated=annotated, profile=profile, df_map=df_map, n_docs=n_docs
        )
        r = dict(r)
        r["read_score"] = round(total, 4)
        r["score_detail"] = detail
        r["n_keywords"] = len(annotated)
        r["kw_categories"] = (detail.get("kw_breakdown") or {}).get("by_category") or {}
        r["intent"] = profile.get("intent")
        ranked.append(r)

    ranked.sort(key=lambda x: (-x["read_score"], x.get("on_disk", False), x["film_slug"]))

    all_path = out_dir / "candidates_ranked.jsonl"
    with all_path.open("w") as f:
        for r in ranked:
            f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")

    brute = []
    for r in ranked:
        if r["read_score"] < args.min_score:
            continue
        if r.get("on_disk") and not args.include_on_disk:
            continue
        if not r.get("post_url"):
            continue
        brute.append(r)
        if len(brute) >= args.top_k:
            break

    brute_path = out_dir / "candidates_brute.jsonl"
    with brute_path.open("w") as f:
        for r in brute:
            row = dict(r)
            row["see_pass"] = True
            row["rank_source"] = "meta_kw_affinity_v2"
            f.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")

    summary = {
        "module": "acquire.rank_meta",
        "version": "2.0.0",
        "intent": profile.get("intent"),
        "merged": len(ranked),
        "with_keywords": n_with_kw,
        "n_docs_idf": n_docs,
        "brute_top_k": len(brute),
        "min_score": args.min_score,
        "top_brute": [
            {
                "slug": r["film_slug"],
                "score": r["read_score"],
                "kw_aff": (r.get("score_detail") or {}).get("kw_affinity"),
                "n_kw": r.get("n_keywords"),
                "genres": r.get("genres"),
                "tags": (r.get("tags") or [])[:6],
                "hits": ((r.get("score_detail") or {}).get("kw_breakdown") or {}).get(
                    "top_hits", []
                )[:4],
            }
            for r in brute[:15]
        ],
        "top_ranked_any": [
            {
                "slug": r["film_slug"],
                "score": r["read_score"],
                "on_disk": r.get("on_disk"),
                "kw_aff": (r.get("score_detail") or {}).get("kw_affinity"),
                "n_kw": r.get("n_keywords"),
            }
            for r in ranked[:12]
        ],
        "ranked_all": str(all_path),
        "output": str(brute_path),
        "policy": "principal=keyword affinity (IMDb taxonomy via TMDB); no vision; no global KW allow-list",
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
