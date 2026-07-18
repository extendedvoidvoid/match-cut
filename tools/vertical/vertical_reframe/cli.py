from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from vertical_reframe.config import AppConfig
from vertical_reframe.pipeline import run_batch

app = typer.Typer(
    add_completion=False,
    help="Vertical reframe v1: center_crop to 9:16 via system FFmpeg.",
)


def _setup_logging(level: str, log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.FileHandler(log_file)
    fh.setFormatter(fmt)
    root.addHandler(fh)


@app.command()
def main(
    input_path: Path = typer.Argument(..., exists=True, help="Video file or folder"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", exists=True),
    width: Optional[int] = typer.Option(None, "--width"),
    height: Optional[int] = typer.Option(None, "--height"),
    strategy: Optional[str] = typer.Option(None, "--strategy"),
    force_encoder: Optional[str] = typer.Option(
        None, "--force-encoder", help="e.g. h264_videotoolbox, libx264"
    ),
    ffmpeg: str = typer.Option("ffmpeg", "--ffmpeg"),
    ffprobe: str = typer.Option("ffprobe", "--ffprobe"),
) -> None:
    """Convert horizontal/mixed video to centered vertical 9:16 (center_crop only)."""
    cfg = AppConfig.load(
        config,
        output_dir=output_dir,
        width=width,
        height=height,
        strategy=strategy,
        force_encoder=force_encoder,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
    )
    _setup_logging(cfg.log_level, cfg.log_file)
    results = run_batch(input_path, cfg)
    fails = [r for r in results if not r.ok and not r.skipped]
    if fails:
        raise typer.Exit(code=1)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
