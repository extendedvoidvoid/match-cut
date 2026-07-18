# MANIFEST — match-cut

| | |
|--|--|
| **name** | match-cut |
| **path** | `/Users/alexphoenix/projects/match-cut` |
| **alias** | `mc` / `matchcut` · `./bin/mc` |
| **created** | 2026-07-18 (manifest) · fork active |
| **status** | active |
| **role** | mainline (reel + client generator) |
| **stack** | Next.js 16 · React 19 · MediaPipe Tasks · FFmpeg.wasm · Python film-grab/reel scripts |
| **public** | yes (fork) — `origin` extendedvoidvoid/match-cut · `upstream` sanjogbora/match-cut |
| **agent files** | AGENTS.md + CLAUDE.md → AGENTS · docs/MODULES.md · docs/GOOD_PRACTICES.md |

## Purpose

Client-side match-cut: photos → MediaPipe eye align → GIF/MP4. Plus offline film-grab acquire, modular kiss/geo classify, Instagram-style reels (`mc reel-*`, `mc module`).

## Commands (quick)

```bash
mc dev | build | lint | check | qc
mc fetch-film-grab …
mc module list | run | mix | apply
mc classify-pass-a
mc lmstudio status | load-vision
```

## Links

- Rules: `AGENTS.md` · `docs/GOOD_PRACTICES.md`
- Modules: `docs/MODULES.md` · `scripts/modules/`
- Global law: `~/.grok/memory/MEMORY.md`
- Setup: **make pro** / **make pro full**

*setup_project full · adapted 2026-07-18*
