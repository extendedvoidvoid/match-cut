"""Numbered export paths — 001_stem.mp4, 002_stem.mp4, …"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REELS_DIR = ROOT / "exports" / "reels"
REGISTRY = ROOT / "exports" / "registry.json"
NUM_PREFIX = re.compile(r"^(\d{3})_")


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {"next": 1, "entries": []}


def save_registry(data: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(data, indent=2) + "\n")


def allocate_number(stem: str, kind: str = "reel") -> str:
    """Return next 3-digit prefix and register stem."""
    reg = load_registry()
    num = reg["next"]
    reg["next"] = num + 1
    reg["entries"].append({"num": f"{num:03d}", "stem": stem, "kind": kind})
    save_registry(reg)
    return f"{num:03d}"


def numbered_path(stem: str, kind: str = "reel", reels_dir: Path | None = None) -> Path:
    """Allocate number and return exports/reels/NNN_stem.mp4."""
    out_dir = reels_dir or REELS_DIR
    prefix = allocate_number(stem, kind)
    return out_dir / f"{prefix}_{stem}.mp4"


def numbered_iterations_path(video_path: Path) -> Path:
    """Manifest beside numbered video: exports/manifests/NNN_stem_iterations.txt"""
    manifests = video_path.parent.parent / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    return manifests / f"{video_path.stem}_iterations.txt"


def renumber_existing(primary: list[tuple[str, str]]) -> list[Path]:
    """Assign 001..N to known primary reels. primary = [(stem, old_filename), ...]"""
    reg = {"next": 1, "entries": []}
    moved: list[Path] = []
    for stem, old_name in primary:
        old = REELS_DIR / old_name
        if not old.exists():
            continue
        num = reg["next"]
        reg["next"] += 1
        new_name = f"{num:03d}_{stem}.mp4"
        new = REELS_DIR / new_name
        if old != new:
            old.rename(new)
        reg["entries"].append({"num": f"{num:03d}", "stem": stem, "file": new_name, "kind": "reel"})
        moved.append(new)
    save_registry(reg)
    return moved