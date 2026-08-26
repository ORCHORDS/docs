# github-actions-path-filters

**Issue:** Running workflows only when relevant files change using path filters
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
In monorepos or mixed-content repos, every push triggers every workflow even when unrelated files changed. This wastes CI minutes and slows feedback loops.

## Pattern / Solution
GitHub Actions supports `paths` and `paths-ignore` filters on push and pull_request triggers.

**Basic path filter:**
```yaml
on:
  push:
    paths:
      - 'src/**'
      - 'package.json'
      - 'package-lock.json'
  pull_request:
    paths:
      - 'src/**'
      - 'package.json'
```

**Ignore docs-only changes:**
```yaml
on:
  push:
    paths-ignore:
      - '**.md'
      - 'docs/**'
      - '.github/CODEOWNERS'
```

**Per-service workflows in a monorepo:**
```yaml
# .github/workflows/api.yml
on:
  push:
    paths:
      - 'services/api/**'
      - 'packages/shared/**'   # shared dep that affects api
    branches: [main, 'release/**']
```

**Dynamic path-based job skipping with `dorny/paths-filter`:**
```yaml
jobs:
  changes:
    runs-on: ubuntu-latest
    outputs:
      api: ${{ steps.filter.outputs.api }}
      web: ${{ steps.filter.outputs.web }}
    steps:
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            api:
              - 'services/api/**'
            web:
              - 'apps/web/**'

  build-api:
    needs: changes
    if: needs.changes.outputs.api == 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo "Building API"
```

## Gotchas
- `paths` filters do **not** apply to `workflow_dispatch` or `schedule` triggers — those always run
- If all changed files are excluded by `paths-ignore`, the workflow is skipped entirely — this means required status checks can go "missing" rather than passing, which blocks merges. Combine with branch protection "skipped is passing" setting or always run a lightweight check job
- `paths` and `paths-ignore` cannot both be used on the same trigger
- Patterns use `.gitignore`-style globbing — `**` matches across directory boundaries, `*` does not
- The filter applies to the diff between the base and head of the push, not individual commit diffs

## Related
- `github-actions-matrix-2026.md`
- `github-actions-monorepo-caching.md`
- `github-required-status-checks.md`
