# Contributing to Match Cut Generator

Fork: [extendedvoidvoid/match-cut](https://github.com/extendedvoidvoid/match-cut)

## Setup

```bash
mc cd          # or: cd /Users/alexphoenix/projects/match-cut
npm install
mc dev         # http://localhost:3000
```

## Before you push

```bash
mc lint
mc build
mc check
```

CI runs the same on every push/PR to `main`.

## Rules (required reading)

| Doc | Purpose |
|-----|---------|
| [docs/GOOD_PRACTICES.md](docs/GOOD_PRACTICES.md) | Canonical MUST/MUST NOT |
| [AGENTS.md](AGENTS.md) | Agent enforcement summary |
| [docs/STRUCTURE.md](docs/STRUCTURE.md) | Module map |

## Pull requests

- One concern per PR when possible.
- Manual smoke: 2+ faces → align → export MP4 @ 720p.
- No new root-level `*_FIX.md` files.