# Requirements — Match Cut Generator

## Runtime (development & build)

| Dependency | Version | Notes |
|------------|---------|-------|
| **Node.js** | 20.x | Pin in `.nvmrc` |
| **npm** | 10+ | Ships with Node 20 |
| **OS** | macOS, Linux, Windows | Dev tested on macOS (Apple Silicon) |

No Python, Docker, or system FFmpeg required — export uses FFmpeg.wasm in the browser.

---

## npm packages (production)

Defined in `package.json`:

| Package | Role |
|---------|------|
| `next` ^14 | App framework (App Router) |
| `react` / `react-dom` ^18 | UI |
| `@mediapipe/tasks-vision` | Face Landmarker |
| `@ffmpeg/ffmpeg`, `@ffmpeg/util` | GIF export |
| `mediabunny` | Media helpers |
| `web-audio-beat-detector` | Beat detection |
| `lucide-react` | Icons |
| `tailwindcss`, `clsx`, `tailwind-merge`, `class-variance-authority` | Styling |
| `@vercel/analytics` | Deploy analytics |

Install:

```bash
npm install
```

---

## npm packages (development)

| Package | Role |
|---------|------|
| `typescript` ^5.2 | Type checking |
| `eslint`, `eslint-config-next` | Lint |
| `autoprefixer`, `postcss` | CSS pipeline |
| `@types/node`, `@types/react`, `@types/react-dom` | Types |

---

## Browser requirements (end users)

### Recommended

- **Chrome** or **Edge** (latest)
- WebAssembly support
- WebCodecs API (MP4 export, best quality)
- Sufficient RAM for canvas + wasm (see below)

### Minimum

- Modern browser with WASM
- JavaScript enabled
- For GIF export: network access on first load (FFmpeg.wasm may load from CDN unless bundled locally)

### Headers (production)

`next.config.js` sets:

- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Embedder-Policy: unsafe-none`

Required for shared memory / wasm behavior in some export paths.

---

## Hardware guidance

| Scenario | RAM | Notes |
|----------|-----|-------|
| 5–10 images, 720p | 4 GB+ | Smooth |
| 30+ images, 1080p | 8 GB+ | Close other tabs |
| 100+ images | 16 GB+ | Batch processing not yet optimized |

Image limits (app UI): up to 200 files, ~10 MB each (JPG/PNG/GIF).

---

## Network

| Action | Network needed? |
|--------|-----------------|
| Face detection | No (after MediaPipe model load) |
| Alignment / preview | No |
| MP4 export (WebCodecs) | No |
| GIF export (FFmpeg.wasm) | Often yes on first use (wasm fetch) |
| Vercel analytics | Yes (deploy only) |

---

## Environment variables

None required for local dev. Optional for deploy:

| Variable | Purpose |
|----------|---------|
| (none today) | Future: error reporting, feature flags |

Copy pattern for future use: `.env.example` when secrets are added.

---

## Verification checklist

After setup:

```bash
node -v          # v20.x
npm -v           # 10+
npm install
npm run build    # must pass
npm run dev      # http://localhost:3000 loads
```

Manual smoke test:

1. Upload 2+ front-facing portraits
2. Wait for alignment (green / aligned status)
3. Export MP4 at 720p
4. File downloads as `match-cut-<timestamp>.mp4`

---

## Future requirements (planned)

| Item | Target phase |
|------|----------------|
| `vitest` + canvas mocks | Stability |
| `playwright` E2E | Stability |
| IndexedDB project persistence | Architecture |
| Bundled FFmpeg (offline GIF) | Performance |
| Node 20 + Next 16 upgrade | Separate PR |