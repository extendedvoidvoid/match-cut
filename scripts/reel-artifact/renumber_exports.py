#!/usr/bin/env python3
"""One-shot: assign 001..N to primary ship reels."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from export_naming import REELS_DIR, renumber_existing

PRIMARY = [
    ("insta_reel_vj_60s", "insta_reel_vj_60s.mp4"),
    ("insta_reel_closeup_1-30_60s", "insta_reel_closeup_1-30_60s.mp4"),
    ("insta_reel_paysage_1-30_60s", "insta_reel_paysage_1-30_60s.mp4"),
]


def main() -> int:
    moved = renumber_existing(PRIMARY)
    print(json.dumps({
        "renumbered": [str(p.name) for p in moved],
        "registry": str(REELS_DIR.parent / "registry.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())