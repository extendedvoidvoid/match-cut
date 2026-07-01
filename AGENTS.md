# AGENTS.md — Match Cut Generator

Rules for any AI agent working in `/Users/alexphoenix/projects/match-cut`.

---

## Project identity

- **What it is:** Client-side Next.js app — upload photos → MediaPipe face/eye detect → align → preview → export GIF/MP4.
- **What it is not:** A server upload pipeline, a Python/ffmpeg CLI, or part of `album-video-creator` / `ai-media-studio` (yet).
- **Privacy model:** All image processing runs in the browser. Do not add server-side image upload without explicit user approval.

---

## Unbreakable rules

1. **Browser-first processing**
   - Face detection, alignment, and export must stay client-side unless the user explicitly requests a server fallback.
   - Never send user photos to external APIs.

2. **Surgical changes**
   - Smallest diff that solves the task. No drive-by refactors.
   - `app/page.tsx`, `lib/beatDetection.ts`, and `lib/videoExport.ts` are large — extend via new hooks/modules rather than growing them further.

3. **Reuse before rewrite**
   - Check `lib/` and `components/` before adding parallel logic.
   - Export filename contract: `` `match-cut-${Date.now()}` `` — do not change without updating README and any saved exports in `Face Aligntment /`.

4. **No silent regressions on export**
   - Any change to `videoExport.ts`, `imageAlignment.ts`, or `faceDetection.ts` must be testable (manual checklist at minimum until automated tests exist).
   - GIF and MP4 paths are separate — fix one without breaking the other.

5. **Document decisions**
   - Significant architecture choices go in `docs/` (not new root-level `*_FIX.md` files).
   - Historical fix notes belong in `docs/history/` only.

---

## Key files (touch map)

| Area | Primary files |
|------|----------------|
| Orchestration | `app/page.tsx` |
| Face / eyes | `lib/faceDetection.ts`, `lib/imageAlignment.ts`, `lib/advancedAlignment.ts` |
| Export | `lib/videoExport.ts`, `components/ExportOptions.tsx` |
| Beat sync | `lib/beatDetection.ts`, `lib/audioManager.ts`, `lib/audioFilters.ts` |
| Types | `lib/types.ts` |
| UI | `components/*.tsx` |
| Build / WASM | `next.config.js` (COOP/COEP, webpack wasm) |

---

## Allowed actions

- Read and edit `app/`, `components/`, `lib/`, `public/`, `docs/`
- Run `npm install`, `npm run dev`, `npm run build`, `npm run lint`
- Add tests under `tests/` or `__tests__/` when introduced
- Add CI under `.github/workflows/` when introduced

## Forbidden actions (without explicit approval)

- Adding backend image storage or third-party vision APIs
- Upgrading Next.js major version in the same PR as feature work
- Deleting `docs/history/` (archived context)
- Moving export outputs from `/Users/alexphoenix/projects/Face Aligntment /` (user artifact folder)

---

## Development workflow

1. Read `README.md` and `docs/STRUCTURE.md` for context.
2. Propose a minimal plan for non-trivial work.
3. Implement surgically; match existing TypeScript + Tailwind style.
4. Verify in Chrome: upload 2–3 face photos → preview → export MP4.
5. Update docs if behavior, requirements, or structure changes.

---

## Common tasks

| Task | Where to look |
|------|----------------|
| Export fails | `lib/videoExport.ts`, `docs/TROUBLESHOOTING.md` |
| Face not detected | `lib/faceDetection.ts`, image quality preflight |
| Beat sync off | `lib/beatDetection.ts`, `exportSettings.beatSync` in `app/page.tsx` |
| UI export options | `components/ExportOptions.tsx` |
| WASM / FFmpeg load | `next.config.js`, network for CDN wasm |

---

## Context for this machine

- **Repo path:** `/Users/alexphoenix/projects/match-cut`
- **Sample exports:** `/Users/alexphoenix/projects/Face Aligntment /` (outputs only, not source)
- **Upstream:** [github.com/sanjogbora/match-cut](https://github.com/sanjogbora/match-cut)
- **Deploy:** Vercel → `match-cut.vercel.app`

---

## When in doubt

Ask before: new dependencies, server routes that handle images, or breaking export filename/format contracts.