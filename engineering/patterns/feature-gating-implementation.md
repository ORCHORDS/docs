# feature-gating-implementation

**Issue:** Gate features by user plan, role, age, region
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app has 3 plans: free, pro, enterprise. Each plan
allows different features. You add a check in every
endpoint: `if (user.plan === 'pro')`. Then you add a 4th
plan. The check is everywhere. The code is 100 places.
You miss one. A free user gets a pro feature.

## Root cause
**Feature gating is everywhere.** A new feature touches many
endpoints. The check is duplicated. A bug in one place is
a feature leak.

**Source:** Stripe — Subscription tiers:
https://stripe.com/docs/billing/subscriptions/overview

## The "centralized feature gate" pattern

```ts
// Define the plan → features mapping once
const PLAN_FEATURES: Record<Plan, Set<Feature>> = {
  free: new Set(['basic', 'read']),
  pro: new Set(['basic', 'read', 'write', 'export']),
  enterprise: new Set(['basic', 'read', 'write', 'export', 'sso', 'audit']),
};

type Feature = 'basic' | 'read' | 'write' | 'export' | 'sso' | 'audit';
type Plan = 'free' | 'pro' | 'enterprise';

function hasFeature(plan: Plan, feature: Feature): boolean {
  return PLAN_FEATURES[plan]?.has(feature) ?? false;
}

// In the handler
if (!hasFeature(ctx.user.plan, 'export')) {
  return jsonError('Feature not available on your plan', 402);
}
```

✅ **Single source of truth** for the plan → features map
✅ **Easy to add a plan** (add one row)
✅ **Easy to add a feature** (add to relevant plans)
❌ **Static map** — doesn't handle per-user overrides, trial
periods, etc.

## The "user-level feature flag" pattern

For per-user overrides (a free user has a trial, an
enterprise user is grandfathered):
```ts
interface User {
  plan: Plan;
  planOverride?: Plan;  // For trials, grandfathering, etc.
  planExpiresAt?: string;  // For trials
  customFeatures?: Feature[];  // For custom deals
}

function getEffectivePlan(user: User): Plan {
  if (user.planOverride) return user.planOverride;
  if (user.planExpiresAt && new Date(user.planExpiresAt) < new Date()) {
    return 'free';  // Trial expired
  }
  return user.plan;
}

function hasFeature(user: User, feature: Feature): boolean {
  const effectivePlan = getEffectivePlan(user);
  if (user.customFeatures?.includes(feature)) return true;
  return PLAN_FEATURES[effectivePlan]?.has(feature) ?? false;
}
```

## The "middleware" pattern

For applying the check to every endpoint:
```ts
type Handler = (ctx: McContext) => Promise<Response>;

function withFeature(feature: Feature, handler: Handler): Handler {
  return async (ctx) => {
    if (!hasFeature(ctx.user, feature)) {
      return jsonError(`Feature ${feature} not available on your plan`, 402);
    }
    return handler(ctx);
  };
}

// Usage
export const onRequestPost = withFeature('export', async (ctx) => {
  // ... the actual handler
});
```

The check is in one place (the middleware). The handler
doesn't need to know about the gate.

## The "decorator" pattern (TypeScript)

```ts
function RequireFeature(feature: Feature) {
  return function (target: any, propertyKey: string, descriptor: PropertyDescriptor) {
    const original = descriptor.value;
    descriptor.value = async function (ctx: McContext) {
      if (!hasFeature(ctx.user, feature)) {
        return jsonError(`Feature ${feature} not available on your plan`, 402);
      }
      return original.call(this, ctx);
    };
  };
}

class ExportController {
  @RequireFeature('export')
  async exportUsers(ctx: McContext) {
    // ...
  }
}
```

## The "data-driven" approach

For complex feature gating, store the plan → features map
in a database:
```sql
CREATE TABLE plan_features (
  plan TEXT NOT NULL,
  feature TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (plan, feature)
);
```

```ts
async function hasFeature(plan: Plan, feature: Feature): Promise<boolean> {
  const row = await env.DB!.prepare(
    `SELECT enabled FROM plan_features WHERE plan = ? AND feature = ?`
  ).bind(plan, feature).first<{ enabled: number }>();
  return row?.enabled === 1;
}
```

Now the marketing team can change plan features without a
deploy. (For a 21+ social platform, the legal/compliance team
should review changes.)

## The "trial period" pattern

```ts
interface User {
  plan: Plan;
  trialEndsAt?: string;  // For trial users
}

function getEffectivePlan(user: User): Plan {
  if (user.trialEndsAt && new Date(user.trialEndsAt) > new Date()) {
    return 'pro';  // Trial gets pro features
  }
  return user.plan;
}
```

The trial user gets pro features until the trial ends. After
the trial, they revert to the free plan.

## The "graceful degradation" pattern

Instead of denying a feature, degrade it:
```ts
// Free user: 100 API calls per day
// Pro user: 10,000 API calls per day
function getApiLimit(plan: Plan): number {
  return { free: 100, pro: 10_000, enterprise: Infinity }[plan];
}

// Free user: 1 GB storage
// Pro user: 100 GB
function getStorageLimit(plan: Plan): number {
  return { free: 1, pro: 100, enterprise: 10_000 }[plan];
}
```

The free user can use the feature, just with limits. This is
better than denying access.

## The "feature matrix" as documentation

The plan → features map should be in a doc, not just code:
```markdown
| Feature | Free | Pro | Enterprise |
|---|---|---|---|
| Posts | 10 | Unlimited | Unlimited |
| Storage | 100 MB | 1 GB | 10 GB |
| Custom domain | ❌ | ✅ | ✅ |
| API access | ❌ | ✅ | ✅ |
| SSO | ❌ | ❌ | ✅ |
| Audit log | ❌ | ❌ | ✅ |
```

The doc is the contract. The code should match.

## The "test the gate" pattern

For every feature, write a test:
```ts
test('export is available on pro', () => {
  expect(hasFeature({ plan: 'pro' } as User, 'export')).toBe(true);
});

test('export is NOT available on free', () => {
  expect(hasFeature({ plan: 'free' } as User, 'export')).toBe(false);
});

test('export is available on free during trial', () => {
  expect(hasFeature({ plan: 'free', trialEndsAt: '2027-01-01' } as User, 'export')).toBe(true);
});

test('export is NOT available on free after trial', () => {
  expect(hasFeature({ plan: 'free', trialEndsAt: '2020-01-01' } as User, 'export')).toBe(false);
});
```

The tests prove the gate works.

## The "feature discovery" pattern

For UX, expose available features to the client:
```ts
// GET /api/features/me
{
  "plan": "pro",
  "features": {
    "export": true,
    "sso": false,
    "api": true
  },
  "limits": {
    "apiCallsPerDay": 10000,
    "storageGB": 1
  }
}
```

The client uses this to show/hide UI, set expectations.

## Verification
- **Test:** `test/feature-gate.test.ts > every feature has a
  test for each plan` — passes
- **Test:** `test/feature-gate.test.ts > the feature matrix
  matches the docs` — passes
- **Live:** Every paid upgrade is tested in production
- **Audit:** Annual review of plan → features map

## Gotchas
- **The feature gate is in the wrong layer.** A free user
  can't bypass it by editing the client; the gate is on
  the server.
- **The "trial expires" logic must be tested.** A bug means
  the trial user keeps the features forever, or loses them
  too early.
- **The "custom features" path** is for special deals
  (enterprise with custom features). Document it.
- **The "plan upgrade" must be immediate.** A user pays for
  pro; the next request should see `plan = 'pro'`. Webhooks
  from Stripe should update the user record in real time.
- **The "graceful degradation"** is a UX choice. Some
  features should be hard-gated (compliance, legal); others
  should be limited (storage, API).

## Related
- `feature-flags.md` (related but different)
- `feature-flags-best-practices.md`
- `rate-limiting-strategies.md` (plan-based limits)
- `graceful-degradation.md`
- Stripe: https://stripe.com/docs/billing/subscriptions/overview
