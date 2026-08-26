# feature-rollout-strategies

**Issue:** Rollout strategies — canary, blue-green, percentage
**Date:** 2026-08-09
**Status:** documented

## Symptom
You deploy a new feature. 100% of users get it at once. 5%
have a bug. You revert. All 5% had a bad experience. You wish
you'd caught it earlier.

## Root cause
**Big-bang deploys are high-risk.** A small percentage of users
hit a bug = a small percentage of your userbase is unhappy.
The bug is small but the impact is real.

**Source:** Various SRE / deployment best practices:
https://sre.google/sre-book/release-engineering/

## The 4 main strategies

### 1. Canary
Deploy the new version to a small subset of users first.
Monitor. If healthy, expand.

```bash
# Deploy v2 to 1% of users
wrangler deploy --version 2 --percentage 1
# Wait 24h, monitor metrics
# If healthy, increase to 10%
wrangler deploy --version 2 --percentage 10
# Wait 24h
# If healthy, increase to 50%
# If healthy, increase to 100%
```

✅ **Use when:** you want real user feedback before full rollout
❌ **Drawback:** the canary users are real users; if buggy, they
see the bug

### 2. Blue-green
Run two parallel environments (blue = current, green = new).
Switch traffic atomically.

```
blue (v1, current)  ← 100% traffic
green (v2, new)     ←  0% traffic

# After green is verified:
green (v2) ← 100% traffic
blue (v1)  ←  0% traffic (kept for rollback)
```

✅ **Use when:** the deploy is risky and you need an instant
rollback path
❌ **Drawback:** 2x infrastructure cost during the deploy

### 3. Percentage
Roll out in increments: 1% → 10% → 50% → 100%.

```
1% for 24h → 10% for 24h → 50% for 24h → 100%
```

✅ **Use when:** you have metrics to track
❌ **Drawback:** slow (takes days); the canary users are real
users

### 4. Feature flag
Decouple deploy from release. Deploy with the feature off.
Turn on for specific users / cohorts.

```ts
if (await isFeatureEnabled('new-dashboard', userId)) {
  return <NewDashboard />;
}
return <OldDashboard />;
```

✅ **Use when:** the feature is risky, or you want to test with
specific users (beta cohort)
❌ **Drawback:** adds complexity (flag management)

## The 3 phases of a rollout

### Phase 1: Internal dogfood
- **Who:** Your team + close collaborators
- **Duration:** 1-2 weeks
- **Tools:** feature flag, internal-only env
- **Goal:** catch obvious bugs

### Phase 2: Beta cohort
- **Who:** Power users, opt-in beta testers
- **Duration:** 2-4 weeks
- **Tools:** feature flag at 1-5% or opt-in cohort
- **Goal:** catch real-world bugs + get feedback

### Phase 3: Gradual rollout
- **Who:** All users
- **Duration:** 1-4 weeks
- **Tools:** percentage rollout, automated monitoring
- **Goal:** confirm scalability + edge cases

## What to monitor

### Quantitative
- **Error rate:** 5xx count / total requests
- **Latency:** p50, p95, p99
- **Conversion rate:** users completing the key action
- **Retention:** users coming back

### Qualitative
- **Support tickets:** increase in user complaints
- **App store reviews:** decrease in rating
- **Social media:** mentions of bugs

### Automated rollback
```ts
// In the rollout script
const errorRate = await getErrorRate('new-feature');
if (errorRate > 0.05) {  // 5% error rate
  console.log('High error rate; rolling back');
  await setRolloutPercentage('new-feature', 0);
  await alert('new-feature rolled back due to high error rate');
}
```

## Verification
- **Test:** Each rollout phase has a documented exit criterion
- **Live:** Monitoring dashboards track the metrics
- **Audit:** Quarterly review of rollout procedures

## Gotchas
- **The "1% canary" is statistical noise.** If your error rate
  is normally 0.5%, a canary at 1% might see 2% (4 errors out
  of 200) — and you can't tell if that's noise or a real bug.
  Use a larger canary (5-10%) for meaningful signal.
- **Real users are not the same as internal users.** Internal
  users have more technical knowledge. Real users find the
  edge cases.
- **The "kill switch" is essential.** Always have a way to
  turn off the feature instantly (feature flag, env var,
  wrangler command).
- **Multi-region rollouts** are different. If your app runs in
  US, EU, APAC, you might roll out to one region first.
- **Database migrations complicate things.** A 1% canary
  might still hit the migration if it's a new schema. Migrate
  first, then deploy the code that uses the new schema.

## Related
- `feature-flags.md` (the flag mechanism)
- `zero-downtime-deploys.md` (the deploy mechanics)
- `preview-environments.md` (the pre-prod testing)
- `error-budget-slo.md` (the metrics to track)
- Google SRE: https://sre.google/sre-book/release-engineering/
