# Context7 — API key & usage (match-cut)

## Do you need an API key?

| Mode | API key | Rate limits |
|------|---------|-------------|
| **Local / agent** (`npx ctx7`) | Optional | Lower without login |
| **CLI login** (`ctx7 login`) | OAuth (no manual key) | Higher |
| **CI scheduled QC** | **Recommended** | Avoid weekly audit failures |

Skill default: works **without** a key. For **Option B weekly cron**, add a key to GitHub Secrets.

---

## How to get a Context7 API key

1. Open **[context7.com/dashboard](https://context7.com/dashboard)** (sign up / log in).
2. Find the **API Keys** card.
3. Click **Create API Key**.
4. Name it (e.g. `match-cut-ci`, `grok-local`).
5. **Copy immediately** — format: `ctx7sk-…` (shown once only).
6. Store in password manager or secrets file.

### Local (Mac)

```bash
# Option A — browser login (no key paste)
npx ctx7 login

# Option B — API key in env (CI + scripts)
echo 'CONTEXT7_API_KEY=ctx7sk-your-key-here' >> ~/.secrets   # or project .env.local (gitignored)
export CONTEXT7_API_KEY=ctx7sk-...
npx ctx7 whoami
```

Copy `.env.example` → `.env.local` and set `CONTEXT7_API_KEY` if using key auth.

### GitHub Actions (weekly/monthly QC)

1. Repo → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**
3. Name: `CONTEXT7_API_KEY`
4. Value: your `ctx7sk-…` key

Workflow reads it automatically; never commit the key.

---

## Verify

```bash
npx ctx7 whoami
npx ctx7 docs /vercel/next.js "webpack asyncWebAssembly config"
```

---

## Match-cut library IDs (QC audit)

| Stack | Library ID |
|-------|------------|
| Next.js | `/vercel/next.js` |
| React | `/react/react` |
| Tailwind | `/tailwindlabs/tailwindcss.com` |
| ESLint | `/eslint/eslint` |
| MediaPipe | `/google-ai-edge/mediapipe` |

Automated queries: `scripts/qc-context7.sh` (called by `scripts/qc-audit.sh`).