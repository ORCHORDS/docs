# Funnel Tracking with Cloudflare Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need step-over-step conversion rates for a multi-step user funnel (sign-up, onboarding, activation) without sending data to a third-party analytics vendor. Cloudflare Analytics Engine lets you write structured data points from any Worker and query them with SQL, making it a zero-latency, privacy-first alternative to Mixpanel or Amplitude.

---

## Context
Cloudflare Analytics Engine (AE) stores data points written via the `writeDataPoint()` method on the `env.ANALYTICS` binding. Each data point carries up to three arrays: `indexes` (strings used for grouping/filtering), `blobs` (arbitrary string metadata), and `doubles` (numeric values). Data is queryable through the Analytics Engine SQL API within minutes of ingestion. The funnel approach here records one data point per funnel step per user, then aggregates with `COUNT(DISTINCT blob1)` to measure unique users at each step. Cohort analysis is done by storing the signup date in `blob3` and filtering at query time.

---

## Setup / Config

```toml
# wrangler.toml
name = "funnel-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "funnel_events"
```

Enable the Analytics Engine dataset in the Cloudflare dashboard under **Workers & Pages → Analytics Engine** before first use.

---

## Implementation

```typescript
// src/index.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

type FunnelStep =
  | "signup_start"
  | "email_verified"
  | "profile_complete"
  | "first_purchase";

/**
 * Record a funnel step for a given user.
 *
 * Layout:
 *   indexes[0] = userId          — partition key for per-user queries
 *   blob1      = step name       — funnel step identifier
 *   blob2      = sessionId       — ties steps within a browsing session
 *   blob3      = signupDate      — ISO date (YYYY-MM-DD) for cohort slicing
 *   double1    = unix timestamp  — precise event time in seconds
 */
export function recordFunnelStep(
  analytics: AnalyticsEngineDataset,
  userId: string,
  step: FunnelStep,
  sessionId: string,
  signupDate: string
): void {
  analytics.writeDataPoint({
    indexes: [userId],
    blobs: [step, sessionId, signupDate],
    doubles: [Date.now() / 1000],
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname, searchParams } = new URL(request.url);

    // Example: POST /funnel  body: { userId, step, sessionId, signupDate }
    if (request.method === "POST" && pathname === "/funnel") {
      const body = await request.json<{
        userId: string;
        step: FunnelStep;
        sessionId: string;
        signupDate: string;
      }>();

      recordFunnelStep(
        env.ANALYTICS,
        body.userId,
        body.step,
        body.sessionId,
        body.signupDate
      );

      return new Response(JSON.stringify({ ok: true }), {
        headers: { "content-type": "application/json" },
      });
    }

    return new Response("not found", { status: 404 });
  },
};
```

---

## SQL Queries — Conversion Rates and Drop-off

```sql
-- Step-over-step unique user counts for the last 7 days
SELECT
  blob1                          AS step,
  COUNT(DISTINCT index1)         AS unique_users
FROM funnel_events
WHERE timestamp > NOW() - INTERVAL '7' DAY
GROUP BY step
ORDER BY unique_users DESC;

-- Conversion rate: each step vs signup_start baseline
WITH base AS (
  SELECT COUNT(DISTINCT index1) AS total
  FROM funnel_events
  WHERE blob1 = 'signup_start'
    AND timestamp > NOW() - INTERVAL '7' DAY
)
SELECT
  blob1 AS step,
  COUNT(DISTINCT index1) AS users,
  ROUND(COUNT(DISTINCT index1) * 100.0 / (SELECT total FROM base), 2) AS pct_of_start
FROM funnel_events
WHERE timestamp > NOW() - INTERVAL '7' DAY
GROUP BY step
ORDER BY users DESC;

-- Cohort analysis: conversion by signup date (blob3)
SELECT
  blob3 AS signup_date,
  blob1 AS step,
  COUNT(DISTINCT index1) AS users
FROM funnel_events
WHERE timestamp > NOW() - INTERVAL '30' DAY
GROUP BY signup_date, step
ORDER BY signup_date DESC, users DESC;
```

Run queries against the Analytics Engine SQL API:

```bash
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: text/plain" \
  --data "SELECT blob1 AS step, COUNT(DISTINCT index1) AS users \
FROM funnel_events \
WHERE timestamp > NOW() - INTERVAL '7' DAY \
GROUP BY step \
ORDER BY users DESC"
```

---

## Anti-patterns
- **Writing one data point per page view instead of per step** — AE has a 25 data points/request limit and a daily write budget; record only meaningful conversion events.
- **Storing userId as a blob instead of an index** — `indexes` are the partitioning keys; placing high-cardinality values in blobs makes `GROUP BY` scans much slower.
- **Querying AE for real-time dashboards on every page load** — AE SQL API has rate limits; cache query results in KV with a 60-second TTL.
- **Omitting signupDate from the data point** — without a cohort dimension you cannot separate organic growth from campaign spikes retroactively.

---

## Gotchas
- Analytics Engine data is available for querying within ~2 minutes of `writeDataPoint()`; do not expect sub-second visibility.
- `blob` fields are limited to 1 KB each; truncate long session IDs or UUIDs before writing.
- The free tier allows 100 K data points/day per dataset; upgrade to Workers Paid for higher limits.
- `COUNT(DISTINCT index1)` is supported but `COUNT(DISTINCT blob1)` is not — always put your deduplication key in `indexes`.
- Timestamps in SQL queries use the AE internal `timestamp` column, not `double1`; `double1` is useful for sub-second ordering but not for `INTERVAL` arithmetic.

---

## Verification

```bash
# Write a test data point via the Worker
curl -X POST https://funnel-worker.example.workers.dev/funnel \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u_test_001","step":"signup_start","sessionId":"sess_abc","signupDate":"2026-08-24"}'

# Wait ~2 minutes, then query AE
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: text/plain" \
  --data "SELECT blob1, COUNT(DISTINCT index1) AS users FROM funnel_events WHERE index1 = 'u_test_001' GROUP BY blob1"

# Expected: { "data": [{ "blob1": "signup_start", "users": 1 }] }
```

---

## Related
- `workers-opentelemetry-trace-export-d1.md`
- `workers-uptime-cron-d1-alert-queue.md`

---

## Sources
- Cloudflare Analytics Engine docs — https://developers.cloudflare.com/analytics/analytics-engine/
- Analytics Engine SQL API reference — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Workers Bindings: Analytics Engine — https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
