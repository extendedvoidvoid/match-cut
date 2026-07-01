# Match Cut Generator

Browser-based tool for creating eye-aligned match-cut animations from photos. Upload images, auto-align faces via MediaPipe, preview in real time, and export GIF or MP4.

**Live:** [match-cut.vercel.app](https://match-cut.vercel.app/)

**Origin:** Forked from [sanjogbora/match-cut](https://github.com/sanjogbora/match-cut). Local development copy lives at `/Users/alexphoenix/projects/match-cut`.

---

## Features

- **Face detection** — MediaPipe Face Landmarker (in-browser)
- **Eye alignment** — Full-frame or face-crop modes; eyes stay fixed across cuts
- **Preview** — Live animation before export
- **Export** — GIF or MP4 at 480p / 720p / 1080p
- **Beat sync** — Optional music-driven frame timing
- **Audio** — Built-in transition sounds or custom audio overlay
- **Privacy** — Images never leave the browser

---

## Quick start

### Prerequisites

See [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) for full system and browser requirements.

| Requirement | Minimum |
|-------------|---------|
| Node.js | 20.x (see `.nvmrc`) |
| npm | 10+ |
| Browser (dev) | Chrome or Edge recommended |

### Install & run

```bash
mc cd            # jump to project (shell alias)
npm install
mc dev           # or: npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Project alias (`mc`)

After shell setup (see below):

| Command | Purpose |
|---------|---------|
| `mc` | `cd` to project |
| `mc dev` | Dev server |
| `mc build` | Production build |
| `mc lint` | ESLint |
| `mc check` | Good-practices guard |
| `mc exports` | Open `Face Aligntment /` sample exports |

From repo: `./bin/mc <command>` or `npm run mc -- dev`

**Shell setup** (in `~/.zshrc`):

```bash
matchcut() {
  local dir="/Users/alexphoenix/projects/match-cut"
  case "${1:-}" in
    dev|build|lint|check|exports) cd "$dir" && "$dir/bin/mc" "$1" ;;
    "") cd "$dir" ;;
    *) cd "$dir" && "$dir/bin/mc" "$@" ;;
  esac
}
alias mc=matchcut
```

### Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Development server |
| `npm run build` | Production build |
| `npm run start` | Serve production build |
| `npm run lint` | ESLint |
| `npm run check:practices` | Enforce repo rules (also in CI) |

---

## Project layout

```
match-cut/
├── app/                    # Next.js App Router
│   ├── page.tsx            # Main editor (orchestration)
│   ├── layout.tsx
│   ├── globals.css
│   └── about/
├── components/             # UI
│   ├── ImageUpload.tsx
│   ├── ImageGrid.tsx
│   ├── AnimationPreview.tsx
│   ├── ExportOptions.tsx
│   └── ProcessingIndicator.tsx
├── lib/                    # Core pipeline (browser-only)
│   ├── faceDetection.ts    # MediaPipe
│   ├── imageAlignment.ts   # Eye-aligned warping
│   ├── advancedAlignment.ts
│   ├── videoExport.ts      # GIF/MP4 (FFmpeg.wasm, WebCodecs)
│   ├── beatDetection.ts    # Beat-sync timing
│   ├── audioManager.ts
│   ├── audioFilters.ts
│   ├── types.ts
│   └── utils.ts
├── public/                 # Static assets (sounds, demo video)
├── docs/
│   ├── REQUIREMENTS.md
│   ├── STRUCTURE.md
│   ├── TROUBLESHOOTING.md
│   └── history/            # Archived dev notes (*_FIX.md, etc.)
├── AGENTS.md               # Rules for AI agents on this repo
├── package.json
└── next.config.js
```

Full module map: [docs/STRUCTURE.md](docs/STRUCTURE.md).

---

## Pipeline overview

```
Upload images
    → faceDetection.ts (MediaPipe)
    → imageAlignment.ts (eye lock)
    → AnimationPreview (canvas frames)
    → videoExport.ts (GIF or MP4)
    → download as match-cut-{timestamp}.ext
```

Optional: `beatDetection.ts` + `audioManager.ts` for music-synced cuts and sound.

---

## Export naming

Exports use millisecond timestamps from the browser:

```
match-cut-{Date.now()}.mp4
match-cut-{Date.now()}.gif
```

Example: `match-cut-1780298643843.gif` → exported 2026-06-01 07:24:03 UTC.

---

## Browser support

| Browser | Face align | MP4 | GIF |
|---------|------------|-----|-----|
| Chrome / Edge | Full | Full (WebCodecs) | Full (FFmpeg.wasm) |
| Firefox | Full | Limited | Full |
| Safari | Full | Limited | Full (may need network for FFmpeg) |

Details: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/GOOD_PRACTICES.md](docs/GOOD_PRACTICES.md) | **Canonical MUST/MUST NOT** (CI-enforced) |
| [AGENTS.md](AGENTS.md) | Agent summary |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Setup + PR checklist |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Node, OS, browser, memory |
| [docs/STRUCTURE.md](docs/STRUCTURE.md) | File and module reference |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common failures and fixes |
| [docs/history/](docs/history/) | Archived implementation notes |

---

## Maturity roadmap (high level)

1. **Basics** — README, AGENTS, structure, requirements *(current)*
2. **Stability** — CI, tests, error UX, IndexedDB project save
3. **Architecture** — Split `app/page.tsx` into hooks + workers
4. **Product** — Presets, manual eye override, aspect ratios

---

## License

MIT — see upstream [sanjogbora/match-cut](https://github.com/sanjogbora/match-cut).