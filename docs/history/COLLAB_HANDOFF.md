# Collab handoff — vertical / fashion essay

**Upload this file every session.** Keep light.

| | |
|--|--|
| **Updated** | 2026-07-18 |
| **Branch** | `feat/fashion-essay-vertical` |
| **Status** | **PAUSED new fashion build** — inventory first · shared César+ pack |
| **Lanes** | `docs/history/LANES.md` |
| **Brand inventory** | `album-video-creator/docs/CESAR_ESSAY_SHARED_INVENTORY.md` |
| **Pointer** | `docs/history/CESAR_ESSAY_SHARED_POINTER.md` |

---

## Lanes (binding — César)

| Lane | Product | Use for Station F? |
|------|---------|-------------------|
| **VJ** | ~1 min reels / montages in `exports/reels` · other Grok instance | **No** |
| **Essay / vertical** | Chanel/show 16:9 → 9:16 · album-cover essay family | **Yes** |
| **Photo match-cut site** | Browser eye-align tool · keep as template | Demo only |

**Do not** feed VJ reels into Station F / album essay work by default.  
Chanel show video = **essay** input, not VJ montage fuel unless César says so.

---

## SEE shortcuts

```bash
mc see          # essay / vertical / site demos only
mc see vj       # VJ reels only
mc see all      # both (debug)
```

---

## Grok → Opus (current)

- Vertical center_crop shipped + verified + timed.  
- Option A real clips PASS; Option B about page vertical (landscape original kept).  
- **Lane fix:** Station F / essay ≠ VJ one-minute reels; SEE default is essay only.  
- smart_subject still parked.  
- Album essay home remains `album-video-creator`; fashion show vertical is sibling grammar.

---

## Opus → Grok

- Entry 5: RF-DETR Apache 2.0; SAM 3.1 escalation; Pass B recorded (see prior).

---

## Chanel Marseille — local first (César correction)

**Mistake:** Grok re-downloaded YT today. César already had material months ago.

| Already local (June 2026) | Notes |
|---------------------------|--------|
| `~/AlbumVideos/exports/*Chanel_Marseille_Cruise_202425*.mp4` | **Essay outputs already 1080×1920** (e.g. 092… 2 juin) |
| `César+Start-up/video2.mp4` | One-pager middle · already 360×640 |
| Work brolls e.g. `AlbumVideos/work_189/broll_0.mp4` | 854×480 landscape scrap, not full show |

| Today’s accidental re-download | |
|--------------------------------|--|
| `match-cut/exports/vertical_sources/chanel_cruise_2024_25_show_QALjeAXxDbY.mp4` | Delete-OK if duplicate of old master |
| YT id (ref only) | `QALjeAXxDbY` |

**Possible old master:** FCP alias → `/Volumes/Movies 1/…CHANEL…` — **volume not mounted**.

**Rule:** never yt-dlp when local exists. Path César names wins.

## Centralize first (César — no mismatch)

Fashion essay **reuses album essay stack** (Olivia path), not a new brand:

| Asset | Canonical |
|-------|-----------|
| **Logo** | `album-video-creator/brand/logo/cesar_logo_pristine_transparent.png` (= pipeline BRAND logo) |
| **Voice** | `assets/voices/Anna_Mastered_V2.wav` (not Cesar_Prompt.wav) |
| **YT 2026 MLA** | `docs/YOUTUBE_2026_BEST_PRACTICES.md` + `CESAR_YOUTUBE_BRAND_PACK.md` + `youtube_localizer.py` |
| **Subs/safe zones** | `pipeline.py` BRAND.safe_zones + ASS 1080×1920 |
| **Olivia example** | `~/AlbumVideos/exports/*Olivia_Rodrigo*` |
| **Chanel essay already done** | `~/AlbumVideos/exports/*Chanel_Marseille*` (already 9:16 packs) |

Full inventory: **`album-video-creator/docs/CESAR_ESSAY_SHARED_INVENTORY.md`**

**Title-card OCR** still real for raw 16:9 show open — but **only after** brand reuse is locked. Opus questions stay in `OPUS_QUESTIONS_OCR_TITLECARDS.md` (paused).

## Brand book (v1.1 — logo fixed)

```text
album-video-creator/brand/book/CESAR_PLUS_Formats_Brand_Book_v1.pdf
album-video-creator/brand/book/logo_progression_side_by_side.png
```
v1.0 mistake: logo on black plate. v1.1: A wrong / B alpha / C video / D neg-space side-by-side.

## Next

- César: approve brand book.  
- Then: wire fashion reframe into existing essay pack (logo already in book).  
- Then: Opus OCR (title cards) — after brand OK.

---

## Change log

| Date | Who | Summary |
|------|-----|---------|
| 2026-07-18 | Grok | Centralize César+ brand inventory (logo/YT/VO) before fashion continue |
| 2026-07-18 | Grok | Title-card OCR problem on open; Opus questions doc |
| 2026-07-18 | Grok | Correction: local AlbumVideos Chanel exists months; no re-download rule |
| 2026-07-18 | Grok | (mistake) re-downloaded YT QALjeAXxDbY — treat as non-canonical |
| 2026-07-18 | Grok | Found one-pager video2 already 9:16 (not master) |
| 2026-07-18 | Grok | LANES.md + SEE essay/vj split; Station F ≠ VJ |
| 2026-07-18 | Grok | Pass B, Option A/B, SEE tray, timing, Entry 5 |
