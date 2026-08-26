# Funnel Analysis with Workers Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to measure conversion across multi-step user flows — signup → email verification → paid subscription — and query live conversion rates without exporting data to a third-party warehouse.

## Context

Cloudflare Analytics Engine stores structured data points you write from Workers. Each data point can carry up to 20 blobs (strings) and 20 doubles (numbers). SQL queries run against the dataset via the Analytics Engine SQL API or the `env.ANALYTICS.query()` binding. Because AE is append-only and column-oriented, funnel queries with `COUNT(DISTINCT …) FILTER (WHERE …)` are fast even over millions of rows.

Key design choices:
- `blob1` = funnel step name (`signup`, `verify`, `subscribe`)
- `blob2` = anonymous user ID (hashed or UUID)
- `doubles[0]` = Unix timestamp in seconds (enables windowed funnels)
- Dataset name: `user_funnel`

---

## Writing Funnel Data Points from a Worker

```typescript
// src/funnel.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

type FunnelStep = 'signup' | 'verify' | 'subscribe';

/**
 * Call this at each step of your funnel.
 * userId should be a stable, hashed identifier — never raw PII.
 */
export function recordFunnelStep(
  analytics: AnalyticsEngineDataset,
  step: FunnelStep,
  userId: string,
  meta?: { plan?: string; country?: string }
): void {
  analytics.writeDataPoint({
    blobs: [
      step,                        // blob1 — funnel step
      userId,                      // blob2 — user identifier
      meta?.plan ?? '',            // blob3 — plan tier (optional)
      meta?.country ?? '',         // blob4 — ISO country code (optional)
    ],
    doubles: [
      Date.now() / 1000,           // doubles[0] — Unix timestamp (seconds)
    ],
    indexes: [userId],             // enables per-user cardinality queries
  });
}

// Usage inside your main Worker fetch handler:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const userId = request.headers.get('x-user-id') ?? 'anonymous';

    if (url.pathname === '/signup' && request.method === 'POST') {
      recordFunnelStep(env.ANALYTICS, 'signup', userId);
      // … handle signup logic …
    }

    if (url.pathname === '/verify' && request.method === 'POST') {
      recordFunnelStep(env.ANALYTICS, 'verify', userId);
    }

    if (url.pathname === '/subscribe' && request.method === 'POST') {
      const plan = (await request.json() as { plan: string }).plan;
      recordFunnelStep(env.ANALYTICS, 'subscribe', userId, { plan });
    }

    return new Response('ok');
  },
};
```

---

## Querying Conversion Rates

Query the Analytics Engine SQL API (or use `env.ANALYTICS.query()` in a Worker) to compute step-level conversion rates:

```typescript
// src/funnel-metrics.ts
const AE_SQL_ENDPOINT =
  'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/analytics_engine/sql';

const FUNNEL_CONVERSION_SQL = `
  SELECT
    COUNT(DISTINCT blob2) FILTER (WHERE blob1 = 'signup')    AS signups,
    COUNT(DISTINCT blob2) FILTER (WHERE blob1 = 'verify')    AS verifies,
    COUNT(DISTINCT blob2) FILTER (WHERE blob1 = 'subscribe') AS subscribes,
    ROUND(
      100.0 *
      COUNT(DISTINCT blob2) FILTER (WHERE blob1 = 'verify') /
      NULLIF(COUNT(DISTINCT blob2) FILTER (WHERE blob1 = 'signup'), 0),
      2
    ) AS signup_to_verify_pct,
    ROUND(
      100.0 *
      COUNT(DISTINCT blob2) FILTER (WHERE blob1 = 'subscribe') /
      NULLIF(COUNT(DISTINCT blob2) FILTER (WHERE blob1 = 'signup'), 0),
      2
    ) AS signup_to_subscribe_pct
  FROM user_funnel
  WHERE timestamp >= NOW() - INTERVAL '7' DAY
`;

export async function getFunnelMetrics(apiToken: string, accountId: string) {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: FUNNEL_CONVERSION_SQL }),
    }
  );
  if (!resp.ok) throw new Error(`AE SQL error: ${resp.status}`);
  const json = await resp.json() as { data: Record<string, unknown>[] };
  return json.data[0];
}
```

---

## Windowed Funnel (24-Hour Completion Window)

A user should only count as converted if they completed all steps within 24 hours of signup. Use a self-join on `blob2` comparing `doubles[0]` timestamps:

```sql
-- Windowed funnel: steps must complete within 86400 seconds of signup
WITH base AS (
  SELECT
    blob2                                  AS user_id,
    MIN(doubles[0]) FILTER (WHERE blob1 = 'signup')    AS t_signup,
    MIN(doubles[0]) FILTER (WHERE blob1 = 'verify')    AS t_verify,
    MIN(doubles[0]) FILTER (WHERE blob1 = 'subscribe') AS t_subscribe
  FROM user_funnel
  WHERE timestamp >= NOW() - INTERVAL '30' DAY
  GROUP BY blob2
)
SELECT
  COUNT(*) FILTER (WHERE t_signup IS NOT NULL)                                           AS signups,
  COUNT(*) FILTER (WHERE t_verify IS NOT NULL AND t_verify - t_signup <= 86400)          AS windowed_verifies,
  COUNT(*) FILTER (WHERE t_subscribe IS NOT NULL AND t_subscribe - t_signup <= 86400)    AS windowed_subscribes
FROM base;
```

---

## Metrics Endpoint Worker

Expose funnel metrics as JSON from a scheduled or on-demand Worker:

```typescript
export default {
  async fetch(request: Request, env: Env & { AE_API_TOKEN: string; CF_ACCOUNT_ID: string }) {
    const data = await getFunnelMetrics(env.AE_API_TOKEN, env.CF_ACCOUNT_ID);
    return Response.json(data, {
      headers: { 'Cache-Control': 'public, max-age=300' },
    });
  },
};
```

---

## Anti-patterns

- **Using raw email or PII as `blob2`** — hash user IDs before writing; Analytics Engine data is retained and accessible to anyone with the API token.
- **Counting rows instead of distinct users** — `COUNT(*)` inflates numbers if a user hits the same step twice; always use `COUNT(DISTINCT blob2)`.
- **No timestamp in `doubles[0]`** — without it you cannot compute windowed funnels; add it from day one.
- **Querying without a time filter** — full dataset scans are slow and costly; always bound with `WHERE timestamp >= …`.

## Gotchas

- Analytics Engine data has a propagation delay of roughly 60 seconds; do not expect real-time counts in the same second.
- `FILTER (WHERE …)` is ANSI SQL but not supported by all SQL dialects — AE's SQL API supports it; do not try to run these queries against D1.
- Dataset names are case-sensitive in the SQL API.
- `doubles` arrays are 1-indexed in AE SQL (`doubles[0]` in the write call maps to `double1` in the query column — check your account's AE schema reference for the exact alias).

## Verification

1. Fire a test request to `/signup` with a known `x-user-id` header.
2. Wait ~60 seconds for propagation.
3. Query `SELECT * FROM user_funnel WHERE blob2 = '<your-test-id>' LIMIT 5` via the AE SQL API.
4. Confirm `blob1` and `doubles[0]` are populated correctly.
5. Run the conversion query and verify `signups >= 1`.

## Related

- `workers-latency-percentile-tracking-analytics-engine.md`
- `durable-objects-websocket-connection-monitoring.md`
- Cloudflare Analytics Engine SQL API docs

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
