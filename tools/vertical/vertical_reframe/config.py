from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "output_dir": "./out_vertical",
    "width": 1080,
    "height": 1920,
    "strategy": "center_crop",
    "extensions": [".mp4", ".mov", ".mkv", ".avi", ".m4v"],
    "encode": {
        "prefer": ["h264_videotoolbox", "hevc_videotoolbox", "libx264"],
        "libx264": {"crf": 18, "preset": "slow"},
        "videotoolbox_h264": {"video_bitrate": "6M"},
        "videotoolbox_hevc": {"video_bitrate": "5M"},
        "audio": {"codec": "aac", "bitrate": "192k"},
    },
    "logging": {"level": "INFO", "file": "./out_vertical/vertical_reframe.log"},
}


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class AppConfig:
    output_dir: Path
    width: int
    height: int
    strategy: str
    extensions: list[str]
    encode_prefer: list[str]
    libx264_crf: int
    libx264_preset: str
    vt_h264_bitrate: str
    vt_hevc_bitrate: str
    audio_codec: str
    audio_bitrate: str
    log_level: str
    log_file: Path
    force_encoder: str | None = None
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"

    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
        *,
        output_dir: Path | None = None,
        width: int | None = None,
        height: int | None = None,
        strategy: str | None = None,
        force_encoder: str | None = None,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
    ) -> AppConfig:
        data = dict(DEFAULTS)
        if config_path is not None:
            raw = yaml.safe_load(config_path.read_text()) or {}
            if not isinstance(raw, dict):
                raise ValueError(f"Config must be a mapping: {config_path}")
            data = _deep_merge(data, raw)

        enc = data.get("encode") or {}
        libx = enc.get("libx264") or {}
        vth = enc.get("videotoolbox_h264") or {}
        vte = enc.get("videotoolbox_hevc") or {}
        aud = enc.get("audio") or {}
        log = data.get("logging") or {}

        out = Path(output_dir if output_dir is not None else data["output_dir"])
        log_file = Path(log.get("file") or (out / "vertical_reframe.log"))

        return cls(
            output_dir=out,
            width=int(width if width is not None else data["width"]),
            height=int(height if height is not None else data["height"]),
            strategy=str(strategy if strategy is not None else data["strategy"]),
            extensions=[str(e).lower() if str(e).startswith(".") else f".{e}".lower() for e in data.get("extensions", DEFAULTS["extensions"])],
            encode_prefer=list(enc.get("prefer") or DEFAULTS["encode"]["prefer"]),
            libx264_crf=int(libx.get("crf", 18)),
            libx264_preset=str(libx.get("preset", "slow")),
            vt_h264_bitrate=str(vth.get("video_bitrate", "6M")),
            vt_hevc_bitrate=str(vte.get("video_bitrate", "5M")),
            audio_codec=str(aud.get("codec", "aac")),
            audio_bitrate=str(aud.get("bitrate", "192k")),
            log_level=str(log.get("level", "INFO")),
            log_file=log_file,
            force_encoder=force_encoder,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
        )
