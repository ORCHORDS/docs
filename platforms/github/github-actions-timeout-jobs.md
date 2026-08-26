# github-actions-timeout-jobs

**Issue:** Setting timeouts on jobs and steps to prevent runaway CI costs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A hung test or infinite loop can run for 6 hours (the GitHub default), consuming all runner minutes and blocking the queue.

## Pattern / Solution
Job-level timeout (minutes):
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - run: npm test
```
Step-level timeout:
```yaml
      - name: Integration tests
        timeout-minutes: 10
        run: pytest tests/integration/
```
Recommended per job type:

| Job type | Suggested timeout |
|---|---|
| Unit tests | 10 min |
| Build | 20 min |
| E2E tests | 45 min |
| Docker build | 30 min |

## Gotchas
- The default timeout is 360 minutes (6 hours) — always set an explicit value.
- Step timeouts do not override job timeouts; the job still wins if it expires first.
- Self-hosted runners: a hung job holds the runner slot; timeouts free it.
- Use `cancel-in-progress: true` in concurrency groups to cancel, not just timeout, stale runs.

## Related
- `github-actions-cancel-redundant.md`
- `github-actions-self-hosted-runners-2026.md`
