# Good practices — Match Cut Generator

Canonical rules for humans and agents. **Non-negotiable** unless explicitly approved.

Referenced by: `AGENTS.md`, `.cursor/rules/good-practices.mdc`, `scripts/check-practices.sh`, CI.

---

## 1. Privacy & trust

| Rule | Detail |
|------|--------|
| **MUST** keep image processing in the browser | MediaPipe, canvas, WASM export — client-only |
| **MUST NOT** upload photos to your server or third-party vision APIs | No OpenAI Vision, no S3 image pipeline without explicit approval |
| **MUST** document any new network call that touches user media | In `docs/` + README privacy section |

---

## 2. Export contract

| Rule | Detail |
|------|--------|
| **MUST** keep download basename `` `match-cut-${Date.now()}` `` | Users and `Face Aligntment /` exports depend on this pattern |
| **MUST** support both GIF and MP4 paths | Changes to one format must not break the other |
| **MUST** run manual smoke after touching `videoExport.ts` | 2+ aligned faces → export MP4 @ 720p in Chrome |
| **MUST NOT** change default resolution/format without updating docs | `ExportSettings` defaults are product decisions |

---

## 3. Architecture & file boundaries

| Rule | Detail |
|------|--------|
| **MUST NOT** grow `app/page.tsx` with new features | Extract hooks (`hooks/`) or lib modules first |
| **MUST** put browser pipeline logic in `lib/` | No MediaPipe/FFmpeg logic inside React components |
| **MUST** keep components presentational | Props in, events out; stateful orchestration in page or hooks |
| **MUST** reuse `lib/types.ts` | No duplicate `ImageData` / `ExportSettings` shapes |
| **MUST NOT** add root-level `*_FIX.md` or `*_PLAN.md` | Use `docs/history/` or `docs/decisions/` |

### Module ownership

```
components/   → UI only
lib/          → face, align, export, beat, audio (no React)
app/          → routes + thin orchestration
hooks/        → React state wiring (when introduced)
workers/      → heavy CPU off main thread (when introduced)
```

---

## 4. Code style

| Rule | Detail |
|------|--------|
| **MUST** use TypeScript strict mode | No `any` without comment |
| **MUST** match existing patterns | `@/` imports, Tailwind utilities, `cn()` for classes |
| **MUST** prefer surgical diffs | One concern per commit/PR |
| **MUST NOT** drive-by refactor unrelated files | Lint/format only touched paths |
| **SHOULD** add types for new public functions | Especially in `lib/` |

---

## 5. WASM & browser compatibility

| Rule | Detail |
|------|--------|
| **MUST** preserve `next.config.js` wasm + COOP settings | Required for FFmpeg.wasm / shared memory |
| **MUST** test export in Chrome after webpack/config changes | Primary target browser |
| **MUST NOT** remove Firefox/Safari fallbacks without documenting regression | See `docs/REQUIREMENTS.md` |

---

## 6. Beat sync & audio

| Rule | Detail |
|------|--------|
| **MUST** keep beat sync optional | Default off; no forced music pipeline |
| **MUST** isolate beat logic in `lib/beatDetection.ts` | Not in `ExportOptions.tsx` beyond UI bindings |
| **MUST NOT** change beat sensitivity semantics silently | UI labels + docs if algorithm changes |

---

## 7. Testing & CI

| Rule | Detail |
|------|--------|
| **MUST** pass `npm run lint` and `npm run build` before push | CI enforces on `main` |
| **MUST** pass `npm run check:practices` | Repo structure guard |
| **SHOULD** add unit tests when changing `lib/imageAlignment.ts` or `lib/faceDetection.ts` | Vitest when test harness exists |
| **MUST NOT** merge with failing CI | Fix or scope down |

---

## 8. Documentation

| Rule | Detail |
|------|--------|
| **MUST** update README for user-visible behavior changes | Features, flags, browser support |
| **MUST** update `docs/STRUCTURE.md` when adding top-level dirs | `hooks/`, `tests/`, etc. |
| **SHOULD** add `docs/decisions/YYYY-topic.md` for major choices | e.g. IndexedDB, server export fallback |

---

## 9. Git & remotes

| Rule | Detail |
|------|--------|
| **MUST** push to `origin` (`extendedvoidvoid/match-cut`) | Your fork |
| **MAY** pull from `upstream` (`sanjogbora/match-cut`) | Selective merges only |
| **MUST NOT** force-push `main` without coordination | |

---

## 10. Smoke checklist (manual, until E2E)

After any change to face, align, or export:

1. `mc dev` (or `npm run dev`)
2. Upload 2–3 clear front-facing portraits
3. Confirm aligned status on each
4. Preview plays smoothly
5. Export MP4 @ 720p → file named `match-cut-<timestamp>.mp4`
6. Optional: export GIF once

---

## Enforcement

| Mechanism | What it checks |
|-----------|------------------|
| `scripts/check-practices.sh` | No stray fix-docs at root; required docs exist |
| `.github/workflows/ci.yml` | lint + build + check:practices |
| `AGENTS.md` | Agent MUST/MUST NOT summary |
| `.cursor/rules/good-practices.mdc` | Cursor always-on rules |