"""Load strict textless poster pool — unique file_path, grouped by film_slug."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "assets" / "movie-posters" / "manifest.jsonl"
SLUG_MAP = ROOT / "assets" / "movie-posters" / "film_slug_map.jsonl"


@dataclass
class PosterAsset:
    path: str
    poster_path: str  # TMDB file_path — global dedup key
    tmdb_id: int
    title: str
    film_slug: str = ""
    source: str = ""


def load_textless_pool() -> list[PosterAsset]:
    pool: dict[str, PosterAsset] = {}
    if MANIFEST.exists():
        for line in MANIFEST.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if not d.get("textless", False):
                continue
            if not Path(d.get("local_path", "")).is_file():
                continue
            key = d.get("poster_path") or d["local_path"]
            pool[key] = PosterAsset(
                path=d["local_path"],
                poster_path=d.get("poster_path", ""),
                tmdb_id=d["tmdb_id"],
                title=d.get("title", ""),
                film_slug=d.get("film_slug", ""),
                source=d.get("source", ""),
            )
    return list(pool.values())


class UniquePosterDeck:
    """Each TMDB poster_path used at most once."""

    def __init__(self, assets: list[PosterAsset], seed: int) -> None:
        by_slug: dict[str, list[PosterAsset]] = {}
        for a in assets:
            if a.film_slug:
                by_slug.setdefault(a.film_slug, []).append(a)
        self._by_slug = {k: v[:] for k, v in by_slug.items()}
        random.Random(seed + 31).shuffle(assets)
        self._fallback = assets[:]
        self._used: set[str] = set()

    def draw_for_slug(self, film_slug: str) -> PosterAsset | None:
        bucket = self._by_slug.get(film_slug, [])
        while bucket:
            a = bucket.pop(0)
            if a.poster_path in self._used:
                continue
            self._used.add(a.poster_path)
            return a
        return None

    def draw(self) -> PosterAsset | None:
        while self._fallback:
            a = self._fallback.pop(0)
            if a.poster_path in self._used:
                continue
            self._used.add(a.poster_path)
            return a
        return None

    def __len__(self) -> int:
        return sum(1 for a in self._fallback if a.poster_path not in self._used)

    @property
    def used_count(self) -> int:
        return len(self._used)

    def available_for_slug(self, film_slug: str) -> int:
        return sum(1 for a in self._by_slug.get(film_slug, []) if a.poster_path not in self._used)