# Analytics Engine User Retention Cohort Query

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Product teams need weekly cohort retention tables — "of users who signed up in week W,
what fraction returned in weeks W+1, W+2 … W+N?" — without shipping data to a third-party
analytics service. On the example project platform, session events are already written to Cloudflare
Analytics Engine from a Tail Worker and a RUM beacon Worker. This article shows how to
write cohort-eligible events, query retention with the Analytics Engine SQL API, and
surface results in a lightweight dashboard Worker.

---

## Context

Analytics Engine supports `GROUP BY` on time buckets and arbitrary `blob` dimensions,
which makes it possible to build cohort queries entirely in SQL without ETL. The key
constraint is the **30-day rolling window** for the free tier (Enterprise customers get
90 days). example project retains a shadow copy in R2-backed Logpush for longer-range analysis,
but day-28 to day-0 cohorts fit natively in Analytics Engine.

Each user action writes one data point. The user identifier is hashed (SHA-256 truncated
to 16 hex chars) before being stored — no PII touches the dataset.

---

## Event Schema

```typescript
// src/analytics/cohort-events.ts

/**
 * Write a user lifecycle event to Analytics Engine.
 *
 * blobs layout:
 *   [0] event_type  – "signup" | "session" | "feature_use"
 *   [1] user_hash   – 16-char truncated SHA-256 of canonical user ID
 *   [2] plan        – "free" | "pro" | "enterprise"
 *   [3] country     – CF-IPCountry or "XX"
 *
 * doubles layout:
 *   [0] session_seconds  – 0 for non-session events
 *
 * indexes[0] = event_type (low cardinality, fast GROUP BY)
 */
export async function writeCohortEvent(
  ae: AnalyticsEngineDataset,
  userId: string,
  eventType: 'signup' | 'session' | 'feature_use',
  plan: string,
  country: string,
  sessionSeconds = 0,
): Promise<void> {
  const hashBuf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(userId),
  );
  const userHash = [...new Uint8Array(hashBuf)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 16);

  ae.writeDataPoint({
    blobs: [eventType, userHash, plan, country],
    doubles: [sessionSeconds],
    indexes: [eventType],
  });
}
```

---

## Signup Cohort Attribution

```typescript
// src/handlers/auth.ts  (excerpt)
import { writeCohortEvent } from '../analytics/cohort-events';

export async function handleSignup(
  request: Request,
  env: Env,
): Promise<Response> {
  const userId = await createUser(request, env.DB);
  const country = request.cf?.country ?? 'XX';

  // Fire-and-forget: do not await so signup latency is unaffected
  env.AE && writeCohortEvent(env.AE, userId, 'signup', 'free', country);

  return new Response(JSON.stringify({ userId }), { status: 201 });
}
```

---

## Analytics Engine SQL Cohort Query

```sql
-- Weekly cohort retention table
-- Returns: cohort_week, retention_week, retained_users, cohort_size, retention_pct

WITH signups AS (
  -- Cohort definition: users who signed up each ISO week
  SELECT
    blob2                                           AS user_hash,
    toStartOfWeek(timestamp)                        AS cohort_week
  FROM example project_USER_EVENTS
  WHERE blob1 = 'signup'
    AND timestamp >= NOW() - INTERVAL '28' DAY
),

sessions AS (
  -- All session events in the same window
  SELECT
    blob2                                           AS user_hash,
    toStartOfWeek(timestamp)                        AS activity_week
  FROM example project_USER_EVENTS
  WHERE blob1 = 'session'
    AND timestamp >= NOW() - INTERVAL '28' DAY
),

cohort_sizes AS (
  SELECT cohort_week, COUNT(DISTINCT user_hash) AS cohort_size
  FROM signups
  GROUP BY cohort_week
),

retention AS (
  SELECT
    s.cohort_week,
    sess.activity_week,
    COUNT(DISTINCT sess.user_hash)                  AS retained_users
  FROM signups s
  JOIN sessions sess ON s.user_hash = sess.user_hash
  WHERE sess.activity_week >= s.cohort_week
  GROUP BY s.cohort_week, sess.activity_week
)

SELECT
  r.cohort_week,
  r.activity_week,
  dateDiff('week', r.cohort_week, r.activity_week)  AS retention_week,
  r.retained_users,
  cs.cohort_size,
  ROUND(100.0 * r.retained_users / cs.cohort_size, 1) AS retention_pct
FROM retention r
JOIN cohort_sizes cs ON r.cohort_week = cs.cohort_week
ORDER BY r.cohort_week DESC, retention_week ASC;
```

---

## Dashboard Worker

```typescript
// src/workers/retention-dashboard.ts
interface Env {
  AE_ACCOUNT_ID: string;
  AE_API_TOKEN: string; // bound secret
}

const AE_ENDPOINT = (accountId: string) =>
  `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`;

const COHORT_SQL = `
  WITH signups AS (
    SELECT blob2 AS user_hash, toStartOfWeek(timestamp) AS cohort_week
    FROM example project_USER_EVENTS
    WHERE blob1 = 'signup' AND timestamp >= NOW() - INTERVAL '28' DAY
  ),
  sessions AS (
    SELECT blob2 AS user_hash, toStartOfWeek(timestamp) AS activity_week
    FROM example project_USER_EVENTS
    WHERE blob1 = 'session' AND timestamp >= NOW() - INTERVAL '28' DAY
  ),
  cohort_sizes AS (
    SELECT cohort_week, COUNT(DISTINCT user_hash) AS cohort_size FROM signups GROUP BY cohort_week
  ),
  retention AS (
    SELECT s.cohort_week, sess.activity_week, COUNT(DISTINCT sess.user_hash) AS retained
    FROM signups s JOIN sessions sess ON s.user_hash = sess.user_hash
    WHERE sess.activity_week >= s.cohort_week
    GROUP BY s.cohort_week, sess.activity_week
  )
  SELECT r.cohort_week, dateDiff('week',r.cohort_week,r.activity_week) AS wk,
         r.retained, cs.cohort_size,
         ROUND(100.0*r.retained/cs.cohort_size,1) AS pct
  FROM retention r JOIN cohort_sizes cs ON r.cohort_week=cs.cohort_week
  ORDER BY r.cohort_week DESC, wk ASC
`;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const res = await fetch(AE_ENDPOINT(env.AE_ACCOUNT_ID), {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.AE_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: COHORT_SQL }),
    });

    if (!res.ok) {
      return new Response('AE query failed', { status: 502 });
    }

    const data = await res.json();
    return new Response(JSON.stringify(data), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## Plan-Segmented Retention

```sql
-- Cohort retention segmented by signup plan
SELECT
  toStartOfWeek(timestamp)                             AS cohort_week,
  blob3                                                AS plan,
  COUNT(DISTINCT blob2)                                AS cohort_size
FROM example project_USER_EVENTS
WHERE blob1 = 'signup'
  AND timestamp >= NOW() - INTERVAL '28' DAY
GROUP BY cohort_week, plan
ORDER BY cohort_week DESC, plan;
```

---

## Anti-patterns

- **Storing raw user IDs in blobs** — PII in Analytics Engine violates GDPR; always hash
  before writing.
- **Using doubles[0] as the cohort key** — doubles are aggregated as sums; cohort identity
  must live in a blob dimension.
- **Querying more than 30 days without Logpush shadow** — free-tier Analytics Engine
  silently drops data older than the retention window; queries appear to show churn when
  the cohort simply aged out.
- **One data point per page-view** — Analytics Engine allows 25 data points per request;
  batch session events in the RUM beacon to reduce write volume.

---

## Gotchas

- `COUNT(DISTINCT blob2)` scans all matching rows; for large datasets (>1 M rows/day)
  query latency may exceed 5 s — cache the result in KV with a 10-minute TTL.
- `toStartOfWeek` anchors to Monday; if your calendar week starts Sunday, use
  `toMonday(timestamp)` or adjust with `dateDiff`.
- Analytics Engine SQL does not support `WITH RECURSIVE`, so pyramid-style N-week
  unrolling must be done client-side by iterating the result set.
- The `_sample_interval` column is always 1 for data points written via `writeDataPoint`;
  multiply `COUNT(*)` by `_sample_interval` only if you use the sampling API.

---

## Verification

```bash
# Quick sanity check: confirm signup events are arriving
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT COUNT(*) AS n FROM example project_USER_EVENTS WHERE blob1='"'"'signup'"'"' AND timestamp >= NOW() - INTERVAL '"'"'1'"'"' DAY"}' \
  | jq '.data[0].n'

# Confirm plan dimension is populated
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob3 AS plan, COUNT(*) AS n FROM example project_USER_EVENTS WHERE blob1='"'"'signup'"'"' GROUP BY plan"}' \
  | jq '.data'
```

---

## Related

- `analytics-engine-funnel-conversion-tracking.md`
- `analytics-engine-multi-tenant-usage-metering.md`
- `rum-beacon-workers-analytics-engine.md`
- `cloudflare-analytics-engine-sql-api-programmatic-querying.md`
- `log-retention-policies.md`

---

## Sources

- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Analytics Engine writeDataPoint: https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- Cohort analysis patterns: https://www.reforge.com/blog/cohort-analysis
- Cloudflare Workers Crypto (SubtleCrypto): https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
