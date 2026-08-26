# feature-cookbook-feature-flags

**Issue:** Feature flags in practice — rollout, evaluation, ops
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a new feature. You want to test it with 1% of
users. You add an `if` check in the code. You deploy. You
change the check. You deploy. The cycle takes 10 min per
change. The product team is frustrated. They want
real-time flag changes.

## Root cause
**Compile-time flags are slow.** Runtime flags are fast.

**Source:** LaunchDarkly:
https://launchdarkly.com/

## The "runtime flag" pattern

```ts
async function isFeatureEnabled(name: string, ctx: McContext): Promise<boolean> {
  // 1. In-memory cache
  if (flagCache.has(name)) return flagCache.get(name)!;

  // 2. KV (or D1)
  const flag = await ctx.env.KV.get<FeatureFlag>(`flag:${name}`, 'json');
  if (!flag) return false;

  // 3. Evaluate
  const result = evaluate(flag, ctx);
  flagCache.set(name, result);

  return result;
}
```

The flag is evaluated per request; changes are immediate.

## The "flag definition" pattern

```ts
interface FeatureFlag {
  name: string;
  type: 'boolean' | 'percentage' | 'cohort' | 'variant';
  enabled: boolean;
  config: {
    percentage?: number;
    cohortRules?: CohortRule[];
    variants?: Array<{ name: string; percentage: number }>;
  };
  createdAt: string;
  updatedAt: string;
}
```

A flag has a name, type, enabled, and config.

## The "boolean flag" pattern

For on/off:
```ts
const flag: FeatureFlag = {
  name: 'new-dashboard',
  type: 'boolean',
  enabled: true,
  config: {},
  // ...
};

isFeatureEnabled('new-dashboard', ctx);  // true
```

## The "percentage rollout" pattern

For gradual rollout:
```ts
const flag: FeatureFlag = {
  name: 'new-dashboard',
  type: 'percentage',
  enabled: true,
  config: { percentage: 10 },  // 10% of users
};

// Deterministic hash: same user + flag = same bucket
function isInRollout(userId: string, flagName: string, percentage: number): boolean {
  const hash = sha256(`${userId}:${flagName}`);
  const bucket = parseInt(hash.slice(0, 8), 16) % 100;
  return bucket < percentage;
}
```

The user is deterministically in or out.

## The "cohort" pattern

For targeting by attributes:
```ts
const flag: FeatureFlag = {
  name: 'pro-feature',
  type: 'cohort',
  enabled: true,
  config: {
    cohortRules: [
      { attribute: 'plan', operator: 'equals', value: 'pro' },
      { attribute: 'country', operator: 'in', values: ['US', 'CA', 'UK'] },
    ],
  },
};

function matchesCohort(ctx: McContext, rules: CohortRule[]): boolean {
  return rules.every(rule => {
    const value = getAttribute(rule.attribute, ctx);
    switch (rule.operator) {
      case 'equals': return value === rule.value;
      case 'in': return Array.isArray(rule.value) && rule.value.includes(value);
      case 'not_in': return !rule.value.includes(value);
    }
    return false;
  });
}
```

The user matches the cohort rules.

## The "variant" pattern

For A/B tests:
```ts
const flag: FeatureFlag = {
  name: 'button-color',
  type: 'variant',
  enabled: true,
  config: {
    variants: [
      { name: 'red', percentage: 50 },
      { name: 'blue', percentage: 50 },
    ],
  },
};

function pickVariant(userId: string, flag: FeatureFlag): string {
  const hash = sha256(`${userId}:${flag.name}`);
  const bucket = parseInt(hash.slice(0, 8), 16) % 100;

  let cumulative = 0;
  for (const variant of flag.config.variants) {
    cumulative += variant.percentage;
    if (bucket < cumulative) return variant.name;
  }
  return flag.config.variants[0].name;
}
```

The user is in a variant.

## The "flag caching" pattern

For performance, cache the flag:
```ts
class FlagCache {
  private cache = new Map<string, { value: boolean; expiresAt: number }>();

  async get(name: string, ctx: McContext): Promise<boolean> {
    const cached = this.cache.get(name);
    if (cached && cached.expiresAt > Date.now()) return cached.value;

    const value = await isFeatureEnabled(name, ctx);
    this.cache.set(name, { value, expiresAt: Date.now() + 30_000 });  // 30s cache
    return value;
  }

  invalidate(name: string) {
    this.cache.delete(name);
  }
}
```

The flag is cached in memory.

## The "kill switch" pattern

For a critical feature, always have a kill switch:
```ts
if (!await isFeatureEnabled('risky-feature', ctx)) {
  return runSafeFeature();
}
return runRiskyFeature();
```

The kill switch is the safety net.

## The "rollout plan" pattern

For a safe rollout:
1. **Day 0:** 0% (deploy behind the flag)
2. **Day 1:** 1% (monitor)
3. **Day 3:** 10% (monitor)
4. **Day 7:** 50% (monitor)
5. **Day 14:** 100% (deploy)
6. **Day 90:** Remove the flag

The rollout is gradual.

## The "rollback" pattern

For an emergency rollback:
```ts
// 1. Set the flag to 0%
await setConfig('new-dashboard', { enabled: false, percentage: 0 }, env);

// 2. The next request uses the old code
// (Cache invalidation takes up to 30s)
```

The flag controls the rollout; rollback is instant.

## The "flag cleanup" pattern

For long-lived flags, schedule cleanup:
```sql
SELECT name, updated_at FROM feature_flags
WHERE enabled = true
  AND updated_at < datetime('now', '-90 days')
  AND rollout_percentage = 100;
```

A flag at 100% for 90 days is dead code.

## The "flag evaluation" metric

For analytics:
```ts
metrics.increment('flag.evaluations_total', {
  flag: name,
  result: 'true',
});
```

The metric shows flag usage.

## The "flag dashboard" pattern

For a dashboard:
- Total flags
- Active flags
- Flags at 100% (candidates for removal)
- Flags not evaluated (dead code)
- Evaluation latency

The dashboard is the source of truth.

## The "flag" anti-patterns

### 1. Long-lived flags
- **Symptom:** A flag at 100% for 6 months
- **Fix:** Schedule cleanup

### 2. No kill switch
- **Symptom:** A bad rollout can't be undone
- **Fix:** Always have a kill switch

### 3. Flag as config
- **Symptom:** A flag for "user's preferred color" (not
  transient state)
- **Fix:** Use a config, not a flag

### 4. Flag in a hot path without cache
- **Symptom:** Every request fetches the flag from KV
- **Fix:** In-memory cache

### 5. Inconsistent naming
- **Symptom:** Flags are `new-dashboard`, `enableNewDashboard`,
  `dashboard_v2`
- **Fix:** Define a naming convention

## Verification
- **Test:** Flag is evaluated correctly
- **Test:** Rollout is deterministic
- **Test:** Kill switch works
- **Live:** Flag metrics are monitored
- **Audit:** Quarterly review of flag list

## Gotchas
- **The "flag in a hot path" anti-pattern.** Cache the
  flag.
- **The "no kill switch" anti-pattern.** Every feature
  should have a kill switch.
- **The "long-lived flag" anti-pattern.** Remove flags
  after 90 days at 100%.
- **The "non-deterministic rollout" anti-pattern.** Use a
  hash for stable bucketing.

## Related
- `feature-flags.md`
- `feature-flags-best-practices.md`
- `feature-flags-implementations.md`
- `feature-flags-vendors.md`
- `feature-toggles-vs-branches.md`
- `feature-rollout-strategies.md`
