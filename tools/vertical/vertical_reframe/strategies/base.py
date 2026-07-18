from __future__ import annotations

from typing import Protocol


class ReframeStrategy(Protocol):
    name: str

    def video_filter(self, *, src_w: int, src_h: int, out_w: int, out_h: int) -> str:
        """Return ffmpeg -vf chain (no encode flags)."""
        ...
