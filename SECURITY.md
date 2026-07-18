# Security — match-cut

## Never commit

- API keys, tokens, passwords, full PAN/CVV
- `.env` with secrets (use `.env.example` for names only)
- Private keys, session cookies, `storageState` dumps
- LM Studio / OpenRouter / NVIDIA / TMDB raw keys

## Where secrets live

- macOS Keychain / password manager
- `~/.secrets/` (chmod 700/600) when local files needed
- Project `.env` gitignored — TMDB etc. for posters only
- Env injected at runtime — not in git

## Project risks (match-cut)

1. **Client privacy (MUST):** stills stay in browser for Next app — no photo upload APIs without approval (`AGENTS.md`).
2. **film-grab / reel scripts:** local disk under `assets/film-grab/` — large; gitignored; do not publish personal still libraries.
3. **Third-party vision:** cloud VL optional and off acquire path; prefer local MediaPipe + optional LM Studio Qwen. Never send full film-grab library to cloud by default.
4. **WASM / COOP:** `next.config.js` wasm headers — retest export if changed.
5. **MCP keys** (Firecrawl, etc.) live in client MCP config — not in this repo.

## Installs

- Vendor / brew core / App Store / official GitHub releases only
- **Denied:** MacUpdate, Softonic, Uptodown, random DMG mirrors
- CF blocks curl → headed browser under **Watch**

## If leaked

1. Rotate key at provider
2. Purge from git history if pushed
3. Note in vault KEYS_META (meta only — no secret text)

*setup_project full · adapted 2026-07-18*
