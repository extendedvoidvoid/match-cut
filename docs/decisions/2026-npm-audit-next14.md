# Decision: npm audit advisory on Next 14

**Date:** 2026-07-01  
**Status:** Active until Next.js 16 upgrade PR

## Context

`npm audit --audit-level=high` reports vulnerabilities in Next 14 and eslint-config-next (glob, postcss). Fix requires `next@16` (breaking).

## Decision

- **PR CI:** audit runs with `continue-on-error: true` (logged, not blocking)
- **QC audit:** `npm-audit` status `warn`, not `fail`
- **Upgrade track:** dedicated PR for Next 16 + re-enable blocking audit

## Client-side note

Match-cut is static client processing; many Next server CVEs are lower risk for this deploy model, but upgrade remains planned.