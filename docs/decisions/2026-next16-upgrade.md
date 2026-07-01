# Decision: Next.js 16 upgrade

**Date:** 2026-07-01  
**Status:** Active

## Context

Next 14 blocked `npm audit --audit-level=high`. User verified Next 16 works on M3 Max with `MATCHCUT_PARALLEL_JOBS=8`.

## Decision

- Upgrade to `next@16`, `react@19`, `eslint@9`, `eslint-config-next@16`
- Use `--webpack` for dev/build (FFmpeg.wasm `asyncWebAssembly` + custom webpack config)
- Add `turbopack: {}` to silence Next 16 default Turbopack/webpack mismatch
- Replace removed `lucide-react` brand icon `Instagram` with local `InstagramIcon` SVG
- Re-enable blocking `npm audit` in CI

## Film-grab pipeline

- No local `film-grab` folder found on disk (2026-07-01 scan)
- Default output: `assets/film-grab/` (gitignored)
- Fetch: `mc fetch-film-grab run --target 3000`