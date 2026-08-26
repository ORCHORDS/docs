# feature-flags-before-code-changes

**Issue:** Shipping code changes without a feature flag removes the ability to instantly revert behavior without a redeploy
**Date:** 2026-08-11
**Status:** documented

## What happened
A new checkout flow was shipped behind no flag. Within two hours, a subtle edge case in address validation blocked 3% of orders. Rolling back required a full redeploy cycle (45 minutes), during which the broken flow continued causing lost revenue. A feature flag would have cut exposure to under 30 seconds.

## The lesson
Every user-facing or revenue-critical code path should ship behind a feature flag. Enable the flag for internal users first, then a small percentage of production traffic, then full rollout. Keep flags alive until the old code path is fully removed.

## Why it matters
Deploys are slow; flag flips are instant. A flag gives you surgical rollback without a redeploy, enables percentage rollouts, and allows A/B testing. Without it, every bug requires a full deploy cycle under incident pressure.

## How to apply
- [ ] Identify if the change affects any user-visible behavior or revenue path — if yes, flag it.
- [ ] Define flag states: off (old path), beta (internal/percentage), on (full rollout).
- [ ] Wire flag evaluation to your observability tool so you can correlate with error rates.
- [ ] Schedule flag cleanup after stable rollout (flags are tech debt if left indefinitely).
- [ ] Never delete the flag before also deleting the old code path.

## Related
- `monitor-before-and-after-deploy.md`
- `always-test-rollback-before-deploying.md`
