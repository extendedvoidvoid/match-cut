# Product lanes — do not mix (César 2026-07-18)

Match-cut monorepo **hosts tools**, but workstreams are **not the same product**.

| Lane | What it is | Where | Station F / essay? |
|------|------------|--------|---------------------|
| **VJ** | Fast ~1 min montages, reels, face-montage experiments | `exports/reels/`, reel scripts, other Grok instance | **No** — not Station F spine |
| **Photo match-cut** | Browser eye-align stills → GIF/MP4 | `app/`, MediaPipe wasm | Tool/demo site; template keep |
| **Essay / vertical** | Landscape show/collection (e.g. Chanel) → 9:16 for **album cover video essay** sibling | `tools/vertical/` + **same César+ brand pack as Olivia** (`album-video-creator`) | **Yes** — one logo/VO/YT MLA |
| **Station F story** | OSS, offline reframe, free mobile, open core | vertical tool + essay path only | **Not** VJ reels |

## Rules for agents

1. **Do not** treat `exports/reels/*` as Station F deliverables.  
2. **Do not** pull VJ montage logic into fashion/album essay pipeline by default.  
3. Chanel / fashion **show** video → vertical reframe → **essay** lane (with album-cover essay grammar later).  
4. Other Grok on VJ = fine; this session does not need reels for Station F.  
5. `mc see` defaults to **essay** tray; use `mc see vj` for reels.

## Home projects

| Project | Lane |
|---------|------|
| `match-cut` reels / modules VJ | VJ |
| `match-cut` `tools/vertical` | Essay / Station F reframe |
| `album-video-creator` (César+) | Album cover essay (music) |
| Fashion show 16:9 → 9:16 | Essay input — **same César+ logo/voice/subs/YT as album essay** (see SHARED_INVENTORY) |

## Station F one-pager (CraftCut) — 3 phone videos

**Site:** `~/projects/César+Start-up/index.html`  
**Not** match-cut reels. Middle column = Chanel.

| File | Label on page | Probe (current) |
|------|----------------|-----------------|
| `César+Start-up/video1.mp4` | Olivia Rodrigo | already **360×640** (~0.6s) |
| `César+Start-up/video2.mp4` | **Chanel Cruise Marseille** | already **360×640** (3s) |
| `César+Start-up/video3.mp4` | Kanye Graduation | already **360×640** (3s) |

So the one-pager demos are **already vertical phone loops**, not raw 16:9 show masters.  
Reframe tool still useful for **longer landscape sources** later; for the page mockups, sources are short 9:16 assets.

Upscale for quality pack:  
`exports/vertical_ready/chanel-cruise-marseille_vertical.mp4` (1080×1920 from video2)  
+ `César+Start-up/video2_vertical.mp4`
