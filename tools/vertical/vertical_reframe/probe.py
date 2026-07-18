from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from vertical_reframe.config import AppConfig
from vertical_reframe.models import EncodeChoice, VideoInfo

log = logging.getLogger(__name__)


def _run_json(ffprobe: str, args: list[str]) -> dict:
    cmd = [ffprobe, "-v", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffprobe failed: {' '.join(cmd)}")
    return json.loads(proc.stdout or "{}")


def probe_video(path: Path, ffprobe: str = "ffprobe") -> VideoInfo:
    data = _run_json(
        ffprobe,
        [
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,duration,codec_type",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
    )
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError(f"No video stream: {path}")
    s = streams[0]
    w = int(s.get("width") or 0)
    h = int(s.get("height") or 0)
    if w <= 0 or h <= 0:
        raise RuntimeError(f"Invalid dimensions: {path}")

    fps: float | None = None
    r = s.get("r_frame_rate") or ""
    if isinstance(r, str) and "/" in r:
        num, den = r.split("/", 1)
        try:
            den_f = float(den)
            if den_f:
                fps = float(num) / den_f
        except ValueError:
            fps = None

    duration: float | None = None
    for key in (s.get("duration"), (data.get("format") or {}).get("duration")):
        if key is None:
            continue
        try:
            duration = float(key)
            break
        except (TypeError, ValueError):
            pass

    # audio presence
    has_audio = False
    try:
        adata = _run_json(
            ffprobe,
            ["-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
        )
        has_audio = bool(adata.get("streams"))
    except RuntimeError:
        has_audio = False

    return VideoInfo(
        path=path,
        width=w,
        height=h,
        fps=fps,
        duration=duration,
        has_audio=has_audio,
    )


def list_encoders(ffmpeg: str = "ffmpeg") -> set[str]:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        log.warning("Could not list encoders: %s", proc.stderr.strip())
        return set()
    found: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        # lines like: V....D h264_videotoolbox    VideoToolbox...
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            found.add(parts[1])
    return found


def choose_encoder(cfg: AppConfig) -> EncodeChoice:
    available = list_encoders(cfg.ffmpeg)
    order = [cfg.force_encoder] if cfg.force_encoder else list(cfg.encode_prefer)
    order = [c for c in order if c]

    for codec in order:
        if codec not in available and cfg.force_encoder:
            raise RuntimeError(f"Forced encoder not available: {codec}")
        if codec not in available:
            continue
        if codec == "h264_videotoolbox":
            extra = ["-c:v", "h264_videotoolbox", "-b:v", cfg.vt_h264_bitrate]
            log.info("encoder=%s bitrate=%s", codec, cfg.vt_h264_bitrate)
            return EncodeChoice(codec=codec, extra_args=extra)
        if codec == "hevc_videotoolbox":
            extra = [
                "-c:v",
                "hevc_videotoolbox",
                "-b:v",
                cfg.vt_hevc_bitrate,
                "-tag:v",
                "hvc1",
            ]
            log.info("encoder=%s bitrate=%s", codec, cfg.vt_hevc_bitrate)
            return EncodeChoice(codec=codec, extra_args=extra)
        if codec == "libx264":
            extra = [
                "-c:v",
                "libx264",
                "-crf",
                str(cfg.libx264_crf),
                "-preset",
                cfg.libx264_preset,
            ]
            log.info(
                "encoder=libx264 crf=%s preset=%s",
                cfg.libx264_crf,
                cfg.libx264_preset,
            )
            return EncodeChoice(codec=codec, extra_args=extra)
        # unknown but present
        log.info("encoder=%s (generic)", codec)
        return EncodeChoice(codec=codec, extra_args=["-c:v", codec])

    # last resort
    log.warning("No preferred encoder found; using libx264")
    return EncodeChoice(
        codec="libx264",
        extra_args=[
            "-c:v",
            "libx264",
            "-crf",
            str(cfg.libx264_crf),
            "-preset",
            cfg.libx264_preset,
        ],
    )
