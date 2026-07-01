# AGENTS.md — Match Cut Generator

**Canonical rules:** [docs/GOOD_PRACTICES.md](docs/GOOD_PRACTICES.md)  
**Enforcement:** `npm run check:practices` + CI + `.cursor/rules/good-practices.mdc`

---

## Project identity

- **Path:** `/Users/alexphoenix/projects/match-cut`
- **Alias:** `mc` / `matchcut` (shell) · `./bin/mc` (repo)
- **Fork:** `origin` → `extendedvoidvoid/match-cut` · `upstream` → `sanjogbora/match-cut`
- **What it is:** Client-side Next.js — photos → MediaPipe → eye align → preview → GIF/MP4
- **Privacy:** Images never leave the browser

---

## MUST (hardcoded)

1. **Client-side only** — face, align, export in browser; no photo upload APIs without approval
2. **Export contract** — `` `match-cut-${Date.now()}` `` basename; GIF and MP4 both work
3. **Module boundaries** — logic in `lib/`; UI in `components/`; do not grow `app/page.tsx`
4. **Surgical diffs** — smallest change; no unrelated refactors
5. **Docs location** — no `*_FIX.md` at root; use `docs/history/` or `docs/decisions/`
6. **CI green** — `lint` + `build` + `check:practices` before done
7. **Smoke after pipeline edits** — 2+ faces → align → MP4 @ 720p in Chrome

## MUST NOT (hardcoded)

1. Server-side image storage or third-party vision APIs (without approval)
2. Breaking `next.config.js` wasm/COOP without export retest
3. Changing export filename/format defaults without README update
4. Next.js major upgrade in same PR as feature work
5. Deleting `docs/history/` or user exports in `Face Aligntment /`
6. Force-push `main`

---

## Touch map

| Area | Files |
|------|-------|
| Orchestration | `app/page.tsx` → prefer new `hooks/` |
| Face / eyes | `lib/faceDetection.ts`, `lib/imageAlignment.ts` |
| Export | `lib/videoExport.ts`, `components/ExportOptions.tsx` |
| Beat / audio | `lib/beatDetection.ts`, `lib/audioManager.ts` |
| WASM | `next.config.js` |

---

## Workflow

1. Read `docs/GOOD_PRACTICES.md` + `docs/STRUCTURE.md`
2. Plan minimal change
3. Implement
4. `mc lint && mc build && mc check`
5. Manual smoke if `lib/` face/export touched
6. Update docs if behavior or structure changed

---

## When in doubt

Ask before: new dependencies, server routes with images, export contract changes.