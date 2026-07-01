# Sub-agent strategy — fast QC on M3 Max

Parallel agent layout for **minimum wall-clock time** on 48 GB M3 Max.

Use when running `/check-work`, scheduled `mc qc`, or manual audits.

---

## Principle

**Split by independence, merge at end.** Never run Context7 inside lint; run in parallel.

```
                    ┌─ Agent A: Lint + tsc ─────────┐
                    ├─ Agent B: npm audit + outdated ┤
Orchestrator ───────┼─ Agent C: Context7 stack (×4) ──┼──► qc-report.md
                    └─ Agent D: check:practices ──────┘
```

Target wall-clock on M3 Max: **~2–4 min** full QC (vs ~8–12 min sequential).

---

## Agent roles

### Agent A — Lint & types (read-only ok)

**Scope:** ESLint, `tsc --noEmit`, build smoke optional  
**Files:** `app/`, `components/`, `lib/`, `tsconfig.json`  
**Commands:**

```bash
cd /Users/alexphoenix/projects/match-cut
npm run lint
npx tsc --noEmit
```

**Exit:** PASS / FAIL + log path `docs/audits/latest/lint.log`

---

### Agent B — Dependency audit

**Scope:** Security + version drift  
**Commands:**

```bash
npm audit --audit-level=high
npm outdated --json > docs/audits/latest/outdated.json
```

**Exit:** PASS if no high/critical; WARN if outdated majors

---

### Agent C — Context7 doc audit (parallel ×4)

**Scope:** Stack docs vs current code patterns  
**Requires:** `CONTEXT7_API_KEY` or `ctx7 login` for reliable CI  
**Parallel queries** (one sub-call each):

| Query ID | Library | Question |
|----------|---------|----------|
| c7-next | `/vercel/next.js` | webpack asyncWebAssembly experimental headers COOP |
| c7-react | `/facebook/react` | useCallback useEffect dependency best practices |
| c7-mp | mediapipe resolve | Face Landmarker browser tasks-vision |
| c7-export | `/vercel/next.js` or ffmpeg | client side video export wasm |

**Script:** `scripts/qc-context7.sh` (4 parallel jobs on M3 Max)

**Exit:** PASS if all queries return; WARN on rate limit (retry with API key)

---

### Agent D — Practices guard

**Scope:** Repo structure hard rules  
**Command:**

```bash
npm run check:practices
```

**Exit:** PASS / FAIL (blocking)

---

## Orchestration modes

### Mode 1 — Shell parallel (fastest local)

```bash
mc qc
# runs scripts/qc-audit.sh — 8 jobs on M3 Max
```

### Mode 2 — Grok Task tool (4 subagents at once)

Launch **in one message**:

1. `generalPurpose` — Agent A lint/tsc  
2. `generalPurpose` — Agent B npm audit/outdated  
3. `generalPurpose` — Agent C run `bash scripts/qc-context7.sh`  
4. `generalPurpose` — Agent D `npm run check:practices`

Orchestrator merges outputs into `docs/audits/YYYY-MM-DD-qc.md`.

### Mode 3 — GitHub scheduled (Option B)

| Schedule | Workflow | Agents simulated |
|----------|----------|------------------|
| Every push/PR | `ci.yml` | A + D + build + audit high |
| Weekly Mon 06:00 UTC | `qc-scheduled.yml` | A + B + C + D full |
| Monthly 1st 06:00 UTC | `qc-scheduled.yml` deep | + outdated report committed |

---

## Merge rules (orchestrator)

| Result | Action |
|--------|--------|
| D fails | **Block** — fix structure first |
| A fails | **Block** merge |
| B high/critical | **Block** until resolved or documented exception |
| C WARN (rate limit) | Retry with API key; don't block if push CI passed |
| B outdated only | **Warn** — monthly issue |

---

## Speed checklist

- [ ] `CONTEXT7_API_KEY` in GitHub Secrets + local `~/.secrets`
- [ ] Use `mc qc` not sequential npm commands
- [ ] Launch 4 Task subagents in parallel for full audit
- [ ] `next dev --turbo` for local UI work
- [ ] Future: 8 face workers for batch align (see HARDWARE.md)