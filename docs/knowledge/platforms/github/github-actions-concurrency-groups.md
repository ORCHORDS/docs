# github-actions-concurrency-groups

**Issue:** Preventing duplicate or racing workflow runs with concurrency groups
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Multiple pushes to a branch queue up redundant CI runs or, worse, two deploys race each other and leave infrastructure in an inconsistent state. Teams need a way to cancel stale runs and serialize deploys.

## Pattern / Solution
The `concurrency` key cancels or queues runs that share the same group string.

**Cancel in-progress CI on new push (common for PRs):**
```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

**Serialize deployments — never cancel, just queue:**
```yaml
concurrency:
  group: deploy-production
  cancel-in-progress: false    # default; queues instead of cancelling
```

**Per-PR concurrency (cancels stale, keeps latest):**
```yaml
concurrency:
  group: pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true
```

**Job-level concurrency (finer grained than workflow-level):**
```yaml
jobs:
  deploy:
    concurrency:
      group: deploy-${{ github.ref_name }}
      cancel-in-progress: false
    runs-on: ubuntu-latest
    steps:
      - run: ./deploy.sh
```

**Dynamic group with fallback (avoid cancelling on main):**
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref == 'refs/heads/main' && github.sha || github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```

## Gotchas
- `cancel-in-progress: true` sends SIGTERM to the runner; cleanup steps using `if: always()` still run but have a limited window
- Group strings are global per repo — collisions across unrelated workflows can queue them unexpectedly if names are too generic
- A cancelled run shows as "Cancelled" not "Failed" — downstream status checks treat this differently
- Concurrency at the workflow level applies to the entire run; at the job level it only serializes that job while sibling jobs may still run
- There is no built-in priority — the newest queued run does not jump ahead of an older queued run

## Related
- `github-actions-runs-2026.md`
- `github-merge-queue.md`
- `github-required-status-checks.md`
