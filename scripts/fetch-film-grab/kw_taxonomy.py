#!/usr/bin/env python3
"""IMDb-style keyword taxonomy: normalize, category annotate, intent affinity.

No global allow-list of keywords. Categories mirror IMDb contribution guide:
  plot_detail | subgenre | timeframe | franchise | other

TMDB returns flat names; we infer category by morphology + light patterns.
Affinity = sum category_weight * idf * seed_match  (seeds live in intent profile).
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable

# --- normalize ----------------------------------------------------------------

_DASH = re.compile(r"[\s_/]+")
_NON = re.compile(r"[^a-z0-9\-]+")
_MULTI = re.compile(r"-{2,}")


def normalize_kw(name: str) -> str:
    """IMDb-style: lower-case, dash-separated tokens."""
    s = (name or "").strip().lower().replace("'", "")
    s = _DASH.sub("-", s)
    s = _NON.sub("", s)
    s = _MULTI.sub("-", s).strip("-")
    return s


def tokens(name: str) -> set[str]:
    n = normalize_kw(name)
    return {t for t in n.split("-") if t and len(t) > 1}


# --- category annotation (IMDb mirror) ----------------------------------------

# Genre-ish tails used in IMDb subgenre keywords (e.g. feel-good-romance).
_SUBGENRE_TAILS = (
    "romance",
    "comedy",
    "drama",
    "horror",
    "thriller",
    "action",
    "adventure",
    "animation",
    "western",
    "musical",
    "fantasy",
    "mystery",
    "crime",
    "war",
    "sport",
    "family",
    "documentary",
    "reality-tv",
    "anime-animation",
)

_TIMEFRAME_RE = re.compile(
    r"("
    r"^\d{3,4}s?$"  # 1960s, 1945
    r"|^\d{1,2}th-century$"
    r"|century$"
    r"|decade$"
    r"|era$"
    r"|period$"
    r"|world-war"
    r"|middle-ages"
    r"|victorian"
    r"|edwardian"
    r"|elizabethan"
    r"|medieval"
    r"|prehistoric"
    r"|futuristic"
    r"|near-future"
    r"|dystopian-future"
    r")",
    re.I,
)

_OTHER_PREFIX = (
    "based-on-",
    "reference-to-",
    "inspired-by-",
    "adapted-from-",
)
_OTHER_EXACT = {
    "f-rated",
    "triple-f-rated",
    "tv-special",
    "tv-mini-series",
    "independent-film",
    "cult-film",
    "directorial-debut",
    "film-debut",
    "based-on-novel-or-book",
    "based-on-true-story",
    "based-on-play-or-musical",
    "woman-director",
}

# Morphological franchise cues only (not a scoring allow-list of titles).
_FRANCHISE_MORPH = re.compile(r"(-franchise|-universe|-saga|-cinematic-universe)$")


def categorize_keyword(name: str) -> str:
    """Return one of: plot_detail, subgenre, timeframe, franchise, other."""
    n = normalize_kw(name)
    if not n:
        return "other"
    if n.endswith("-character") or n.endswith("-episode"):
        return "other"
    if n in _OTHER_EXACT or any(n.startswith(p) for p in _OTHER_PREFIX):
        return "other"
    if _FRANCHISE_MORPH.search(n):
        return "franchise"
    if _TIMEFRAME_RE.search(n) or n.endswith("-era") or n.endswith("-period"):
        return "timeframe"
    # compound subgenre: X-romance, dark-comedy, superhero-action, …
    parts = n.split("-")
    if len(parts) >= 2 and parts[-1] in _SUBGENRE_TAILS:
        return "subgenre"
    if n in _SUBGENRE_TAILS:
        return "subgenre"
    # open-ended default — IMDb plot detail
    return "plot_detail"


def annotate_keywords(raw: Iterable[str | dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("keyword") or ""
            kid = item.get("id")
        else:
            name = str(item)
            kid = None
        n = normalize_kw(name)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(
            {
                "id": kid,
                "name": name if isinstance(name, str) else n,
                "norm": n,
                "category": categorize_keyword(n),
            }
        )
    return out


# --- affinity -----------------------------------------------------------------

def seed_match(kw_norm: str, seeds: Iterable[str]) -> float:
    """0..1 match of keyword against intent seeds (token-first; no fuzzy mid-word).

    Short seeds (love, kiss) only match exact keyword or whole dash-tokens —
    blocks child-marriage←marriage noise and loved←love mid-token hits.
    """
    if not kw_norm:
        return 0.0
    kt = tokens(kw_norm)
    best = 0.0
    for seed in seeds:
        sn = normalize_kw(seed)
        if not sn:
            continue
        if kw_norm == sn:
            best = max(best, 1.0)
            continue
        st = tokens(sn)
        if not st:
            continue
        # whole-token containment (seed tokens ⊆ keyword tokens)
        if st <= kt:
            # denser overlap scores higher
            j = len(st) / max(len(kt), 1)
            best = max(best, 0.85 + 0.15 * min(j, 1.0))
            continue
        if kt and st and (kt <= st):
            best = max(best, 0.8)
            continue
        inter = len(st & kt)
        if inter:
            j = inter / max(len(st | kt), 1)
            # require at least one contentful token (>3 chars) when partial
            if any(len(t) > 3 for t in (st & kt)):
                best = max(best, 0.5 + 0.4 * j)
            continue
        # multi-word seed as dash-bounded phrase inside longer kw only
        if len(st) >= 2 and f"-{sn}-" in f"-{kw_norm}-":
            best = max(best, 0.9)
    return best


def idf(df: int, n_docs: int) -> float:
    """Smooth IDF; rare plot details beat ubiquitous ones."""
    if n_docs <= 0:
        return 1.0
    return math.log(1.0 + n_docs / (1.0 + max(df, 0)))


def _primary_stem(kw_norm: str, seeds: Iterable[str]) -> str:
    """Dominant seed token for diminishing-returns grouping."""
    kt = tokens(kw_norm)
    for seed in seeds:
        st = tokens(normalize_kw(seed))
        if st and st <= kt:
            return sorted(st, key=len)[-1]
    if kt:
        return max(kt, key=len)
    return kw_norm


def affinity_score(
    annotated: list[dict[str, Any]],
    *,
    seeds: list[str],
    demote_seeds: list[str] | None = None,
    category_weights: dict[str, float] | None = None,
    df_map: dict[str, int] | None = None,
    n_docs: int = 0,
) -> tuple[float, dict[str, Any]]:
    """Principal keyword score for one title. Returns (score, breakdown)."""
    cw = category_weights or {
        "plot_detail": 1.0,
        "subgenre": 0.7,
        "timeframe": 0.25,
        "franchise": 0.15,
        "other": 0.1,
    }
    demote_seeds = demote_seeds or []
    df_map = df_map or {}
    pos = 0.0
    neg = 0.0
    hits: list[dict[str, Any]] = []
    # diminishing returns per primary content token (stop marriage×N pile-up)
    stem_count: dict[str, int] = {}
    for kw in annotated:
        n = kw["norm"]
        cat = kw.get("category") or categorize_keyword(n)
        w_cat = float(cw.get(cat, 0.2))
        m = seed_match(n, seeds)
        d = seed_match(n, demote_seeds)
        w_idf = idf(df_map.get(n, 1), n_docs) if n_docs else 1.0
        if m > 0:
            stem = _primary_stem(n, seeds)
            k = stem_count.get(stem, 0)
            stem_count[stem] = k + 1
            decay = 1.0 / (1.0 + 0.65 * k)
            contrib = w_cat * m * w_idf * decay
            pos += contrib
            hits.append(
                {
                    "norm": n,
                    "category": cat,
                    "match": round(m, 3),
                    "contrib": round(contrib, 4),
                    "sign": "+",
                    "stem": stem,
                }
            )
        if d > 0:
            contrib = w_cat * d * w_idf * 0.8
            neg += contrib
            hits.append(
                {
                    "norm": n,
                    "category": cat,
                    "match": round(d, 3),
                    "contrib": round(-contrib, 4),
                    "sign": "-",
                }
            )
    hits.sort(key=lambda h: abs(h["contrib"]), reverse=True)
    score = pos - neg
    return score, {
        "pos": round(pos, 4),
        "neg": round(neg, 4),
        "n_kw": len(annotated),
        "top_hits": hits[:8],
        "by_category": _count_cats(annotated),
    }


def _count_cats(annotated: list[dict[str, Any]]) -> dict[str, int]:
    c: dict[str, int] = {}
    for kw in annotated:
        cat = kw.get("category") or "other"
        c[cat] = c.get(cat, 0) + 1
    return c


def load_intent_profile(path, intent: str | None = None) -> dict[str, Any]:
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text())
    intent = intent or data.get("default_intent") or "kiss_romance"
    profiles = data.get("intents") or {}
    if intent not in profiles:
        raise KeyError(f"unknown intent {intent!r}; have {sorted(profiles)}")
    prof = dict(profiles[intent])
    prof["intent"] = intent
    prof["category_weights"] = data.get("category_weights") or {}
    return prof
