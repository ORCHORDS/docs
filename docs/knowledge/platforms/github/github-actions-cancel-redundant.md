# github-actions-cancel-redundant

**Issue:** Cancelling in-progress workflow runs when a new commit is pushed to the same branch
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Rapid successive pushes queue up many workflow runs. Each consumes runner minutes; only the latest result matters.

## Pattern / Solution
Built-in concurrency group (recommended):
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```
Per-job concurrency:
```yaml
jobs:
  build:
    concurrency:
      group: build-${{ github.ref }}
      cancel-in-progress: true
```
Protect release/main merges from cancellation:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```

## Gotchas
- Never cancel production deployments — gate `cancel-in-progress` on the branch name.
- Cancelled jobs count as "cancelled" not "failed" — status checks may need updating.
- The group string can be any string; use a composite that uniquely scopes the concurrent work.
- Without this, a stale run can overwrite a newer deployment if runners are fast.

## Related
- `github-actions-concurrency-groups.md`
- `github-actions-timeout-jobs.md`
