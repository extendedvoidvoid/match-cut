# Timing — vertical reframe measured + full essay pipeline estimates

**Host:** Apple M3 Max · ffmpeg 8.1.1 · `h264_videotoolbox`  
**Date:** 2026-07-18 · branch `feat/fashion-essay-vertical`  
**Agent-run** (not César). Synthetic 1920×1080 testsrc (not heavy 4K grade).

---

## 1) Measured: center_crop only (`tools/vertical`)

Wall clock = probe + encode + verify (whole CLI path).

| Source duration | Wall time | vs realtime | Notes |
|-----------------|-----------|-------------|--------|
| **5 s** | **~1.00 s** | ~0.20× | VT H.264 |
| **30 s** | **~2.87 s** | ~0.10× | VT H.264 |

**Extrapolate center_crop only** (≈0.10× RT from 30s sample):

| Source | Est. wall |
|--------|-----------|
| 60 s | ~6 s |
| 90 s | ~9 s |
| 3 min | ~17 s |
| 5 min | ~29 s |

**Caveats:** real 4K / high-bitrate show footage slower; first encoder probe cold; libx264 fallback much slower (often ~1–3× realtime or worse).

---

## 2) Estimates: full “online” fashion essay pipeline (not built)

Rough **first-cut** calendar/wall for **one ~60–90 s vertical essay** (scripted, FR or EN).  
Ranges = optimistic (local + free tiers warm) → pessimistic (API queue, retakes, human gates).

| Stage | What | Est. wall (one episode) | Depends on |
|-------|------|-------------------------|------------|
| A. Research / text | topic outline, facts, script draft | **5–25 min** human+LLM · **0.5–3 min** pure LLM if template fixed | web search quality; Mistral cheap OK |
| B. Fact check / human gate | César Approve script | **2–15 min** | human only |
| C. B-roll / source film | already on disk vs fetch | **0** if local · **5–40 min** acquire/rights | film-grab / your Marseille-class files |
| D. **Vertical reframe** | center_crop v1 | **~5–15 s** for ~60–90 s 1080p source on M3 Max VT | measured path above |
| E. Subs / captions | ASR + SRT + burn or sidecar | **0.5–3 min** local Whisper-class · **1–8 min** API | length, language, accuracy pass |
| F. Cloned / TTS voice | generate VO + align | **0.5–4 min** local TTS · **1–10 min** API clone + QC | gate: must not ship bad clone |
| G. Mix A/V | VO + music bed + ducking | **0.5–3 min** scripted · **5–20 min** first handcraft | not in v1 tool |
| H. Final encode 9:16 | already vertical or re-mux | **5–40 s** VT | |
| I. Publish pack | title, cover still, upload free mobile | **2–10 min** | human |

### Ballpark totals (one 60–90 s episode)

| Mode | Est. |
|------|------|
| **Machine-only automated path** (script already approved, local assets, local ASR/TTS) | **~5–20 min** wall first time setup excluded |
| **With human script gate + light QC** (realistic Station F demo) | **~20–60 min** per episode |
| **Heavy research + rights + retakes** | **hours** |

**center_crop share of total:** usually **&lt;1 min** — not the bottleneck.  
Bottlenecks: **script quality, voice QC, sub accuracy, asset rights, human Approve.**

---

## 3) What this means for Station F story

- Open **reframe** is cheap and fast on M3 Max (measured).  
- “Online video + text search + subs + cloned voice” is a **pipeline of stages**; only D is shipped.  
- Demo honesty: show fast reframe **now**; quote full-essay times as **estimate ranges**, not promises.

---

## 4) Re-run measure

```bash
cd tools/vertical
# logs include wall=…s ratio=…x realtime after each OK
PYTHONPATH=. python3 -m vertical_reframe /path/to/clip -o /tmp/out_vertical
```
