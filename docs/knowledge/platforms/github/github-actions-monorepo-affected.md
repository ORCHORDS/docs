# github-actions-monorepo-affected

**Issue:** Running CI only for packages affected by a pull request in a monorepo
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
In large monorepos, running CI for every package on every PR wastes time. Affected-package detection limits work to changed scopes.

## Pattern / Solution
Using Nx:
```bash
npx nx affected --target=test --base=origin/main
```
Using Turborepo:
```bash
npx turbo run test --filter=...[origin/main]
```
Using `dorny/paths-filter` to gate jobs:
```yaml
      - id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            api:
              - 'packages/api/**'
            web:
              - 'packages/web/**'
      - if: steps.filter.outputs.api == 'true'
        run: pnpm --filter api test
```

## Gotchas
- `--base=origin/main` requires `fetch-depth: 0` in `checkout` to have the full comparison base.
- Turborepo's `--filter` supports both package names and git ranges.
- Affected detection misses implicit dependencies — always include a shared-library change as affecting all consumers.
- Cache invalidation must be per-package; a monorepo-wide cache key defeats the purpose.

## Related
- `github-actions-monorepo-caching.md`
- `github-actions-path-filters.md`
- `github-actions-cancel-redundant.md`
