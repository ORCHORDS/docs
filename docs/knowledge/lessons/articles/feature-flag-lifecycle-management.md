# Feature Flag Lifecycle Management

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your codebase has hundreds of feature flags, many of which were "temporary"
but have been active for years. No one knows which flags are safe to
remove. New engineers encounter nested flag conditions and cannot
determine the intended behavior. Flag configurations are scattered across
multiple systems with no central inventory. Removing a flag requires
days of investigation to verify it is not still in use.

## Context

Feature flags (feature toggles) enable deploying code to production
without exposing it to all users, supporting gradual rollouts, A/B
testing, and kill switches. However, without lifecycle management, flags
accumulate as technical debt — LaunchDarkly recommends a 90-120 day
time-to-archive target for temporary flags. In 2026, leading teams treat
feature flags as first-class entities with defined lifecycles, owners,
expiration dates, and automated cleanup workflows.

## Flag lifecycle stages

```
1. Proposed   → Flag requested with business justification
2. Created    → Flag defined in flag management system
3. Developing → Code instrumented with flag checks
4. Testing    → Flag toggled in staging/preview environments
5. Rolled out → Flag enabled for 100% of production users
6. Archived   → Flag removed from code and configuration
```

### Stage transitions

| Transition | Trigger | Action |
|---|---|---|
| Proposed → Created | Technical review | Define flag key, type, default value, owner |
| Created → Developing | Sprint planning | Add flag checks in application code |
| Developing → Testing | PR merged | Verify flag behavior in non-production |
| Testing → Rolled out | Gradual rollout complete (100%) | Flag is fully on for all users |
| Rolled out → Archived | Cleanup window elapsed | Remove flag from code and config |

## Flag types and expected lifespans

| Type | Purpose | Expected lifespan | Example |
|---|---|---|---|
| **Release** | Gate unfinished features | 1-4 weeks | `new-checkout-flow` |
| **Experiment** | A/B test variants | 2-8 weeks | `pricing-page-v2` |
| **Ops** | Kill switch for risky paths | Permanent (reviewed quarterly) | `enable-new-payment-processor` |
| **Permission** | Entitlement gating | Permanent (tied to plan) | `premium-analytics` |

Only Ops and Permission flags should be permanent. Release and Experiment
flags must have expiration dates.

## Flag naming conventions

```
{scope}.{feature}.{purpose}

Examples:
  checkout.apple-pay.release      → Release flag for Apple Pay in checkout
  pricing.annual-discount.experiment → A/B test for annual discount
  payments.stripe-v3.ops          → Kill switch for Stripe v3 migration
  plan.advanced-analytics.permission → Entitlement for advanced analytics
```

Consistent naming allows automated detection of flag type and expected
lifespan.

## Implementation patterns

### Flag evaluation with default-safe behavior

```typescript
// Safe: feature is OFF by default (flag not found = off)
if (flags.isEnabled('new-checkout-flow', { default: false })) {
  return renderNewCheckout();
}
return renderCurrentCheckout();
```

### Gradual rollout

```
Day 1:  1% of users (canary)
Day 3:  10% of users (early adopters)
Day 7:  25% of users (broader validation)
Day 14: 50% of users (at-scale validation)
Day 21: 100% of users (full rollout)
Day 30: Flag archived (code cleaned up)
```

### Stale flag detection

```typescript
// Flag metadata includes creation date and expected lifespan
const FLAG_METADATA = {
  'new-checkout-flow': {
    created: '2026-07-01',
    type: 'release',
    maxAge: 30, // days
    owner: 'checkout-team',
    jiraTicket: 'SHOP-1234',
  },
};

function detectStaleFlags() {
  const now = Date.now();
  for (const [key, meta] of Object.entries(FLAG_METADATA)) {
    const age = (now - new Date(meta.created).getTime()) / 86400000;
    if (age > meta.maxAge && meta.type !== 'ops' && meta.type !== 'permission') {
      alert(`Stale flag: ${key} (${Math.floor(age)} days old, owner: ${meta.owner})`);
    }
  }
}
```

## Cleanup workflow

### Automated cleanup pipeline

```
1. Detection  → Scan for flags that are 100% on/off for > 14 days
2. Notification → Notify flag owner via Slack/email
3. PR creation → Auto-generate PR removing flag checks
4. Review     → Owner reviews and approves removal
5. Archive    → Remove flag from management system
```

### Code removal patterns

```typescript
// BEFORE: Flag in code
function getPrice(item) {
  if (flags.isEnabled('dynamic-pricing')) {
    return dynamicPricingEngine.calculate(item);
  }
  return item.basePrice;
}

// AFTER: Flag removed (feature is now permanent)
function getPrice(item) {
  return dynamicPricingEngine.calculate(item);
}
```

### Tracking flag debt

| Metric | Healthy | Warning | Critical |
|---|---|---|---|
| Total active flags | < 50 | 50-100 | > 100 |
| Flags older than 90 days | < 10% | 10-25% | > 25% |
| Flags with no owner | 0 | 1-5 | > 5 |
| Time-to-archive (median) | < 30 days | 30-90 days | > 90 days |

## Anti-patterns

- **No expiration date** — creating flags without a planned removal date.
  Every release and experiment flag should have an expiration date set
  at creation time.
- **Nested flag conditions** — code paths gated by multiple flags create
  exponential complexity. If feature B depends on feature A, use a
  single flag or explicit dependency chain.
- **Flag-driven architecture** — using feature flags to manage permanent
  system configuration. Flags are for temporary conditions; permanent
  configuration belongs in config files or environment variables.
- **No flag ownership** — flags without a designated owner become orphans
  that no one is responsible for cleaning up. Every flag must have an
  owner (team or individual).

## Gotchas

- **Stale flag references in tests** — removing a flag from production
  code but leaving it in test fixtures causes test failures. Include
  tests in the cleanup PR.
- **Flag evaluation performance** — evaluating hundreds of flags per
  request adds latency. Cache flag state at the start of each request
  and evaluate once. Avoid calling the flag service per-evaluation.
- **Database migrations behind flags** — schema changes cannot be easily
  rolled back with a flag toggle. Separate data migrations from feature
  flags.
- **Distributed flag consistency** — in a microservices architecture,
  different services may see different flag states during a rollout.
  Use the same flag evaluation context (user ID, session) across
  services.

## Verification

- Every release and experiment flag has an expiration date.
- Stale flag report runs weekly and is reviewed by engineering leads.
- Median time-to-archive is under 30 days for release flags.
- No flags exist without a designated owner.
- Automated cleanup PRs are generated for flags that reach 100% rollout.
- Flag count is tracked as a team metric (like code coverage or test count).

## Related

- `documentation/docs/policies/lessons/tech-debt-management-prioritization.md`
- `documentation/docs/policies/lessons/blameless-postmortem-incident-review.md`
- `documentation/docs/policies/testing/event-driven-async-api-testing.md`

## Source URLs (verified 2026-08-16)

- LaunchDarkly flag lifecycle — https://launchdarkly.com/docs/guides/flags/flag-lifecycle
- Martin Fowler feature toggles — https://martinfowler.com/articles/feature-toggles.html
- Feature flag best practices (DevCycle) — https://devcycle.com/blog/feature-flag-best-practices
- ConfigCat stale flags — https://configcat.com/blog/2024/07/02/stale-feature-flags/
