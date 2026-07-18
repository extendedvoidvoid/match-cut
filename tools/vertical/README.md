# tools/vertical — center_crop 9:16 (v1)

Offline FFmpeg reframe. **Does not touch** `app/`, `components/`, or `public/`.

## Requirements

- Python 3.12+ (3.14 OK)
- System `ffmpeg` / `ffprobe` (VideoToolbox on macOS when available)
- `typer`, `pyyaml`, `tqdm` (`pip install typer pyyaml tqdm`)

## One command

```bash
cd tools/vertical
PYTHONPATH=. python3 -m vertical_reframe.cli \
  --config config.example.yaml \
  /path/to/video_or_folder \
  -o ./out_vertical
```

Output: `{name}_vertical.mp4` · log: `out_vertical/vertical_reframe.log` (exact ffmpeg cmd per file).

## Smoke test

```bash
cd tools/vertical
PYTHONPATH=. python3 tests/test_smoke.py
```

## v1 scope

- Strategy: `center_crop` only  
- Filter: scale cover → crop → `format=yuv420p`  
- Encode: `h264_videotoolbox` → `hevc_videotoolbox` → `libx264` CRF 18  

See `ARCHITECTURE.md` and `docs/history/VERTICAL_V1_SPEC.md`.
