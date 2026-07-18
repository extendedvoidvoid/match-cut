# Questions for Opus — OCR + title-card reframe (bulletproof)

**PAUSED until César confirms shared brand inventory.**  
See `album-video-creator/docs/CESAR_ESSAY_SHARED_INVENTORY.md` — fashion reuses **same** César+ logo/VO/YT MLA as Olivia album essays; OCR is only for **geometry on title cards**, not a new brand stack.

**Context for Opus (short):**  
Essay lane (not VJ). Source is official **16:9** Chanel Cruise Marseille show. Center-crop to 9:16 **destroys burn-in title cards** at open (and maybe close). Product goal: keep Chanel on-screen text readable, then add **existing César+ logo** (same as Olivia), **existing cloned VO**, **existing YouTube subs pipeline**. Need OCR offline-friendly (local M3) that drives crop only.

**Evidence (Grok inspected):**

| t | 16:9 | After center 9:16 |
|---|------|-------------------|
| 0s | black | black |
| ~1s | aerial Cité Radieuse, no title yet | architecture only |
| ~2s | centered burn-in: **CHANEL / CRUISE 2024/25 SHOW / MARSEILLE** | **text clipped** (letters cut L/R) |

Full vertical: `exports/vertical_ready/chanel-cruise-marseille_full_vertical.mp4`  
Frames: `exports/vertical_ready/ocr_inspect/`  
16:9 source: `exports/vertical_sources/chanel_cruise_2024_25_show_QALjeAXxDbY.mp4`

---

## Product pipeline (next stages — order)

1. **Detect title-card segments** (open / maybe close) via OCR + scene heuristics.  
2. **Reframe strategy switch:** geometric `center_crop` for runway; **text-aware crop** (or letterbox/fit) when OCR finds brand/title block.  
3. **Preserve Chanel text** (do not re-typeset fake Chanel unless César decides overlay rebuild).  
4. Add **César+ logo** (safe zone, no collide with Chanel type).  
5. **VO** (cloned César voice) multi-language.  
6. **Subs** for YouTube (SRT/ASS, burn or sidecar).  
7. Final 9:16 encode (VT).

---

## Questions for Opus (please answer short + recommend)

### A. OCR engine (local / offline first)

1. **Default OCR stack on Apple Silicon 2026** for sparse white brand type over photo/video:  
   Apple Vision · Tesseract · PaddleOCR · EasyOCR · other?  
   Which is best for **large spaced caps** (CHANEL) + multi-line centered stack?

2. Should we OCR **every frame**, **1 fps**, or **scene-change only** for a 14 min show? Cost/accuracy tradeoff on M3 Max.

3. How to handle **low-contrast / translucent** white type on bright concrete (as in this open card)?

4. **Language pack:** EN titles only for Chanel cards, or FR too? Multi-script later?

5. **Confidence threshold** to trust a box as “title card” vs false positive (signage on building, subtitles later in show)?

### B. Title-card → crop policy

6. When OCR finds a text block, preferred reframe:  
   - (a) crop so **text bbox center** = frame center  
   - (b) **fit entire bbox** with margin (may letterbox / zoom less)  
   - (c) **pad/blur sides** keep full 16:9 width of text  
   Which for luxury brand cards?

7. **Temporal smooth:** once title card starts, freeze crop for N seconds vs track text box each frame?

8. How to detect **title card end** (text fades) to switch back to `center_crop` / future `smart_subject`?

9. **Open vs end cards:** same detector, or separate end-credit rules (smaller type, legal lines)?

### C. Output schema (so Grok can implement)

10. Propose a **JSONL schema** per segment, e.g.  
    `{t0, t1, kind: title|runway|end, texts[], bboxes_norm[], crop_cx_cy, strategy}`  
    Minimum fields for v0.

11. Should OCR write **ASS/SRT of burn-in text** for QC only, or also feed the **spoken essay script** (usually separate)?

### D. Stack boundaries

12. Confirm: OCR/title-card module lives in **local Python** (essay lane), **not** browser match-cut. OK?

13. AGPL/Tesseract license OK for public fork vs Apple Vision only on César’s Mac?

14. Interaction with existing **AlbumVideos** essay pipeline (already has FR/IT VO for Chanel Marseille): OCR is only for **reframing**, not re-authoring scripts — agree?

### E. Failure modes (bulletproof)

15. Checklist of failure cases we must test: black frames, text only 0.5s, text animated in, two columns, end card dense legal text, no text for 10 min mid-show.

16. **Human gate:** auto-crop title cards with preview stills before batch full 14 min — recommended?

---

## What Grok will do after Opus answers

- Spec `title_card` strategy next to `center_crop` (no smart_subject yet unless needed).  
- Offline OCR pass → JSONL → reframe open/close → rest center_crop.  
- Then logo / VO / subs as separate modules (AlbumVideos / César+ already close).

---

## César product reminder (for both models)

| Keep | Add |
|------|-----|
| Chanel burn-in text (readable) | César+ logo |
| 16:9 master for geometry | Cloned voice multi-lang |
| Essay lane ≠ VJ reels | YouTube subs |
