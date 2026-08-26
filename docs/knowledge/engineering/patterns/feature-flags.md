# feature-flags

**Issue:** Deploy dark, release gradually
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a major feature. It's in the deploy. All users get it
at once. The feature is broken for 20% of users. You revert.
Half your users had a bad experience. The other half saw a
feature briefly and then it disappeared.

## Root cause
**Coupling deploy time to release time is the root cause.** If
"deploy the code" and "turn on the feature" are the same event,
you can't separate them. To roll back, you must redeploy
(risky, slow).

**Source:** LaunchDarkly / Split / etc. — feature flag
fundamentals:
https://launchdarkly.com/blog/what-are-feature-flags/

> "Feature flags ... let you decouple deployment from release."

## Fix

### 3 levels of feature flags

#### Level 1: Build-time flags (simplest)
```ts
const FEATURE_NEW_DASHBOARD = process.env.FEATURE_NEW_DASHBOARD === 'true';
if (FEATURE_NEW_DASHBOARD) {
  return <NewDashboard />;
}
return <OldDashboard />;
```

- **Pros:** Simple, no runtime cost
- **Cons:** Toggle requires redeploy, no per-user targeting

#### Level 2: Runtime flags via config (medium)
```ts
const featureFlags = await env.KV.get('feature-flags', 'json') ?? {};
if (featureFlags.NEW_DASHBOARD) {
  return <NewDashboard />;
}
return <OldDashboard />;
```

- **Pros:** Toggle without redeploy, eventual consistency
- **Cons:** No per-user targeting, KV eventually consistent

#### Level 3: User-targeted flags (advanced)
```ts
// Per-user flag evaluation
const enabled = await isFeatureEnabledForUser(
  env,
  'new-dashboard',
  userId,
  { cohort: 'beta-testers' }
);
if (enabled) {
  return <NewDashboard />;
}
return <OldDashboard />;
```

The flag service evaluates:
- User attributes (id, role, cohort, region)
- Percentage rollout (e.g. "1% of users")
- Time-based (e.g. "after 2026-09-01")
- Allowlist / blocklist (specific user IDs)

- **Pros:** Gradual rollout, kill switch, A/B testing
- **Cons:** More complex, requires a flag service

### Pattern: flag naming

`feature_<name>_<stage>`:
- `feature_new_dashboard_dev` — only in dev
- `feature_new_dashboard_beta` — beta cohort only
- `feature_new_dashboard_pct_1` — 1% rollout
- `feature_new_dashboard_pct_10` — 10% rollout
- `feature_new_dashboard_full` — 100% (the eventual state)

Or with a manifest:
```json
{
  "new-dashboard": {
    "stages": [
      { "stage": "dev", "enabled_for": ["dev-users"] },
      { "stage": "beta", "enabled_for": ["beta-testers"] },
      { "stage": "pct_1", "pct": 1 },
      { "stage": "pct_10", "pct": 10 },
      { "stage": "pct_50", "pct": 50 },
      { "stage": "full", "pct": 100 }
    ]
  }
}
```

### Pattern: kill switch

For any feature that could be dangerous (e.g. a new payment
flow), add a kill switch:
```ts
// In your flag service
if (await isFeatureEnabled('payment-flow-v2')) {
  return processPaymentV2(...);
}
// Else: processPaymentV1 (the fallback)
```

If V2 is broken, flip the kill switch → instant fallback to V1
without a redeploy.

### Pattern: cleanup

Old flags are tech debt. After a feature is at 100% and stable,
remove the flag (and the fallback code):
```bash
# Find all feature flag references
grep -rn "feature_new_dashboard" src/
# Remove them
```

Schedule a quarterly flag cleanup.

## Verification
- **Test:** `test/feature-flags.test.ts` — flag is honored per
  user + per cohort
- **Live:** New feature is at 1% for 24h before 10% → 50% → 100%
- **Audit:** Quarterly flag cleanup

## Gotchas
- **A flag at 100% is not the same as no flag.** The if/else
  is dead code. Remove the flag AND the fallback to keep the
  code clean.
- **Flag evaluation on every request is expensive.** Cache the
  flag result per-user (in a session-bound KV entry).
- **Flags can leak state.** If a user is in the 1% cohort and
  you remove them, their data may be in a different format
  than users who never saw the feature. Migrations matter.
- **Don't use flags for long-term config.** A "feature" that
  is always on for some users and always off for others is a
  config, not a flag. Use a per-user config instead.
- **A flag service is a SPOF.** If the flag service is down,
  the app can't evaluate flags. Cache the result + fall back to
  a sensible default.

## Related
- `patterns/retry-with-jitter.md`
- LaunchDarkly: https://launchdarkly.com/
- Split: https://www.split.io/
- CF Workers KV (for simple flag storage): https://developers.cloudflare.com/kv/
