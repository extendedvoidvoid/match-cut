from __future__ import annotations

import logging
import shlex
import subprocess
from pathlib import Path

from vertical_reframe.config import AppConfig
from vertical_reframe.models import EncodeChoice, VideoInfo

log = logging.getLogger(__name__)


def build_command(
    *,
    cfg: AppConfig,
    info: VideoInfo,
    vf: str,
    encode: EncodeChoice,
    output: Path,
) -> list[str]:
    cmd: list[str] = [
        cfg.ffmpeg,
        "-y",
        "-i",
        str(info.path),
        "-vf",
        vf,
        *encode.extra_args,
    ]
    if info.has_audio:
        cmd.extend(
            [
                "-c:a",
                cfg.audio_codec,
                "-b:a",
                cfg.audio_bitrate,
            ]
        )
    else:
        cmd.append("-an")
    cmd.extend(["-movflags", "+faststart", str(output)])
    return cmd


def run_ffmpeg(cmd: list[str]) -> None:
    # Exact command for César to reproduce / debug
    printable = " ".join(shlex.quote(c) for c in cmd)
    log.info("ffmpeg_cmd %s", printable)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err[-4000:] if err else f"ffmpeg exit {proc.returncode}")
