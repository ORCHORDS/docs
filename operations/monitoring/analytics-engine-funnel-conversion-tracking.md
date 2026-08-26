# Analytics Engine Funnel Conversion Tracking

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project needs to understand where anonymous users drop off during the post-creation flow: landing page → sign-up prompt → content submission → first reaction received. Without funnel visibility, product decisions are guesses. Traditional session-based funnels require cookies and a persistent user identity, which conflicts with the platform's anonymous-first model. Cloudflare Analytics Engine provides a privacy-safe, edge-native alternative by tracking funnel steps as timestamped data points keyed on a transient session token hashed at ingestion.

## Context

Analytics Engine data points land in a time-series store queryable through the SQL API. Each data point can carry up to 20 blobs (string fields) and 20 doubles (numeric fields). For funnel tracking, each step in the user journey is written as a separate data point with a shared session identifier, allowing SQL window functions to reconstruct ordered step sequences. Because Analytics Engine retains data for 31 days by default and has no PII, no GDPR data-subject-request pipeline is required for these events.

## Section 1 — Instrumentation: Step Beacons from the Worker

Add a `trackFunnelStep` helper to the main example project API Worker that fires on each meaningful user action. The session token is a 64-bit random value generated client-side at landing and sent in every subsequent request header — it is hashed before storage so it cannot be reversed to a persistent identity.

```typescript
// workers/src/funnel.ts
import { Env } from "./types";

export type FunnelStep =
  | "landing_view"
  | "signup_prompt_shown"
  | "signup_started"
  | "signup_completed"
  | "post_created"
  | "first_reaction_received";

const STEP_INDEX: Record<FunnelStep, number> = {
  landing_view: 1,
  signup_prompt_shown: 2,
  signup_started: 3,
  signup_completed: 4,
  post_created: 5,
  first_reaction_received: 6,
};

async function hashSessionToken(raw: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(raw)
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 32); // 128-bit prefix — sufficient for collision resistance at scale
}

export async function trackFunnelStep(
  step: FunnelStep,
  request: Request,
  env: Env,
  extras: Record<string, string> = {}
): Promise<void> {
  const rawToken = request.headers.get("x-example project-session") ?? "";
  if (!rawToken) return; // no token, no tracking

  const sessionHash = await hashSessionToken(rawToken);
  const cf = (request as any).cf ?? {};

  env.ANALYTICS_ENGINE.writeDataPoint({
    blobs: [
      step,                              // blob1: step name
      cf.country ?? "unknown",           // blob2: country
      cf.colo ?? "unknown",              // blob3: edge colo
      extras.referrer ?? "",             // blob4: referrer category
      extras.variant ?? "control",       // blob5: A/B variant
      extras.platform ?? "web",          // blob6: client platform
    ],
    doubles: [
      STEP_INDEX[step],                  // double1: step ordinal for ordering
      Date.now(),                        // double2: client timestamp ms (server-side)
    ],
    indexes: [sessionHash],             // high-cardinality: hashed session
  });
}
```

## Section 2 — Data Collection: Emitting Steps from Route Handlers

Instrument each route that corresponds to a funnel step. Keep the call non-blocking with `ctx.waitUntil` so it never adds latency to the response.

```typescript
// workers/src/routes/signup.ts
import { trackFunnelStep } from "../funnel";

export async function handleSignupPrompt(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  // ... business logic ...
  ctx.waitUntil(
    trackFunnelStep("signup_prompt_shown", request, env, {
      referrer: request.headers.get("x-referrer-category") ?? "",
    })
  );
  return new Response(JSON.stringify({ promptShown: true }), {
    headers: { "content-type": "application/json" },
  });
}

export async function handleSignupComplete(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  // ... create account, set session ...
  ctx.waitUntil(
    trackFunnelStep("signup_completed", request, env, {
      variant: request.headers.get("x-ab-variant") ?? "control",
    })
  );
  return new Response(JSON.stringify({ ok: true }));
}
```

## Section 3 — Funnel Queries via Analytics Engine SQL API

Use a two-step CTE to count sessions that reached each step, then compute conversion rates relative to the top of the funnel.

```sql
-- Step counts for the last 7 days
WITH step_sessions AS (
  SELECT
    blob1                        AS step_name,
    double1                      AS step_ord,
    COUNT(DISTINCT _sample_interval * index1) AS sessions
  FROM analytics_engine_dataset
  WHERE
    timestamp > NOW() - INTERVAL '7' DAY
  GROUP BY 1, 2
),
top AS (
  SELECT sessions AS top_sessions
  FROM step_sessions
  WHERE step_name = 'landing_view'
)
SELECT
  ss.step_name,
  ss.step_ord,
  ss.sessions,
  ROUND(100.0 * ss.sessions / t.top_sessions, 1) AS pct_of_landing
FROM step_sessions ss, top t
ORDER BY ss.step_ord;

-- Drop-off between consecutive steps
WITH ordered AS (
  SELECT
    step_name,
    step_ord,
    COUNT(DISTINCT index1) AS sessions,
    LAG(COUNT(DISTINCT index1)) OVER (ORDER BY step_ord) AS prev_sessions
  FROM analytics_engine_dataset
  WHERE timestamp > NOW() - INTERVAL '7' DAY
  GROUP BY 1, 2
)
SELECT
  step_name,
  sessions,
  ROUND(100.0 * (1 - sessions::float / NULLIF(prev_sessions, 0)), 1) AS drop_pct
FROM ordered
ORDER BY step_ord;
```

## Section 4 — Grafana Dashboard via SQL API Proxy

Expose the SQL API through a lightweight Worker proxy so Grafana Infinity datasource can poll without exposing the Cloudflare API token.

```typescript
// workers/src/funnel-query-proxy.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<{ query: string }>();
    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: body.query }),
      }
    );

    const data = await resp.json();
    return new Response(JSON.stringify(data), {
      headers: {
        "content-type": "application/json",
        "cache-control": "s-maxage=60",
      },
    });
  },
};
```

Grafana panel JSON snippet for step conversion bar chart:

```json
{
  "type": "barchart",
  "title": "example project Signup Funnel (7d)",
  "targets": [
    {
      "refId": "A",
      "url": "https://funnel-proxy.example.com/sql",
      "method": "POST",
      "data": "{\"query\": \"SELECT blob1 AS step, COUNT(DISTINCT index1) AS sessions FROM analytics_engine_dataset WHERE timestamp > NOW() - INTERVAL '7' DAY GROUP BY 1 ORDER BY MIN(double1)\"}"
    }
  ]
}
```

## Anti-patterns

- Storing raw session tokens as the index — even short-lived tokens become linkable if leaked from Analytics Engine exports.
- Writing one data point per page-view event from the browser — use the Worker as the aggregation layer; browser beacons go to the Worker, not directly to Analytics Engine.
- Using the same index for all steps of the same session — you lose the ability to count distinct sessions per step; keep the index as the hashed session token so `COUNT(DISTINCT index1)` works correctly.
- Treating funnel drop-off rates as stable without A/B variant segmentation — conversion varies by platform and experiment; always include `blob5` (variant) in GROUP BY when comparing cohorts.
- Querying more than 31 days — Analytics Engine does not retain data beyond its retention window; for longer-term trends, Logpush to R2 and query with Athena.

## Gotchas

- `COUNT(DISTINCT index1)` in Analytics Engine SQL is an approximation (HyperLogLog); expect ±2 % error at scale.
- The `_sample_interval` system column is always 1 for Analytics Engine writes from Workers (not sampled by the platform); multiply by it for forward-compatibility if you later add sampling.
- `writeDataPoint` is fire-and-forget; failures are silently dropped — add a fallback Logpush pipeline for critical step events.
- Sessions that span midnight are split across date partitions; use `timestamp >` with an absolute offset, not `DATE(timestamp) =`.
- Analytics Engine blobs are case-sensitive in WHERE clauses; normalise step names to snake_case at write time.

## Verification

1. In a staging environment, curl each funnel endpoint in order with a fixed `x-example project-session: test-session-abc123` header.
2. Wait 30 seconds, then query: `SELECT blob1, COUNT(*) FROM ae WHERE index1 LIKE 'e3b0%' GROUP BY 1` (replace with actual hash prefix).
3. Confirm 6 rows appear with step ordinals 1–6 in `double1`.
4. Hit only steps 1 and 2 with a second session token; verify the drop-off query shows 50 % at step 3.
5. Confirm the Grafana proxy endpoint returns valid JSON and caches with `s-maxage=60`.

## Related

- `/documentation/categories/monitoring/cloudflare-analytics-engine.md`
- `/documentation/categories/monitoring/analytics-engine-cardinality-management-multi-dimension.md`
- `/documentation/categories/monitoring/analytics-engine-sql-api-programmatic-querying.md`
- `/documentation/categories/monitoring/rum-beacon-workers-analytics-engine.md`
- `/documentation/categories/monitoring/funnel-analytics-monitoring.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/get-started/
