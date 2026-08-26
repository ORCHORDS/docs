# feature-toggles-detail

**Issue:** Practical feature toggle patterns — types, SDK, evaluation
**Date:** 2026-08-09
**Status:** documented

## Symptom
You want to ship a new feature to 1% of users. You add a
boolean check in the code. You redeploy. You change the
check. You redeploy. The cycle takes 10 min per change.
You want real-time toggle changes.

## Root cause
**Compile-time flags are slow to change.** Runtime flags
(evaluated per request) are fast.

**Source:** Various feature flag guides.

## The "runtime flag" pattern

```ts
async function isFeatureEnabled(name: string, ctx: McContext): Promise<boolean> {
  // 1. Check in-memory cache
  if (flagCache.has(name)) return flagCache.get(name)!;

  // 2. Fall back to KV (or D1)
  const flag = await ctx.env.KV.get<FeatureFlag>(`flag:${name}`, 'json');
  if (!flag) return false;

  // 3. Evaluate
  const result = evaluate(flag, ctx);

  // 4. Cache
  flagCache.set(name, result);

  return result;
}
```

The flag is evaluated per request. Changes in the KV are
seen within 30-60s (KV eventual consistency) or immediately
(if using D1).

## The "flag types" pattern

Different types for different use cases:

### Boolean
```ts
const isNewDashboard = await isFeatureEnabled('new-dashboard', ctx);
if (isNewDashboard) {
  return renderNewDashboard();
} else {
  return renderOldDashboard();
}
```

### Percentage rollout
```ts
function isInRollout(userId: string, flagName: string, percentage: number): boolean {
  const hash = crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${userId}:${flagName}`));
  const bucket = parseInt(toHex(new Uint8Array(hash).slice(0, 4)), 16) % 100;
  return bucket < percentage;
}
```

The user is deterministically in or out of the rollout.

### Variant (A/B test)
```ts
function pickVariant(userId: string, flag: VariantFlag): string {
  const hash = ...;
  const bucket = ...;
  let cumulative = 0;
  for (const variant of flag.variants) {
    cumulative += variant.percentage;
    if (bucket < cumulative) return variant.name;
  }
  return flag.variants[0].name;
}

const variant = await getVariant('button-color', ctx);
// variant: 'red' | 'blue' | 'green'
```

### Targeting rules
```ts
interface TargetingRule {
  attribute: string;  // 'plan', 'country', 'role', etc.
  operator: 'equals' | 'in' | 'not_in' | 'contains';
  values: any[];
}

function matchesRule(rule: TargetingRule, context: McContext): boolean {
  const value = getAttribute(rule.attribute, context);
  switch (rule.operator) {
    case 'equals': return value === rule.values[0];
    case 'in': return rule.values.includes(value);
    case 'not_in': return !rule.values.includes(value);
    case 'contains': return String(value).includes(rule.values[0]);
  }
}
```

A user on the `pro` plan in `US` with `role: admin` matches
specific rules.

## The "flag SDK" pattern

For client-side, use a SDK:
```ts
// Initialize
const flags = new FeatureFlagClient({ apiKey: env.FLAGS_API_KEY });

// Use
if (await flags.isEnabled('new-dashboard')) {
  // ...
}

// Variant
const variant = await flags.getVariant('button-color');

// Targeting
const isInCohort = await flags.matches('plan:pro', { userId: 'u_123', plan: 'pro' });
```

The SDK handles caching, refresh, evaluation.

## The "SDK caching" pattern

The SDK caches flags in memory:
```ts
class FeatureFlagClient {
  private cache = new Map<string, FeatureFlag>();

  async isEnabled(name: string): Promise<boolean> {
    if (this.cache.has(name)) return evaluate(this.cache.get(name)!);

    const flag = await this.fetchFlag(name);
    this.cache.set(name, flag);
    return evaluate(flag);
  }

  // Refresh every 30s
  startRefresh(intervalMs = 30_000): void {
    setInterval(async () => {
      const flags = await this.fetchAllFlags();
      this.cache = new Map(flags.map(f => [f.name, f]));
    }, intervalMs);
  }
}
```

The SDK refreshes in the background; the request is fast.

## The "streaming flags" pattern

For real-time flag changes (no 30s delay):
```ts
// Server-sent events
const eventSource = new EventSource('/api/flags/stream');
eventSource.addEventListener('flag', (event) => {
  const flag = JSON.parse(event.data);
  this.cache.set(flag.name, flag);
});
```

The server pushes flag changes; the client updates in
real-time.

## The "flag override" pattern

For testing, allow override:
```ts
// From a cookie
const override = getCookie('flag-override')?.split(',');
for (const o of override ?? []) {
  const [name, value] = o.split('=');
  this.cache.set(name, JSON.parse(value));
}
```

A user with the cookie can override flags for testing.

## The "evaluation context" pattern

The context passed to the flag system:
```ts
interface EvaluationContext {
  userId: string;
  tenantId: string;
  email: string;
  plan: string;
  country: string;
  role: string;
  createdAt: string;
  // ... custom attributes
}

function buildContext(ctx: McContext): EvaluationContext {
  return {
    userId: ctx.user.id,
    tenantId: ctx.tenant.id,
    email: ctx.user.email,
    plan: ctx.user.plan,
    country: ctx.user.country,
    role: ctx.user.role,
    createdAt: ctx.user.createdAt,
  };
}
```

The context is consistent across evaluations.

## The "flag in D1" pattern

For full control, store flags in D1:
```sql
CREATE TABLE feature_flags (
  name TEXT PRIMARY KEY,
  type TEXT NOT NULL,  -- 'boolean', 'percentage', 'variant', 'rules'
  enabled INTEGER NOT NULL DEFAULT 1,
  config TEXT NOT NULL,  -- JSON
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

```ts
async function isFeatureEnabled(name: string, context: EvaluationContext, env: Env): Promise<boolean> {
  const flag = await env.DB!.prepare(
    `SELECT * FROM feature_flags WHERE name = ?`
  ).bind(name).first<FeatureFlag>();

  if (!flag || !flag.enabled) return false;

  return evaluate(JSON.parse(flag.config), context);
}
```

## The "flag caching across isolates" pattern

For CF Workers, each isolate has its own cache. To share:
```ts
let sharedCache: Map<string, FeatureFlag> | null = null;

async function loadSharedCache(env: Env): Promise<Map<string, FeatureFlag>> {
  // Use CF's Cache API as a shared cache
  const cache = caches.default;
  const cached = await cache.match('https://flags/all');
  if (cached) {
    const flags = await cached.json();
    return new Map(flags.map(f => [f.name, f]));
  }

  // Fetch all flags
  const flags = await fetchAllFlags(env);
  const response = new Response(JSON.stringify(flags));
  await cache.put('https://flags/all', response);
  return new Map(flags.map(f => [f.name, f]));
}
```

The Cache API is shared across all isolates in a region.

## The "flag evaluation logging" pattern

For analytics, log every evaluation:
```ts
function logEvaluation(name: string, result: boolean, context: EvaluationContext): void {
  console.log({
    timestamp: new Date().toISOString(),
    flag: name,
    result,
    userId: context.userId,
    tenantId: context.tenantId,
  });
}
```

This data feeds into analytics (Datadog, etc.).

## The "kill switch" pattern

For a critical feature, always have a kill switch:
```ts
// In the code
if (await isFeatureEnabled('risky-feature', ctx)) {
  return runRiskyFeature();
} else {
  return runSafeFeature();
}

// To kill: disable the flag
// The next request uses the safe path
```

The kill switch is the safety net.

## Verification
- **Test:** `test/flags.test.ts > rollout is deterministic
  for same user` — passes
- **Test:** `test/flags.test.ts > kill switch disables
  feature` — passes
- **Live:** Flag changes are logged + analyzed
- **Audit:** Quarterly review of flag list

## Gotchas
- **The "flag in a hot path" perf issue.** Each evaluation
  is a lookup. Cache the results.
- **The "flag change is not instant" gotcha.** KV is
  eventually consistent; D1 is strongly consistent. Pick
  the right one.
- **The "deterministic hash" is essential.** A non-
  deterministic rollout means a user is sometimes in,
  sometimes out.
- **The "kill switch is the most important flag" rule.**
  Every feature should have a kill switch.
- **The "long-lived flag" anti-pattern.** Remove flags
  after 90 days at 100%.

## Related
- `feature-flags.md`
- `feature-flags-best-practices.md`
- `feature-flags-implementations.md`
- `feature-toggles-vs-branches.md`
- LaunchDarkly: https://launchdarkly.com/
- GrowthBook: https://www.growthbook.io/
- Unleash: https://www.getunleash.io/
