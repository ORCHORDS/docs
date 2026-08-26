# feature-cookbook-analytics

**Issue:** Analytics — events, funnels, dashboards
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a feature. You want to know: are people using it?
You don't have analytics. You add a console.log. The logs
overwhelm the system. You turn off the logs. You have no
data. You wish you had a proper analytics system.

## Root cause
**Analytics is a feature, not a console.log.** Build it
right.

**Source:** Various analytics guides.

## The "event" pattern

For each user action, emit an event:
```ts
async function trackEvent(event: AnalyticsEvent, env: Env): Promise<void> {
  await env.ANALYTICS.writeDataPoint({
    blobs: [event.name, event.userId, event.tenantId, event.properties?.category],
    doubles: [event.value ?? 1],
    indexes: [event.tenantId, event.name],
  });
}

// Usage
await trackEvent({
  name: 'user.login',
  userId: ctx.user.id,
  tenantId: ctx.tenant.id,
  properties: { method: 'password' },
}, env);
```

The event is structured; the query is fast.

## The "CF Analytics Engine" pattern

For high-volume, low-cost:
```ts
env.ANALYTICS.writeDataPoint({
  blobs: ['event-name', userId, tenantId],  // Indexed
  doubles: [duration],  // Numeric
  indexes: [tenantId, 'event-name'],  // For fast query
});
```

CF Analytics Engine is designed for this. Cheap, fast.

## The "pageview" pattern

For web analytics:
```ts
// On the client
function trackPageview(path: string): void {
  navigator.sendBeacon('/api/analytics', JSON.stringify({
    type: 'pageview',
    path,
    referrer: document.referrer,
    userAgent: navigator.userAgent,
    timestamp: Date.now(),
  }));
}

// On the server
export async function handleAnalytics(request: Request, env: Env): Promise<Response> {
  const event = await request.json();
  await env.ANALYTICS.writeDataPoint({
    blobs: ['pageview', event.path, event.referrer],
    doubles: [event.timestamp],
    indexes: [event.path],
  });
  return new Response('OK', { status: 204 });
}
```

`sendBeacon` is non-blocking; the page unload doesn't wait.

## The "funnel" pattern

For conversion analysis:
```ts
async function trackFunnelStep(userId: string, funnel: string, step: string, env: Env): Promise<void> {
  await env.ANALYTICS.writeDataPoint({
    blobs: [funnel, step, userId],
    doubles: [1],
    indexes: [funnel, step],
  });
}

// Usage in onboarding
await trackFunnelStep(user.id, 'onboarding', 'step1_signup', env);
await trackFunnelStep(user.id, 'onboarding', 'step2_verify_email', env);
await trackFunnelStep(user.id, 'onboarding', 'step3_complete_profile', env);
await trackFunnelStep(user.id, 'onboarding', 'step4_first_action', env);

// Query: 100 signed up, 80 verified, 50 completed profile, 20 did first action
// Conversion: 20%
```

The funnel shows where users drop off.

## The "retention" pattern

For cohort analysis:
```ts
async function getRetention(cohort: string, day: number, env: Env): Promise<number> {
  // Query: of users who signed up on day 0, how many were active on day N?
  const result = await env.ANALYTICS.query({
    query: `
      SELECT count(DISTINCT userId) AS active
      FROM events
      WHERE event = 'user.active'
        AND userId IN (SELECT userId FROM events WHERE event = 'user.signup' AND date = '2026-08-09')
        AND date = date_add('2026-08-09', INTERVAL ? DAY)
    `,
    params: [day],
  });
  return result.active / cohortSize;
}
```

Retention = (active on day N) / (cohort size).

## The "feature usage" pattern

For "is this feature being used?":
```ts
async function trackFeatureUse(feature: string, userId: string, env: Env): Promise<void> {
  await env.ANALYTICS.writeDataPoint({
    blobs: [feature, userId],
    doubles: [1],
    indexes: [feature],
  });
}

// Query: how many users used this feature in the last 7 days?
const result = await env.ANALYTICS.query({
  query: `
    SELECT count(DISTINCT userId) AS users
    FROM events
    WHERE event = ?
      AND timestamp > now() - INTERVAL '7' DAY
  `,
  params: [feature],
});
```

Track usage; measure adoption.

## The "cohort" pattern

For cohort analysis (users grouped by signup date):
```sql
SELECT
  date_trunc('day', signup_at) AS cohort,
  count(DISTINCT user_id) AS size,
  count(DISTINCT CASE WHEN last_active > signup_at + INTERVAL '7' DAY THEN user_id END) AS d7_retention
FROM users
GROUP BY cohort
ORDER BY cohort DESC;
```

Cohorts let you compare retention over time.

## The "dashboard" pattern

For a metrics dashboard:
```ts
async function getDashboardMetrics(env: Env): Promise<DashboardMetrics> {
  // 1. DAU
  const dau = await env.ANALYTICS.query({
    query: `SELECT count(DISTINCT userId) AS dau FROM events WHERE event = 'user.active' AND timestamp > now() - INTERVAL '1' DAY`,
  });

  // 2. New signups
  const signups = await env.ANALYTICS.query({
    query: `SELECT count() AS count FROM events WHERE event = 'user.signup' AND timestamp > now() - INTERVAL '1' DAY`,
  });

  // 3. Conversion
  const conversion = signups.count / visits.count;

  return { dau, signups, conversion };
}
```

The dashboard is the source of truth.

## The "privacy" pattern

For GDPR-compliant analytics:
- **No PII:** Don't include email, name, phone in events
- **Hash user IDs:** Use a one-way hash; can match but not
  reverse
- **Anonymize IP:** Truncate the IP
- **Consent:** Only track with consent

```ts
function hashUserId(userId: string): string {
  return crypto.subtle.digest('SHA-256', new TextEncoder().encode(userId + env.SALT)).then(b => Buffer.from(b).toString('hex'));
}
```

The user ID is hashed; PII is not stored.

## The "third-party" choice

For managed analytics:
- **Amplitude:** Product analytics
- **Mixpanel:** Product analytics
- **PostHog:** Self-hostable
- **Plausible:** Privacy-focused
- **Google Analytics:** Web (with consent)
- **CF Analytics Engine:** Built-in for CF Workers

For most apps, **CF Analytics Engine + a hosted product
analytics tool** is the right combination.

## The "event taxonomy" pattern

For consistent events, define a taxonomy:
```markdown
## Event taxonomy

### Format
`{object}.{action}`

### Examples
- `user.signed_up`
- `user.logged_in`
- `user.updated_profile`
- `post.created`
- `post.liked`
- `comment.created`
- `payment.completed`
- `payment.failed`

### Properties
- **userId:** The user ID (hashed)
- **tenantId:** The tenant ID
- **timestamp:** ISO 8601
- **properties:** Action-specific data
```

The taxonomy is the contract.

## The "real-time" pattern

For real-time dashboards:
```ts
// Use a WebSocket or SSE
const stream = await env.ANALYTICS.queryStream({
  query: `SELECT * FROM events WHERE timestamp > now() - INTERVAL '1' MINUTE`,
});

for await (const event of stream) {
  // Push to the dashboard
}
```

The dashboard updates in real-time.

## Verification
- **Test:** Event is tracked
- **Test:** Funnel is computed correctly
- **Live:** Dashboard shows the metrics
- **Audit:** Quarterly review of events

## Gotchas
- **The "track everything" anti-pattern.** Too many events
  overwhelm the system. Track what matters.
- **The "PII in events" anti-pattern.** A user email in an
  event is a GDPR issue. Hash + anonymize.
- **The "no retention" anti-pattern.** Old events pile up.
  Set a retention period.
- **The "different schemas" anti-pattern.** Every event
  has a different shape. Use a taxonomy.
- **The "no consent" anti-pattern.** Tracking without
  consent is illegal in many places.

## Related
- `observability-three-pillars-detail.md`
- `feature-observability-pattern.md`
- `gdpr-article-17-erasure.md`
- `audit-log-as-product.md`
- CF Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Amplitude: https://amplitude.com/
- PostHog: https://posthog.com/
- Plausible: https://plausible.io/
