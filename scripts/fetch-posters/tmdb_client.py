"""TMDB client — strict textless posters via include_image_language=null."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

TMDB_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/original"


@dataclass
class PosterRecord:
    tmdb_id: int
    title: str
    poster_path: str
    poster_url: str
    textless: bool = True
    release_date: str = ""


class TMDBClient:
    def __init__(self, api_key: str, delay: float = 0.35) -> None:
        self.api_key = api_key
        self.delay = delay
        self._last_req = 0.0
        self._use_bearer = len(api_key) > 40
        self._headers = (
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            if self._use_bearer
            else {}
        )
        self._params_base: dict[str, str] = {} if self._use_bearer else {"api_key": api_key}

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_req
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_req = time.monotonic()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        self._throttle()
        p = {**self._params_base, **(params or {})}
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{TMDB_BASE}{path}", headers=self._headers, params=p)
        if r.status_code == 429:
            time.sleep(2.0)
            return self._get(path, params)
        if r.status_code != 200:
            return None
        return r.json()

    def search_movie(self, title: str, year: int | None = None) -> dict[str, Any] | None:
        params: dict[str, Any] = {"query": title}
        if year:
            params["year"] = year
        data = self._get("/search/movie", params)
        if not data:
            return None
        results = data.get("results", [])
        return results[0] if results else None

    def textless_poster_paths(self, movie_id: int) -> list[str]:
        """TMDB textless = iso_639_1 null; fetch via include_image_language=null."""
        data = self._get(f"/movie/{movie_id}/images", {"include_image_language": "null"})
        if not data:
            return []
        paths: list[str] = []
        for p in data.get("posters", []):
            if p.get("iso_639_1") is not None:
                continue
            fp = p.get("file_path")
            if fp:
                paths.append(fp)
        return paths

    def movie_textless_records(self, movie_id: int, title: str = "") -> list[PosterRecord]:
        meta = self._get(f"/movie/{movie_id}")
        if meta:
            title = title or meta.get("title") or ""
        paths = self.textless_poster_paths(movie_id)
        release = (meta or {}).get("release_date") or ""
        return [
            PosterRecord(
                tmdb_id=movie_id,
                title=title,
                poster_path=fp,
                poster_url=f"{IMAGE_BASE}{fp}",
                textless=True,
                release_date=release,
            )
            for fp in paths
        ]

    def discover_movies(self, page: int = 1) -> list[dict[str, Any]]:
        data = self._get(
            "/discover/movie",
            {
                "page": page,
                "sort_by": "popularity.desc",
                "include_adult": "false",
                "include_video": "false",
            },
        )
        if not data:
            return []
        return data.get("results", [])


def load_tmdb_key() -> str:
    key = os.environ.get("TMDB_API_KEY", "").strip().strip('"')
    if key:
        return key
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("TMDB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError(
        "TMDB_API_KEY not set — copy TMDB v4 Read token from projects/poster-to-scene/.env",
    )


def key_fingerprint(api_key: str) -> str:
    """Safe log line — never print full token."""
    if len(api_key) > 40:
        return f"TMDB v4 Bearer (len={len(api_key)}, aud=read)"
    return f"TMDB v3 api_key (len={len(api_key)})"


def slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").title()