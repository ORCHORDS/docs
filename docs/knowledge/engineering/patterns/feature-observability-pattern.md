# feature-observability-pattern

**Issue:** How to design observability into a feature
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a new feature. The dashboard shows the new metric
is 0. Six months later, the user says "this feature is
broken." You investigate. There's no data. You don't know
if the feature is being used, if it's slow, or if it's
erroring.

## Root cause
**Features need observability from day 1.** Without it,
you can't answer "is this feature working?"

**Source:** Honeycomb — Feature observability:
https://www.honeycomb.io/

## The "5 things to observe" pattern

For every feature, observe:
1. **Usage:** How often is it called? By whom?
2. **Latency:** How long does it take? (p50, p95, p99)
3. **Errors:** How often does it fail? Why?
4. **Business outcome:** What's the conversion? Retention?
5. **User feedback:** What do users say?

## The "usage" pattern

Track usage:
```ts
async function trackFeatureUsage(featureName: string, ctx: McContext, env: Env): Promise<void> {
  await env.ANALYTICS.writeDataPoint({
    blobs: [featureName, ctx.user.id, ctx.tenant.id],
    doubles: [1],
    indexes: [ctx.tenant.id],
  });
}

// In the feature
await trackFeatureUsage('new-dashboard', ctx, env);
```

For business reporting:
- **Daily active users (DAU):** Unique users using the
  feature per day
- **Weekly active users (WAU):** Per week
- **Monthly active users (MAU):** Per month
- **Adoption rate:** % of users using the feature

## The "latency" pattern

Track latency:
```ts
const start = Date.now();
try {
  const result = await doTheThing(input, ctx);
  const duration = Date.now() - start;
  metrics.histogram('feature.duration_ms', duration, { feature: 'new-dashboard', status: 'success' });
  return result;
} catch (err) {
  const duration = Date.now() - start;
  metrics.histogram('feature.duration_ms', duration, { feature: 'new-dashboard', status: 'error' });
  throw err;
}
```

The histogram shows the distribution. The dashboard shows
p50, p95, p99.

## The "error" pattern

Track errors:
```ts
try {
  // ... do work
} catch (err) {
  // 1. Increment the error counter
  metrics.increment('feature.errors_total', { feature: 'new-dashboard', error_code: getErrorCode(err) });

  // 2. Capture in Sentry (with context)
  Sentry.captureException(err, {
    tags: { feature: 'new-dashboard' },
    extra: { userId: ctx.user.id, requestId: ctx.requestId },
  });

  // 3. Log
  logEvent('feature.error', 'error', { feature: 'new-dashboard', error: String(err) });

  throw err;
}
```

Three signals: counter, Sentry, log. The counter is for
alerts; Sentry is for diagnosis; the log is for forensic
analysis.

## The "business outcome" pattern

For business metrics, track conversion:
```ts
async function trackFunnel(userId: string, step: string, env: Env): Promise<void> {
  await env.ANALYTICS.writeDataPoint({
    blobs: [userId, step],
    doubles: [1],
    indexes: [step],
  });
}

// In the feature
await trackFunnel(ctx.user.id, 'viewed_dashboard', env);
await trackFunnel(ctx.user.id, 'clicked_settings', env);
await trackFunnel(ctx.user.id, 'completed_setup', env);
```

The funnel shows: 100 viewed, 30 clicked, 5 completed.
5% conversion.

## The "A/B test observability" pattern

For A/B tests, track the variant:
```ts
const variant = await getVariant('new-dashboard', ctx);
metrics.increment('feature.usage_total', { feature: 'new-dashboard', variant });
```

The dashboard shows usage by variant. Statistical analysis
determines which variant is better.

## The "user feedback" pattern

For qualitative feedback:
```ts
// In the UI
<button onclick="sendFeedback('useful')">👍 This was useful</button>
<button onclick="sendFeedback('not_useful')">👎 Not useful</button>

// In the API
async function recordFeedback(input: FeedbackInput, ctx: McContext, env: Env): Promise<void> {
  await env.ANALYTICS.writeDataPoint({
    blobs: [input.feature, input.sentiment, ctx.user.id],
    doubles: [1],
    indexes: [input.feature],
  });
}
```

The dashboard shows feedback by feature. Low-rated
features are candidates for redesign.

## The "feature dashboard" pattern

For each feature, a dashboard with:
- **Usage:** DAU, WAU, MAU
- **Latency:** p50, p95, p99
- **Errors:** error rate, error types
- **Conversion:** funnel steps
- **Feedback:** sentiment breakdown

The dashboard is the source of truth for feature health.

## The "feature health" pattern

For automated health, a "feature health" metric:
```ts
// Combine into a single score
const usage = getUsageRate('new-dashboard', '7d');
const errorRate = getErrorRate('new-dashboard', '7d');
const latency = getP99Latency('new-dashboard', '7d');

let health = 'healthy';
if (errorRate > 0.01) health = 'degraded';
if (errorRate > 0.05 || latency > 1000) health = 'unhealthy';

metrics.gauge('feature.health', healthScore(health), { feature: 'new-dashboard' });
```

The health is a single number; the dashboard shows it as
a color (green/yellow/red).

## The "feature kill criteria" pattern

For a risky feature, define kill criteria upfront:
```markdown
## Feature: New dashboard

### Kill criteria
- Error rate > 5% for 10 min → disable
- p99 latency > 2s for 10 min → disable
- Conversion drops > 30% vs old dashboard → disable
- 3+ P0 bugs in 1 week → disable
```

The criteria are defined before launch; the kill switch is
the action.

## The "feature sunset" pattern

When a feature is no longer useful, sunset it:
1. **Announce:** Tell users the feature is going away
2. **Warn:** In the UI, show "this feature is being
   removed"
3. **Track:** Count users still using the feature
4. **Disable:** When usage drops to near zero, disable
5. **Remove:** Delete the code

A feature is not "forever." It's a tool with a lifecycle.

## Verification
- **Test:** Metrics are emitted on every feature call
- **Live:** Dashboard shows the feature's health
- **Audit:** Quarterly review of feature health

## Gotchas
- **The "metrics without action" anti-pattern.** Every
  metric should have an owner + an action.
- **The "100% observability" anti-pattern.** Some things
  are not worth observing. Focus on the user-impacting
  ones.
- **The "A/B test without statistical significance" anti-
  pattern.** A 10% difference in 100 users is not
  significant. Wait for n > 1000 (or use a power
  calculator).
- **The "kill switch missing" anti-pattern.** Every
  feature should have a kill switch.
- **The "feature forever" anti-pattern.** Features have a
  lifecycle; sunset them when they're no longer useful.

## Related
- `observability-three-pillars-detail.md`
- `observability-metrics-design-detail.md`
- `error-budget-slo.md`
- `feature-flags.md` (kill switch)
- `feature-flags-best-practices.md`
- `feature-gating-implementation.md`
- Honeycomb: https://www.honeycomb.io/
- Amplitude: https://amplitude.com/
- Mixpanel: https://mixpanel.com/
