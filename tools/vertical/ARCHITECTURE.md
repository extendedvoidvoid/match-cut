# tools/vertical — Pass A architecture (no implementation yet)

**Branch:** `feat/fashion-essay-vertical`  
**Spec:** `docs/history/VERTICAL_V1_SPEC.md`  
**Status:** Pass B implemented — see `vertical_reframe/` + `README.md`

---

## Answer to collab filter-graph question

**Drive center_crop with scale-then-crop, not crop-only.**

```text
scale=w=OUT_W:h=OUT_H:force_original_aspect_ratio=increase,crop=OUT_W:OUT_H,format=yuv420p
```

- Covers target 9:16 box from 16:9 (and mixed AR) without letterboxing.  
- `format=yuv420p` locked (Opus): mobile / QuickTime / VT play safety.  
- One filter chain before HW or software encode.  
- **Prefer subprocess + argv**; log the **exact ffmpeg command per file**.  
- ffmpeg-python only if graph + VT stay readable.

OpenCV / numpy: **not required for v1.** Flag if someone tries to pull them for center_crop.

---

## Module layout (proposed)

```text
tools/vertical/
  ARCHITECTURE.md          # this file (Pass A)
  README.md                # Pass B: install + one command (stub OK later)
  pyproject.toml           # Pass B: optional package metadata
  vertical_reframe/
    __init__.py
    cli.py                 # typer entry: vertical-reframe / main
    config.py              # load YAML + CLI overrides
    models.py              # dataclasses: Job, VideoInfo, EncodeChoice
    probe.py               # ffprobe + encoder detection
    ffmpeg_run.py          # build argv, run, log
    pipeline.py            # batch/single orchestration
    strategies/
      __init__.py
      base.py              # ReframeStrategy protocol
      center_crop.py       # v1 only
      # smart_subject.py   # NOT in v1 — stub file optional with NotImplementedError only if needed for import clarity; prefer absent
  tests/
    test_smoke.py          # one short clip; skip if no sample
  config.example.yaml
```

Temporary monorepo home. Migrate per `docs/ROADMAP_VIDEO_ESSAY_APP.md`.

Optional later (not v1): thin `mc vertical` → calls this CLI. Only if zero logic duplication.

---

## `ReframeStrategy` interface

```python
# strategies/base.py — conceptual (Pass B types exact)

from typing import Protocol
from pathlib import Path

class ReframeStrategy(Protocol):
    name: str  # "center_crop"

    def video_filter(self, *, src_w: int, src_h: int, out_w: int, out_h: int) -> str:
        """Return ffmpeg -vf / filter_complex video chain (no encode flags)."""
        ...

class CenterCrop:
    name = "center_crop"

    def video_filter(self, *, src_w: int, src_h: int, out_w: int, out_h: int) -> str:
        # v1 ignores src_* for formula (cover+crop is scale-based);
        # src kept for logging and future strategies.
        return (
            f"scale=w={out_w}:h={out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h}"
        )
```

Future `SmartSubject` implements same protocol; returns time-varying crop only when designed (not v1).

---

## YAML schema (`config.example.yaml`)

```yaml
# tools/vertical/config.example.yaml
output_dir: ./out_vertical
width: 1080
height: 1920
strategy: center_crop   # only center_crop implemented in v1
extensions: [".mp4", ".mov", ".mkv", ".avi", ".m4v"]

encode:
  # detection order (first available wins unless forced)
  prefer:
    - h264_videotoolbox   # macOS default — free mobile friendly
    - hevc_videotoolbox   # optional quality/size; CLI can force
    - libx264
  libx264:
    crf: 18
    preset: slow
  videotoolbox_h264:
    # bitrate or quality mode — Pass B pick one documented default
    # e.g. allow_sw: true is N/A; use -b:v or -q:v per probe
    video_bitrate: "6M"
  audio:
    codec: aac
    bitrate: "192k"
    # or copy if compatible — Pass B: prefer aac re-encode for mobile safety

logging:
  level: INFO
  file: ./out_vertical/vertical_reframe.log
```

**CLI overrides config** (typer): `--input`, `--output-dir`, `--width`, `--height`, `--strategy`, `--force-encoder`, `--config`.

Output name: `{stem}_vertical.mp4` in `output_dir`.

---

## Encoder detection (visible chain)

```text
1. If force_encoder set → use it (fail loud if missing)
2. Else probe `ffmpeg -hide_banner -encoders`
3. Prefer first match in encode.prefer that exists
4. Log: "encoder=h264_videotoolbox" or "encoder=libx264 crf=18 preset=slow"
5. Never assume NVIDIA on Mac; never assume VT on Windows
```

Windows note (v1 doc only): `h264_nvenc` / `libx264` in prefer list later; Mac path is primary for César now.

---

## FFmpeg command templates

### Probe

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,duration,codec_name \
  -show_entries format=duration \
  -of json INPUT
```

### center_crop + H.264 VideoToolbox

```bash
ffmpeg -y -i INPUT \
  -vf "scale=w=1080:h=1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p" \
  -c:v h264_videotoolbox -b:v 6M \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  OUTPUT_vertical.mp4
```

### center_crop + libx264 fallback

```bash
ffmpeg -y -i INPUT \
  -vf "scale=w=1080:h=1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p" \
  -c:v libx264 -crf 18 -preset slow \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  OUTPUT_vertical.mp4
```

### Optional HEVC VT (flag `--encoder hevc_videotoolbox`)

```bash
ffmpeg -y -i INPUT \
  -vf "scale=w=1080:h=1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p" \
  -c:v hevc_videotoolbox -b:v 5M -tag:v hvc1 \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  OUTPUT_vertical.mp4
```

**Audio:** re-encode AAC for mobile predictability unless Pass B proves stream copy safe and shorter.

**Pixel format:** if VT fails on odd pix_fmt, insert `format=nv12` or `yuv420p` before encode (Pass B smoke will show). Prefer documenting fallback in probe logs.

---

## Pipeline flow

```text
cli
  → load config + resolve paths (file | folder glob)
  → for each input:
        probe video stream (skip + warn if none)
        strategy.video_filter(...)
        pick encoder
        ffmpeg_run → {stem}_vertical.mp4
        verify: ffprobe out w/h; optional duration check
  → summary counts (ok / skip / fail)
```

Batch continues on single-file failure.

---

## Ambiguities / pushbacks

| Topic | Stance |
|-------|--------|
| ffmpeg-python vs subprocess | Prefer **subprocess + argv** for legibility and VT flags; ffmpeg-python optional wrapper only if it stays clear |
| Variable frame rate sources | Document: may need `-vsync cfr` later; v1 best-effort ±1 frame on CFR |
| HDR / 10-bit | v1: convert to yuv420p/nv12 for mobile; no HDR preserve claim |
| Multiple video streams | Use first video stream only |
| Image sequences as “video” | Out of scope v1 |
| Tying into Next demo of 3 videos | Out of scope v1 — offline CLI first |

---

## Smoke test plan (Pass B)

```bash
# after implement
python -m vertical_reframe.cli \
  --input tests/fixtures/sample_landscape_10s.mp4 \
  --output-dir /tmp/vertical_smoke \
  --config tools/vertical/config.example.yaml

ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 \
  /tmp/vertical_smoke/sample_landscape_10s_vertical.mp4
# expect: 1080,1920
```

Fixture: César provides short landscape clip (Marseille-class or synthetic). Do not invent copyrighted test media in git if policy forbids — generate solid color 16:9 with ffmpeg in test setup if needed:

```bash
ffmpeg -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 3 -c:v libx264 -pix_fmt yuv420p tests/fixtures/sample_landscape_10s.mp4
```

---

## Dependencies (v1)

```text
python 3.12+
typer
tqdm
pyyaml
# system: ffmpeg, ffprobe with videotoolbox on macOS when available
# NOT: moviepy, opencv (v1)
```

---

## Pass A complete when

- [x] Module layout written  
- [x] ReframeStrategy + CenterCrop filter decision  
- [x] YAML schema  
- [x] FFmpeg templates + encoder chain  
- [x] Ambiguities called out  
- [ ] César confirms → Pass B implement  

**No production Python modules in this pass** (by design).
