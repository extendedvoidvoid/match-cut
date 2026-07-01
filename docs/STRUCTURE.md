# File structure — Match Cut Generator

Reference for `/Users/alexphoenix/projects/match-cut`.

---

## Top level

```
match-cut/
├── app/                 # Next.js routes & global styles
├── components/          # React UI (presentational + forms)
├── lib/                 # Browser pipeline (no React)
├── public/              # Static files served as-is
├── docs/                # Project documentation
├── AGENTS.md            # AI agent rules
├── README.md            # Project entry point
├── package.json         # Dependencies & scripts
├── package-lock.json
├── tsconfig.json        # TypeScript (@/* → project root)
├── next.config.js       # WASM, webpack fallbacks, COOP headers
├── tailwind.config.js
├── postcss.config.js
├── .eslintrc.js
├── .nvmrc               # Node 20
└── .gitignore
```

---

## `app/` — routes

| File | Responsibility |
|------|----------------|
| `page.tsx` | **Main editor.** State, service init (FaceDetector, ImageAligner, VideoExporter, AudioManager, BeatDetector), upload handler, alignment loop, preview frame generation, export trigger. |
| `layout.tsx` | Root layout, metadata, fonts |
| `globals.css` | Tailwind base + app-wide styles |
| `about/page.tsx` | About / marketing page |

**Planned refactor:** extract hooks from `page.tsx` → `hooks/useFacePipeline.ts`, `hooks/useExport.ts`, etc.

---

## `components/` — UI

| File | Responsibility |
|------|----------------|
| `ImageUpload.tsx` | Drag-drop / file picker; passes `File[]` upstream |
| `ImageGrid.tsx` | Thumbnail grid, reorder, remove, retry failed |
| `AnimationPreview.tsx` | Canvas playback, play/pause, frame indicator |
| `ExportOptions.tsx` | Format, resolution, duration, loop, audio, beat-sync controls |
| `ProcessingIndicator.tsx` | Progress bar + status text during init/processing |

Components should stay mostly stateless; heavy logic stays in `lib/` or hooks.

---

## `lib/` — core pipeline

All modules are browser-side (Canvas, Web Audio, WASM). Import alias: `@/lib/...`.

| File | Lines (approx) | Responsibility |
|------|----------------|----------------|
| `faceDetection.ts` | ~250 | `FaceDetector` class — MediaPipe init, `detectFace()`, eye landmarks |
| `imageAlignment.ts` | ~600 | `ImageAligner` — `alignImageFull`, `alignImageFaceCrop`, smoothing |
| `advancedAlignment.ts` | ~300 | Extra alignment helpers |
| `videoExport.ts` | ~900 | `VideoExporter` — GIF (FFmpeg.wasm) + MP4 (WebCodecs), `exportAndDownload()` |
| `beatDetection.ts` | ~1200 | `BeatDetector` — audio analysis, BPM, per-frame durations |
| `audioManager.ts` | ~250 | Built-in sounds + custom file playback for export |
| `audioFilters.ts` | ~150 | Audio processing filters |
| `types.ts` | ~100 | `ImageData`, `ExportSettings`, `AnimationFrame`, resolutions |
| `utils.ts` | ~60 | `generateId`, `loadImageFromFile`, `cn`, canvas helpers |
| `essentia.d.ts` | types | Essentia.js typings (beat detection experiments) |

### Data flow types (`types.ts`)

- `ImageData` — file, url, status (`pending` | `processing` | `aligned` | `failed`), aligned canvas
- `ExportSettings` — format, resolution, frameDuration, loop, alignmentMode, beatSync, audio
- `AnimationFrame` — canvas + duration per frame

---

## `public/` — static assets

| Asset | Use |
|-------|-----|
| `click-sound.mp3`, `pop-sound.mp3`, `shutter-sound.mp3` | Built-in transition audio |
| `effect demo.mp4` | Marketing / demo |
| `favicon.svg` | Site icon |

---

## `docs/`

| Path | Purpose |
|------|---------|
| `REQUIREMENTS.md` | Node, browser, hardware |
| `STRUCTURE.md` | This file |
| `TROUBLESHOOTING.md` | User-facing failure guide |
| `history/` | Archived `*_FIX.md`, `*_PLAN.md` dev notes (26 files) |

Do not add new fix-note markdown at repo root — use `docs/history/` or CHANGELOG.

---

## Path aliases

`tsconfig.json`:

```json
"paths": { "@/*": ["./*"] }
```

Examples: `@/lib/faceDetection`, `@/components/ImageUpload`.

---

## Build artifacts (gitignored)

- `node_modules/`
- `.next/`
- `out/` (if added)

---

## Related folders (outside repo)

| Path | Relation |
|------|----------|
| `/Users/alexphoenix/projects/Face Aligntment /` | User export archive (`match-cut-*.mp4`, `*.gif`) |
| [sanjogbora/match-cut](https://github.com/sanjogbora/match-cut) | Upstream source |
| [match-cut.vercel.app](https://match-cut.vercel.app/) | Production deploy |

---

## Planned structure (not yet created)

```
match-cut/
├── hooks/               # useFacePipeline, useBeatSync, useExport
├── workers/             # faceWorker, exportWorker (main-thread relief)
├── tests/               # vitest unit + fixtures
├── e2e/                 # playwright smoke
└── .github/workflows/   # ci.yml
```

Add these when Phase 2 (architecture) and Phase 3 (tests) begin.