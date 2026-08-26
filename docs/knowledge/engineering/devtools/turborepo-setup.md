# turborepo-setup

**Issue:** Monorepo task pipeline has no caching or dependency awareness
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tasks run sequentially in wrong order; no cache means rebuilding unchanged packages.

## Pattern / Solution
Add turbo.json at root. Define pipeline with dependsOn: [^build] for topological order. turbo run build caches outputs. Remote cache via Vercel or self-hosted. --filter runs subset of packages.

## Gotchas
- Cache keys include inputs glob — misconfigured inputs cause stale cache hits
- turbo run dev does not cache persistent tasks; set persistent: true in pipeline

## Related
- nx-monorepo-setup, pnpm-workspace-setup
