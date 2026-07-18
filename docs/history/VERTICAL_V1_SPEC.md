# Vertical reframe v1 — single source of decisions

**Branch:** `feat/fashion-essay-vertical` (private working name)  
**Status:** Pass B implemented · smoke OK · not public  
**Date:** 2026-07-18

## Goal (v1 only)

Convert horizontal or mixed-aspect **video** to vertical **9:16** (default 1080×1920) using **`center_crop` only**.  
File or folder in → `{name}_vertical.mp4` + log.

## Why (product)

Client match-cut handles **photos** → eye align → GIF/MP4.  
It does **not** reframe landscape **video** (e.g. collection/show 16:9) for Stories/Reels shells. That is this tool.

## Opus 4.8 — keep as law

| Keep | Reject for v1 |
|------|----------------|
| Option 1: center_crop first | smart_subject + montage + music in one PR |
| DoD: exact size, ±1 frame, HW fallback | Vague “Premiere quality” without metrics |
| Two-pass: architecture then code | One-shot mega-script |
| moviepy out | Pull moviepy “just in case” |
| Name smoother later (EMA / one-euro) when smart_subject ships | Fake auto_reframe now |

## Collab contract (human-legible)

- No easter eggs or model-only jokes in identifiers or comments.
- Everything readable by César without a decoder ring.
- Say disagreements in prose (PR / this doc), not in clever names.

## Paris brand coherence (not public naming)

Two essay lines, one city brand world:

| Line | Home | Spine |
|------|------|--------|
| Album cover video essay | `album-video-creator` (César+) | Animated cover + VO |
| Fashion video essay | this branch → later own app | Show/collection film → vertical |

Shared later: 9:16, free mobile encode, local-first, open core.  
Do **not** invent a third visual language.

## Station F constraints (engineering only — no marketing strings required in code)

- Open core path offline on M3 Max  
- Cheap Mistral optional later (not required for center_crop)  
- Free Apple/Google mobile → prefer **H.264** VT default  

## Website / HTML template (do not erase)

The **browser site** (Next app UI) is good and César will reuse it as a template for other projects.

| Keep | Rule |
|------|------|
| `app/` · `components/` · `public/` · styles | **Do not delete** for vertical reframe work |
| Demo media under `public/` | Keep; reframe CLI is separate offline tool |
| Future site edits | **Version** — new branch or `docs/history/` snapshot / tag before redesign |

Vertical reframe v1 lives in `tools/vertical/` only. It must **not** replace or gut the website.

## Out of scope v1

- `smart_subject`, `auto_reframe_like`  
- Montage, crossfades, captions, music ducking  
- Next.js / FFmpeg.wasm rewrite · **no site erase**  
- Public product name / Station F landing  
- YOLO / RF-DETR / SAM / cloud or local VLM in the reframe path  

### Parked design (Opus 2026-07-18 + Grok answer)

| Topic | Decision |
|-------|----------|
| Runtime | Browser = photo MediaPipe only; heavy detect = **local Python modules** |
| smart_subject | LATER module; `SubjectDetector`; **RF-DETR core Apache 2.0** default (XL/2XL PML); YOLO26 AGPL flagged |
| Tracking | ByteTrack-class default; **SAM 3.1** multiplex/occlusion escalation |
| Vision APIs | No upload / no cloud vision; optional **local** VLM only |
| Overlap | Align with existing `classify.*` / modules — no second parallel zoo |

## Definition of done (provable)

1. Output exactly target dimensions (default 1080×1920)  
2. fps and duration match source within ±1 frame  
3. No dropped/duplicated frames on straight center_crop  
4. Corrupt file: skip + log warning; batch continues  
5. Encoder detection visible in log: VT → libx264 CRF 18  
6. One smoke command + short sample clip  
7. No moviepy, no OpenCV required for center_crop  

## Filter-graph decision (Pass A)

**Q:** crop alone vs scale-then-crop on 4K?

**A (locked for implement Pass B):**

```text
Always: scale so the frame *covers* the target box, then center crop, then yuv420p.
  scale=w={W}:h={H}:force_original_aspect_ratio=increase
  crop={W}:{H}
  format=yuv420p
Then encode (VT or libx264).

Rationale: pure crop on 16:9 4K→1080×1920 under-covers height without prior scale;
scale-with-increase + crop is the standard cover behavior and stays one filter chain
compatible with hardware encode after filters.
format=yuv420p: Opus ACK — mobile / QuickTime / VT play safety (avoid green-tint / won't-play).
Log the exact ffmpeg command per file (repro / debug).
```

If source is already ≥ target AR in the useful direction, same graph still correct (scale may be near-identity then crop).

## Process

1. **Pass A (done here):** layout, interface, YAML, ffmpeg templates — no production code  
2. Human confirm  
3. **Pass B:** implement + smoke  

## Related

- `docs/ROADMAP_VIDEO_ESSAY_APP.md` — leave monorepo when green  
- `tools/vertical/ARCHITECTURE.md` — Pass A detail  
