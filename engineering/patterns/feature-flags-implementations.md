# feature-flags-implementations

**Issue:** Build a feature flag system without a vendor
**Date:** 2026-08-09
**Status:** documented

## Symptom
You want feature flags. LaunchDarkly costs $10k/month.
You decide to build your own. You start with a config
file. Then you need a dashboard. Then you need
targeting. Then you need rollout. Six months later, you've
built a feature flag system instead of a product.

## Root cause
**Feature flag systems are complex.** Targeting, rollouts,
audit logs, and dashboards are non-trivial. Build vs buy
is a real choice.

**Source:** Various feature flag guides.

## The "build vs buy" decision

### Buy (LaunchDarkly, Split.io, Statsig, GrowthBook, Unleash)
- **Cost:** $0 (open source) to $10k+/month (enterprise)
- **Pros:** Battle-tested, dashboards, audit logs, SDKs
- **Cons:** Cost, vendor lock-in

### Build
- **Cost:** Engineering time (months)
- **Pros:** Custom, no vendor
- **Cons:** Ongoing maintenance, missing features

For most teams, **buy (or use an open-source self-hosted
option like GrowthBook or Unleash)** is the right answer.
Build only if you have a very specific need (e.g. on-prem
only, no external deps).

## The "minimum viable flag system"

If you must build, the minimum:
1. **Flag definition:** name, type, default, rollout %
2. **Evaluation:** per-user, per-tenant
3. **Storage:** D1 table or KV
4. **API:** Read flags; write flags
5. **Caching:** in-memory for the hot path

```sql
CREATE TABLE feature_flags (
  name TEXT PRIMARY KEY,
  type TEXT NOT NULL,  -- 'boolean', 'percentage', 'cohort'
  default_value TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  rollout_percentage INTEGER,  -- 0-100
  cohort_filter TEXT,  -- JSON: e.g. { "plan": "pro" }
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feature_flag_audit (
  id TEXT PRIMARY KEY,
  flag_name TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,  -- 'created', 'updated', 'enabled', 'disabled'
  old_value TEXT,
  new_value TEXT,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## The "flag evaluation" function

```ts
interface FlagContext {
  userId?: string;
  tenantId?: string;
  plan?: string;
  cohort?: string;
}

function evaluateFlag(flag: FeatureFlag, context: FlagContext): boolean {
  // Disabled flag = false
  if (!flag.enabled) return false;

  // Cohort filter
  if (flag.cohortFilter) {
    const filter = JSON.parse(flag.cohortFilter);
    if (!matchesCohort(context, filter)) return false;
  }

  // Rollout
  if (flag.rolloutPercentage !== null && flag.rolloutPercentage < 100) {
    if (!isInRollout(context.userId ?? 'anon', flag.name, flag.rolloutPercentage)) {
      return false;
    }
  }

  return true;
}

function isInRollout(userId: string, flagName: string, percentage: number): boolean {
  // Deterministic hash: same user + flag = same bucket
  const hash = sha256(`${userId}:${flagName}`);
  const bucket = parseInt(hash.slice(0, 8), 16) % 100;
  return bucket < percentage;
}
```

The hash makes the rollout stable: a user in the 50% cohort
stays in (or out) across requests.

## The "flag caching" pattern

For high-throughput apps, cache the flag evaluation:
```ts
class FlagCache {
  private cache = new Map<string, { flag: FeatureFlag; expiresAt: number }>();

  async get(name: string, env: Env): Promise<FeatureFlag | null> {
    const cached = this.cache.get(name);
    if (cached && cached.expiresAt > Date.now()) return cached.flag;

    // Fetch from DB
    const flag = await env.DB!.prepare(
      `SELECT * FROM feature_flags WHERE name = ?`
    ).bind(name).first<FeatureFlag>();

    if (flag) {
      this.cache.set(name, { flag, expiresAt: Date.now() + 30_000 });
    }
    return flag;
  }

  invalidate(name: string) {
    this.cache.delete(name);
  }
}
```

The cache is per-isolate. For cross-isolate invalidation,
use KV or a DO.

## The "flag dashboard" pattern

For a minimal dashboard, use a static page that reads from
D1:
```ts
// /api/admin/flags
export async function listFlags(request: Request, env: Env): Promise<Response> {
  const flags = await env.DB!.prepare(
    `SELECT name, enabled, rollout_percentage, updated_at FROM feature_flags`
  ).all<FeatureFlag>();
  return jsonOk(flags.results);
}

// /api/admin/flags/:name
export async function updateFlag(name: string, request: Request, env: Env): Promise<Response> {
  const data = await request.json();
  await env.DB!.prepare(
    `UPDATE feature_flags SET enabled = ?, rollout_percentage = ?, updated_at = ? WHERE name = ?`
  ).bind(data.enabled, data.rolloutPercentage, new Date().toISOString(), name).run();

  // Audit
  await env.DB!.prepare(
    `INSERT INTO feature_flag_audit (id, flag_name, actor_id, action, new_value) VALUES (?, ?, ?, ?, ?)`
  ).bind(crypto.randomUUID(), name, ctx.user.id, 'updated', JSON.stringify(data)).run();

  return jsonOk({ success: true });
}
```

## The "open source" options

| Tool | Self-hosted | Cloud | License |
|---|---|---|---|
| **Unleash** | ✅ | ✅ | Apache 2.0 |
| **GrowthBook** | ✅ | ✅ | MIT |
| **Flagsmith** | ✅ | ✅ | BSD |
| **Flipt** | ✅ | ❌ | MPL 2.0 |
| **Confidant** | ✅ | ❌ | Apache 2.0 |

For most teams, **Unleash** or **GrowthBook** is a great
choice. Self-host or use the cloud.

## The "flag types" pattern

Different flag types for different use cases:

### Boolean
- `enabled: true/false`
- Use: simple on/off

### Percentage rollout
- `rolloutPercentage: 0-100`
- Use: gradual rollout

### Cohort
- `cohortFilter: { plan: 'pro' }`
- Use: target by plan, role, etc.

### Variant (A/B test)
- `variants: ['A', 'B', 'C']`
- Use: A/B testing; multivariate

## The "flag variants" pattern

For A/B tests:
```sql
CREATE TABLE feature_flag_variants (
  flag_name TEXT NOT NULL,
  variant_name TEXT NOT NULL,
  percentage INTEGER NOT NULL,
  PRIMARY KEY (flag_name, variant_name)
);
```

```ts
function pickVariant(flag: FeatureFlag, userId: string): string {
  const hash = sha256(`${userId}:${flag.name}`);
  const bucket = parseInt(hash.slice(0, 8), 16) % 100;

  let cumulative = 0;
  for (const variant of flag.variants) {
    cumulative += variant.percentage;
    if (bucket < cumulative) return variant.name;
  }
  return flag.variants[0].name;
}
```

The user is deterministically assigned to a variant.

## The "flag cleanup" pattern

For long-lived flags, schedule cleanup:
```sql
-- Find flags that have been at 100% for 90+ days
SELECT name FROM feature_flags
WHERE enabled = 1
  AND rollout_percentage = 100
  AND updated_at < datetime('now', '-90 days');
```

Send a Slack message with the list. Mark them for removal.

## The "kill switch" pattern

For a critical feature, always have a kill switch:
```ts
// In the code
if (await isFeatureEnabled('new-dashboard', ctx)) {
  return renderNewDashboard(user);
} else {
  return renderOldDashboard(user);
}

// To kill: set enabled = 0 in the DB
// The next request uses the old code
```

The kill switch is the safety net for a bad rollout.

## Verification
- **Test:** `test/flags.test.ts > flag evaluation is
  deterministic for same user` — passes
- **Test:** `test/flags.test.ts > cohort filter excludes
  out-of-cohort` — passes
- **Live:** Flag evaluations are logged + analyzed
- **Audit:** Quarterly review of flag list

## Gotchas
- **The "build vs buy" calculation** is non-trivial. A
  self-hosted Unleash takes a day to set up; building your
  own takes months.
- **The "deterministic hash" is essential.** A non-
  deterministic rollout means a user is sometimes in, sometimes
  out — broken UX.
- **The "cache invalidation" is hard.** A flag change must
  propagate fast. KV + eventual consistency = 60s delay.
  D1 + cache = ~30s delay.
- **The "kill switch" is the most important flag.** If only
  one flag is implemented, implement the kill switch.
- **The "flag as config" anti-pattern.** Flags are for
  transient state. Per-user config is a config, not a flag.
- **The "long-lived flag" anti-pattern.** A flag at 100%
  for 90 days is dead code. Remove it.

## Related
- `feature-flags.md`
- `feature-flags-best-practices.md`
- `feature-toggles-vs-branches.md`
- `feature-environment-promotion.md`
- Unleash: https://www.getunleash.io/
- GrowthBook: https://www.growthbook.io/
- LaunchDarkly: https://launchdarkly.com/
