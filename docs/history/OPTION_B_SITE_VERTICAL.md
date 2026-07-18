# Option B — vertical asset on site (versioned)

**Date:** 2026-07-18  
**Branch:** `feat/fashion-essay-vertical`

## What changed

| Action | Detail |
|--------|--------|
| **Added** | `public/effect-demo-vertical.mp4` (1080×1920, from center_crop) |
| **Kept** | `public/effect demo.mp4` (original landscape — **not deleted**) |
| **About page** | demo `<video src>` → `/effect-demo-vertical.mp4` |
| **Backup** | `docs/history/site_versions/about_page.tsx.YYYYMMDD.bak` |
| **Ready pack** | `exports/vertical_ready/` (same vertical + other A test outputs) |

## Restore landscape demo

1. In `app/about/page.tsx`, set `src="/effect demo.mp4"`  
   or copy from `docs/history/site_versions/about_page.tsx.*.bak`  
2. Optional: remove `public/effect-demo-vertical.mp4` if unused  

## Not done (no Marseille master)

Middle “Chanel collection” slot still needs César’s landscape master path when available → reframe → same pattern (`public/…-vertical.mp4` + versioned page edit).

## Site template rule

Do not erase `app/` / `components/` / `public/` originals. New assets get new names. Page edits get bak under `docs/history/site_versions/`.
