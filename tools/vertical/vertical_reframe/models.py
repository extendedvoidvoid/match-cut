from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    width: int
    height: int
    fps: float | None
    duration: float | None
    has_audio: bool


@dataclass(frozen=True)
class EncodeChoice:
    codec: str  # h264_videotoolbox | hevc_videotoolbox | libx264
    extra_args: list[str]


@dataclass
class JobResult:
    input_path: Path
    output_path: Path | None
    ok: bool
    skipped: bool
    message: str
    wall_seconds: float | None = None
    source_duration: float | None = None
