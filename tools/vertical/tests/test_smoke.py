"""Smoke: generate short landscape clip, reframe, assert 1080x1920."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vertical_reframe.config import AppConfig
from vertical_reframe.pipeline import process_one


def test_center_crop_smoke(tmp_path: Path) -> None:
    sample = tmp_path / "sample_landscape.mp4"
    out_dir = tmp_path / "out"
    # 3s 1920x1080 test pattern
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1920x1080:rate=30",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(sample),
        ],
        check=True,
        capture_output=True,
    )
    cfg = AppConfig.load(None, output_dir=out_dir, width=1080, height=1920)
    result = process_one(sample, cfg)
    assert result.ok, result.message
    assert result.output_path is not None
    assert result.output_path.exists()
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(result.output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip() == "1080,1920"


if __name__ == "__main__":
    # runnable without pytest
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_center_crop_smoke(Path(d))
    print("smoke OK")
