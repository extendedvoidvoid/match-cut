# Hardware profile — MacBook M3 Max (48 GB unified)

**Hardcoded target machine** for local dev, QC, and performance defaults.

| Spec | Value |
|------|-------|
| Chip | Apple M3 Max |
| Unified memory | **48 GB** |
| Profile ID | `m3-max-48gb` |
| Repo path | `/Users/alexphoenix/projects/match-cut` |

All scripts and agent docs assume this host unless noted.

---

## Enforced defaults

| Setting | Value | Where |
|---------|-------|-------|
| `NODE_OPTIONS` | `--max-old-space-size=8192` | `package.json` dev/build |
| Next dev bundler | Turbopack (`next dev --turbo`) | `package.json` |
| Parallel QC jobs | **8** | `scripts/qc-audit.sh` |
| Context7 parallel queries | **4** | `scripts/qc-context7.sh` |
| CI (GitHub) | `ubuntu-latest` | Not M3 — cloud only |

---

## Why 8 parallel QC jobs

M3 Max has high-performance cores suitable for parallel lint + audit + Context7 + outdated checks. `scripts/qc-audit.sh` runs independent audits concurrently on **this Mac**; GitHub scheduled runs stay sequential (single runner).

---

## Browser runtime (match-cut app)

Processing is **in-browser** on the same machine:

| Workload | M3 Max guidance |
|----------|-----------------|
| 5–30 images @ 720p | Default — smooth in Chrome |
| 50+ images @ 1080p | Close other tabs; 48 GB allows large canvas batches |
| 100+ images | Prefer face-crop mode; future: 8-worker pipeline (see SUBAGENT_STRATEGY) |

---

## Planned app optimizations (M3-aware)

| Phase | Optimization |
|-------|----------------|
| Now | Turbopack dev, 8 GB Node heap for build |
| Next | `workers/faceWorker.ts` × **8** parallel face alignment |
| Next | `OffscreenCanvas` in workers for export prep |
| Later | Native ffmpeg CLI fallback for local batch (optional, still no upload) |

---

## Environment snippet (`~/.zshrc` optional)

```bash
export MATCHCUT_HARDWARE_PROFILE=m3-max-48gb
export MATCHCUT_PARALLEL_JOBS=8
```

`bin/mc` and QC scripts read these when set; defaults match table above.