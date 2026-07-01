---
name: context7
description: >
  Context7 CLI docs for match-cut. Auto-trigger for Next.js, React, Tailwind,
  ESLint, MediaPipe, FFmpeg.wasm, or when user says context7 / library docs.
metadata:
  short-description: "Context7 CLI — match-cut stack"
---

# Context7 — match-cut

API key: optional locally; recommended for `mc qc` / CI. See `docs/CONTEXT7.md`.

## Workflow

```bash
npx -y ctx7 library "<name>" "<query>"
npx -y ctx7 docs "<libraryId>" "<specific question>"
```

## Library IDs

| Stack | ID |
|-------|-----|
| Next.js 14 | `/vercel/next.js` |
| React 18 | `/facebook/react` |
| Tailwind 3 | `/tailwindlabs/tailwindcss` |
| ESLint | `/eslint/eslint` |

MediaPipe: `npx -y ctx7 library mediapipe "face landmarker"`

## Automated audit

```bash
mc qc-context7
# or full: mc qc
```

Hardware: M3 Max 48GB — 4 parallel Context7 queries (`MATCHCUT_CTX7_PARALLEL=4`).