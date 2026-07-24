#!/usr/bin/env python3
"""Mix VJ post effects onto an export reel.

Modes
  negative-toggle  — keep source (smudge/smear edges) + invert every Nth frame
  interleave       — A/B frame interleave of two finished reels
  blend            — 50/50 pixel blend of two reels (same length preferred)

Default: negative-toggle on the latest face-montage smudge reel.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

from export_naming import numbered_iterations_path, numbered_path

ROOT = Path(__file__).resolve().parents[2]
REELS = ROOT / "exports" / "reels"
DEFAULT_STEM = "insta_reel_fx_smudge_neg_toggle_60s"
SMUDGE_CANDIDATES = (
    "011_insta_reel_face_montage_6-30_60s.mp4",
    "010_insta_reel_face_montage_6-30_60s.mp4",
    "009_insta_reel_face_montage_6-30_60s.mp4",
    "insta_reel_extend_12-24_60s.mp4",
    "001_insta_reel_vj_60s.mp4",
)


def resolve_default_smudge() -> Path:
    for name in SMUDGE_CANDIDATES:
        p = REELS / name
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"no smudge reel in {REELS}; pass --input (face_montage or extend fill)"
    )


def apply_negative(frame: np.ndarray) -> np.ndarray:
    return cv2.bitwise_not(frame)


def open_capture(path: Path) -> tuple[cv2.VideoCapture, float, int, int, int]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    return cap, fps, w, h, n


def open_writer(path: Path, fps: float, w: int, h: int) -> cv2.VideoWriter:
    """Write mp4 via ffmpeg pipe when possible; else OpenCV mp4v."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError(f"cannot open VideoWriter for {path}")
    return writer


def reencode_mpeg4(src: Path, dst: Path) -> None:
    """Match reel-artifact encode (mpeg4 q:v 5 yuv420p)."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-c:v", "mpeg4", "-q:v", "5", "-pix_fmt", "yuv420p",
            str(dst),
        ],
        check=True,
    )


def mode_negative_toggle(
    src: Path,
    out_path: Path,
    *,
    every: int,
    phase: int,
    invert_on: bool,
    iterations_path: Path | None,
) -> dict:
    """Keep smudge source; invert frames where (i + phase) % every == 0."""
    if every < 1:
        raise ValueError("--every must be >= 1")
    cap, fps, w, h, _n_hint = open_capture(src)
    log = [
        "# match-cut fx_mix — smudge source + on/off negative",
        f"# source={src.name}",
        f"# mode=negative_toggle  every={every}  phase={phase}  invert_on={invert_on}",
        f"# fps={fps:.4f}  size={w}x{h}",
        "",
    ]
    n = 0
    inverted = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="fx-mix-neg-") as tmp:
            raw = Path(tmp) / "raw.mp4"
            writer = open_writer(raw, fps, w, h)
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    hit = ((n + phase) % every) == 0
                    do_neg = hit if invert_on else not hit
                    if do_neg:
                        frame = apply_negative(frame)
                        inverted += 1
                        tag = "NEG"
                    else:
                        tag = "POS"
                    writer.write(frame)
                    log.append(f"frame={n:04d}  state={tag}")
                    n += 1
            finally:
                writer.release()
            if n == 0:
                raise RuntimeError(f"no frames in {src}")
            reencode_mpeg4(raw, out_path)
    finally:
        cap.release()

    iter_path = iterations_path or numbered_iterations_path(out_path)
    iter_path.write_text("\n".join(log) + "\n")
    return {
        "mode": "negative_toggle",
        "source": str(src),
        "output": str(out_path),
        "iterations": str(iter_path),
        "frames": n,
        "inverted": inverted,
        "every": every,
        "phase": phase,
        "fps": fps,
        "size": [w, h],
    }


def mode_interleave(
    a: Path,
    b: Path,
    out_path: Path,
    *,
    start_with: str,
    iterations_path: Path | None,
) -> dict:
    """Alternate frames A,B,A,B… (shorter stream ends the mix)."""
    cap_a, fps_a, w_a, h_a, _ = open_capture(a)
    cap_b, fps_b, _w_b, _h_b, _ = open_capture(b)
    fps = min(fps_a, fps_b) if fps_a and fps_b else (fps_a or fps_b or 24.0)
    w, h = w_a, h_a
    log = [
        "# match-cut fx_mix — interleave two reels",
        f"# A={a.name}  B={b.name}  start_with={start_with}",
        f"# fps={fps:.4f}  size={w}x{h} (A geometry; B resized if needed)",
        "",
    ]
    n = 0
    use_a = start_with.lower() == "a"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="fx-mix-il-") as tmp:
            raw = Path(tmp) / "raw.mp4"
            writer = open_writer(raw, fps, w, h)
            try:
                while True:
                    cap = cap_a if use_a else cap_b
                    ok, frame = cap.read()
                    if not ok:
                        break
                    if frame.shape[1] != w or frame.shape[0] != h:
                        frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
                    tag = "A" if use_a else "B"
                    writer.write(frame)
                    log.append(f"frame={n:04d}  from={tag}")
                    n += 1
                    use_a = not use_a
            finally:
                writer.release()
            if n == 0:
                raise RuntimeError("no frames from either input")
            reencode_mpeg4(raw, out_path)
    finally:
        cap_a.release()
        cap_b.release()

    iter_path = iterations_path or numbered_iterations_path(out_path)
    iter_path.write_text("\n".join(log) + "\n")
    return {
        "mode": "interleave",
        "source_a": str(a),
        "source_b": str(b),
        "output": str(out_path),
        "iterations": str(iter_path),
        "frames": n,
        "fps": fps,
        "size": [w, h],
    }


def mode_blend(
    a: Path,
    b: Path,
    out_path: Path,
    *,
    alpha: float,
    iterations_path: Path | None,
) -> dict:
    """Pixel blend: out = (1-alpha)*A + alpha*B."""
    alpha = float(np.clip(alpha, 0.0, 1.0))
    cap_a, fps_a, w, h, _ = open_capture(a)
    cap_b, fps_b, _, _, _ = open_capture(b)
    fps = min(fps_a, fps_b) if fps_a and fps_b else (fps_a or fps_b or 24.0)
    log = [
        "# match-cut fx_mix — blend two reels",
        f"# A={a.name}  B={b.name}  alpha={alpha:.3f}",
        f"# out = (1-a)*A + a*B",
        "",
    ]
    n = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="fx-mix-bl-") as tmp:
            raw = Path(tmp) / "raw.mp4"
            writer = open_writer(raw, fps, w, h)
            try:
                while True:
                    ok_a, fa = cap_a.read()
                    ok_b, fb = cap_b.read()
                    if not ok_a or not ok_b:
                        break
                    if fb.shape[1] != w or fb.shape[0] != h:
                        fb = cv2.resize(fb, (w, h), interpolation=cv2.INTER_AREA)
                    if fa.shape[1] != w or fa.shape[0] != h:
                        fa = cv2.resize(fa, (w, h), interpolation=cv2.INTER_AREA)
                    out = cv2.addWeighted(fa, 1.0 - alpha, fb, alpha, 0.0)
                    writer.write(out)
                    log.append(f"frame={n:04d}  blend={alpha:.3f}")
                    n += 1
            finally:
                writer.release()
            if n == 0:
                raise RuntimeError("no overlapping frames")
            reencode_mpeg4(raw, out_path)
    finally:
        cap_a.release()
        cap_b.release()

    iter_path = iterations_path or numbered_iterations_path(out_path)
    iter_path.write_text("\n".join(log) + "\n")
    return {
        "mode": "blend",
        "source_a": str(a),
        "source_b": str(b),
        "output": str(out_path),
        "iterations": str(iter_path),
        "frames": n,
        "alpha": alpha,
        "fps": fps,
        "size": [w, h],
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description="Mix smudge-edge reel with on/off negative (or interleave/blend two reels)",
    )
    p.add_argument(
        "--mode",
        choices=("negative-toggle", "interleave", "blend"),
        default="negative-toggle",
        help="negative-toggle=smudge src + alternate invert (default)",
    )
    p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Smudge/smear source reel (default: latest face_montage in exports/reels)",
    )
    p.add_argument("--a", type=Path, default=None, help="Reel A (interleave/blend)")
    p.add_argument("--b", type=Path, default=None, help="Reel B (interleave/blend)")
    p.add_argument(
        "--every",
        type=int,
        default=2,
        help="Invert every N frames (2 = on/off flicker). Default 2",
    )
    p.add_argument(
        "--phase",
        type=int,
        default=1,
        help="Offset for toggle (1 = first frame POS, second NEG). Default 1",
    )
    p.add_argument(
        "--invert-on",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When hit: invert (default true). --no-invert-on keeps hit frames positive",
    )
    p.add_argument("--alpha", type=float, default=0.5, help="Blend weight of B (default 0.5)")
    p.add_argument(
        "--start-with",
        choices=("a", "b"),
        default="a",
        help="Interleave first frame from A or B",
    )
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--no-number", action="store_true")
    p.add_argument("--stem", type=str, default=DEFAULT_STEM)
    p.add_argument("--iterations", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    def resolve_out() -> Path:
        if args.output is not None:
            return args.output
        if args.no_number:
            return Path.home() / "Downloads" / f"{args.stem}.mp4"
        return numbered_path(args.stem)

    if args.mode == "negative-toggle":
        src = args.input or args.a or resolve_default_smudge()
        if not src.is_file():
            print(f"error: missing input {src}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(json.dumps({
                "mode": "negative_toggle",
                "source": str(src),
                "output": f"exports/reels/NNN_{args.stem}.mp4",
                "every": args.every,
                "phase": args.phase,
            }, indent=2))
            return 0
        out_path = resolve_out()
        report = mode_negative_toggle(
            src,
            out_path,
            every=args.every,
            phase=args.phase,
            invert_on=args.invert_on,
            iterations_path=args.iterations,
        )
    else:
        a = args.a or args.input
        b = args.b
        if a is None or b is None:
            print("error: interleave/blend need --a and --b", file=sys.stderr)
            return 1
        if not a.is_file() or not b.is_file():
            print(f"error: missing A={a} B={b}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(json.dumps({
                "mode": args.mode,
                "a": str(a),
                "b": str(b),
                "output": f"exports/reels/NNN_{args.stem}.mp4",
            }, indent=2))
            return 0
        out_path = resolve_out()
        if args.mode == "interleave":
            report = mode_interleave(
                a, b, out_path,
                start_with=args.start_with,
                iterations_path=args.iterations,
            )
        else:
            report = mode_blend(
                a, b, out_path,
                alpha=args.alpha,
                iterations_path=args.iterations,
            )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
