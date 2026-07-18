from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from vertical_reframe.config import AppConfig
from vertical_reframe.ffmpeg_run import build_command, run_ffmpeg
from vertical_reframe.models import JobResult
from vertical_reframe.probe import choose_encoder, probe_video
from vertical_reframe.strategies import get_strategy

log = logging.getLogger(__name__)


def collect_inputs(path: Path, extensions: list[str]) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(path)
    ext_set = {e.lower() for e in extensions}
    files = sorted(
        p for p in path.iterdir() if p.is_file() and p.suffix.lower() in ext_set
    )
    return files


def output_path_for(inp: Path, output_dir: Path) -> Path:
    return output_dir / f"{inp.stem}_vertical.mp4"


def verify_output(path: Path, expect_w: int, expect_h: int, ffprobe: str) -> None:
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe verify failed: {proc.stderr.strip()}")
    line = (proc.stdout or "").strip()
    parts = line.split(",")
    if len(parts) < 2:
        raise RuntimeError(f"Unexpected probe: {line!r}")
    w, h = int(parts[0]), int(parts[1])
    if w != expect_w or h != expect_h:
        raise RuntimeError(f"Bad size {w}x{h}, expected {expect_w}x{expect_h}")


def process_one(path: Path, cfg: AppConfig) -> JobResult:
    out = output_path_for(path, cfg.output_dir)
    t0 = time.perf_counter()
    try:
        info = probe_video(path, cfg.ffprobe)
    except Exception as e:
        wall = time.perf_counter() - t0
        log.warning("SKIP %s — %s (wall=%.3fs)", path, e, wall)
        return JobResult(
            path, None, ok=False, skipped=True, message=str(e), wall_seconds=wall
        )

    try:
        strategy = get_strategy(cfg.strategy)
        vf = strategy.video_filter(
            src_w=info.width,
            src_h=info.height,
            out_w=cfg.width,
            out_h=cfg.height,
        )
        encode = choose_encoder(cfg)
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_command(cfg=cfg, info=info, vf=vf, encode=encode, output=out)
        run_ffmpeg(cmd)
        verify_output(out, cfg.width, cfg.height, cfg.ffprobe)
        wall = time.perf_counter() - t0
        src_dur = info.duration
        rtx = (wall / src_dur) if src_dur and src_dur > 0 else None
        if rtx is not None:
            log.info(
                "OK %s → %s wall=%.3fs source=%.3fs ratio=%.2fx realtime encoder=%s",
                path.name,
                out.name,
                wall,
                src_dur,
                rtx,
                encode.codec,
            )
        else:
            log.info(
                "OK %s → %s wall=%.3fs encoder=%s",
                path.name,
                out.name,
                wall,
                encode.codec,
            )
        return JobResult(
            path,
            out,
            ok=True,
            skipped=False,
            message="ok",
            wall_seconds=wall,
            source_duration=src_dur,
        )
    except Exception as e:
        wall = time.perf_counter() - t0
        log.error("FAIL %s — %s (wall=%.3fs)", path, e, wall)
        return JobResult(
            path,
            out if out.exists() else None,
            ok=False,
            skipped=False,
            message=str(e),
            wall_seconds=wall,
        )


def run_batch(input_path: Path, cfg: AppConfig) -> list[JobResult]:
    paths = collect_inputs(input_path, cfg.extensions)
    if not paths:
        log.warning("No inputs under %s", input_path)
        return []
    results: list[JobResult] = []
    try:
        from tqdm import tqdm

        iterator = tqdm(paths, desc="vertical", unit="file")
    except ImportError:
        iterator = paths

    for p in iterator:
        results.append(process_one(p, cfg))
    ok = sum(1 for r in results if r.ok)
    skip = sum(1 for r in results if r.skipped)
    fail = sum(1 for r in results if not r.ok and not r.skipped)
    log.info("summary ok=%s skip=%s fail=%s total=%s", ok, skip, fail, len(results))
    return results
