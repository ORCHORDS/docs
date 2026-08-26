# Collecting Core Web Vitals Beacons in Workers with Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You want to capture real-user Core Web Vitals (LCP, CLS, INP) from your frontend and store them server-side for aggregate SQL queries without paying for a third-party RUM service. A Cloudflare Worker receives `POST /vitals` beacons from the `web-vitals` browser library and writes each data point to Analytics Engine, which you can then query for P75 breakdowns per page.

---

## Context
The `web-vitals` JavaScript library (Google) emits metric objects containing `name`, `value`, `rating` (good/needs-improvement/poor), and `navigationType`. A tiny `navigator.sendBeacon` call ships these to your Worker endpoint without blocking page unload. The Worker validates the payload, handles CORS preflight for cross-origin requests, and calls `env.AE.writeDataPoint()` to persist the measurement. Analytics Engine stores data in a columnar format queryable via a REST SQL API, enabling P75 aggregations per metric per page path.

---

## Section 1 — Wrangler Config & Client Setup

```toml
# wrangler.toml
name = "orchords-vitals"
compatibility_date = "2025-09-01"
main = "src/worker.ts"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "web_vitals"

[vars]
ALLOWED_ORIGINS = "https://example.com,https://www.example.com"
```

```bash
# Client-side dependency
npm install web-vitals
```

```typescript
// client/vitals.ts  (bundled and served by your frontend)
import { onLCP, onCLS, onINP, type Metric } from 'web-vitals';

const VITALS_ENDPOINT = 'https://vitals.example.com/vitals';

function sendVital(metric: Metric): void {
  const payload = JSON.stringify({
    name: metric.name,           // 'LCP' | 'CLS' | 'INP' | 'FCP' | 'TTFB'
    value: metric.value,         // raw metric value
    rating: metric.rating,       // 'good' | 'needs-improvement' | 'poor'
    url: location.pathname,      // page path (no PII in full URL)
    nav: metric.navigationType,  // 'navigate' | 'reload' | 'back-forward'
  });

  // sendBeacon survives page unload; fallback to fetch for older browsers
  const sent = navigator.sendBeacon
    ? navigator.sendBeacon(VITALS_ENDPOINT, new Blob([payload], { type: 'application/json' }))
    : false;

  if (!sent) {
    fetch(VITALS_ENDPOINT, {
      method: 'POST',
      body: payload,
      headers: { 'Content-Type': 'application/json' },
      keepalive: true,
    }).catch(() => undefined);
  }
}

// Register all Core Web Vitals
onLCP(sendVital, { reportAllChanges: false });
onCLS(sendVital, { reportAllChanges: false });
onINP(sendVital, { reportAllChanges: false });
```

---

## Section 2 — Worker Implementation

```typescript
// src/worker.ts
import { z } from 'zod';

const VitalSchema = z.object({
  name: z.enum(['LCP', 'CLS', 'INP', 'FCP', 'TTFB']),
  value: z.number().nonnegative(),
  rating: z.enum(['good', 'needs-improvement', 'poor']),
  url: z.string().max(2000),
  nav: z.enum(['navigate', 'reload', 'back-forward', 'prerender']).optional(),
});

type Vital = z.infer<typeof VitalSchema>;

interface Env {
  AE: AnalyticsEngineDataset;
  ALLOWED_ORIGINS: string;
}

const CORS_HEADERS_BASE = {
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Max-Age': '86400',
};

function getAllowedOrigins(env: Env): Set<string> {
  return new Set(
    env.ALLOWED_ORIGINS.split(',').map((o) => o.trim()).filter(Boolean)
  );
}

function corsHeaders(origin: string | null, allowedOrigins: Set<string>): HeadersInit {
  if (!origin || !allowedOrigins.has(origin)) {
    return CORS_HEADERS_BASE;
  }
  return {
    ...CORS_HEADERS_BASE,
    'Access-Control-Allow-Origin': origin,
    'Vary': 'Origin',
  };
}

function writeVital(env: Env, vital: Vital, ip: string): void {
  // Analytics Engine layout:
  //   blob1 = metric name
  //   blob2 = rating
  //   blob3 = url path
  //   blob4 = nav type
  //   double1 = metric value (ms or score)
  //   index1 = metric name (for fast filtering)
  try {
    env.AE.writeDataPoint({
      blobs: [
        vital.name,
        vital.rating,
        vital.url,
        vital.nav ?? 'navigate',
      ],
      doubles: [vital.value],
      indexes: [vital.name],
    });
  } catch (e) {
    console.error('Analytics Engine write failed', e);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin');
    const allowedOrigins = getAllowedOrigins(env);

    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(origin, allowedOrigins),
      });
    }

    if (url.pathname !== '/vitals' || request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'Not Found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Parse and validate body
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return new Response(JSON.stringify({ error: 'Invalid JSON' }), {
        status: 400,
        headers: {
          'Content-Type': 'application/json',
          ...corsHeaders(origin, allowedOrigins),
        },
      });
    }

    const parsed = VitalSchema.safeParse(body);
    if (!parsed.success) {
      return new Response(
        JSON.stringify({ error: 'Validation failed', issues: parsed.error.issues }),
        {
          status: 400,
          headers: {
            'Content-Type': 'application/json',
            ...corsHeaders(origin, allowedOrigins),
          },
        }
      );
    }

    // Fire-and-forget: do not await so we can return 204 immediately
    const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
    writeVital(env, parsed.data, ip);

    return new Response(null, {
      status: 204,
      headers: corsHeaders(origin, allowedOrigins),
    });
  },
};
```

---

## Section 3 — P75 SQL Queries & Verification

```typescript
// scripts/query-vitals.ts — run with ts-node or wrangler dev --compatibility-flags
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

async function queryP75(
  metric: 'LCP' | 'CLS' | 'INP',
  days = 7
): Promise<void> {
  const sql = `
    SELECT
      blob3 AS page_path,
      quantileWeighted(0.75)(double1, 1) AS p75_${metric.toLowerCase()},
      countIf(blob2 = 'good') AS good_count,
      countIf(blob2 = 'needs-improvement') AS ni_count,
      countIf(blob2 = 'poor') AS poor_count,
      count() AS total
    FROM web_vitals
    WHERE
      blob1 = '${metric}'
      AND timestamp > NOW() - INTERVAL '${days}' DAY
    GROUP BY page_path
    HAVING total >= 10
    ORDER BY p75_${metric.toLowerCase()} DESC
    LIMIT 50
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        'Content-Type': 'text/plain',
      },
      body: sql,
    }
  );

  const data = await res.json();
  console.table((data as { data: unknown[] }).data);
}

// Query P75 for all three Core Web Vitals
await Promise.all([
  queryP75('LCP'),
  queryP75('CLS'),
  queryP75('INP'),
]);
```

```bash
# Local dev
npx wrangler dev --port=8788

# Send a test beacon
curl -X POST http://localhost:8788/vitals \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://example.com' \
  -d '{"name":"LCP","value":1850,"rating":"good","url":"/tracks","nav":"navigate"}'

# Confirm CORS preflight
curl -X OPTIONS http://localhost:8788/vitals \
  -H 'Origin: https://example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -I

# Reject unknown origin
curl -X POST http://localhost:8788/vitals \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://evil.com' \
  -d '{"name":"LCP","value":500,"rating":"good","url":"/"}' -I

# Deploy
npx wrangler deploy
```

---

## Anti-patterns
- **Sending the full `window.location.href` as the URL** — Full URLs may contain query strings with PII (email, tokens); send only `location.pathname`.
- **Awaiting `writeDataPoint` in the request handler** — Analytics Engine writes are non-blocking by design; awaiting them adds unnecessary latency to every beacon response.
- **Returning 200 with a body for beacon responses** — `sendBeacon` ignores response bodies; return 204 to save bandwidth and signal success clearly.
- **Skipping CORS preflight handling** — Cross-origin `sendBeacon` with `Content-Type: application/json` triggers a preflight; without handling `OPTIONS`, all beacons are dropped silently.
- **Storing raw IP addresses in Analytics Engine** — IP addresses are PII under GDPR; use them only for deduplication if needed, and never write them to persistent storage.

---

## Gotchas
- Analytics Engine `writeDataPoint` requires at least one of `blobs`, `doubles`, or `indexes` to be non-empty; an empty call throws.
- The `quantileWeighted` function is Analytics Engine-specific SQL and is not standard SQL; it does not exist in other databases.
- `sendBeacon` only accepts `Blob`, `BufferSource`, `FormData`, `URLSearchParams`, or `string` as the body — passing a plain object silently sends `[object Object]`; always `JSON.stringify` first.
- Analytics Engine data has a propagation delay of up to 5 minutes before it appears in SQL queries; do not test immediately after writing.
- The `web-vitals` library fires CLS and INP on page hide/unload, which means beacons may arrive significantly after the initial page load; your Worker must always be available, not just at page-load time.

---

## Verification

```bash
# Confirm 204 on valid beacon
curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8788/vitals \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://example.com' \
  -d '{"name":"INP","value":120,"rating":"good","url":"/tracks"}'
# Expected: 204

# Confirm 400 on invalid metric name
curl -s -X POST http://localhost:8788/vitals \
  -H 'Content-Type: application/json' \
  -d '{"name":"TTI","value":100,"rating":"good","url":"/"}' | jq '.error'
# Expected: "Validation failed"

# Query Analytics Engine after 5-minute propagation
export CF_ACCOUNT_ID=your-account-id
export CF_API_TOKEN=your-api-token
npx ts-node scripts/query-vitals.ts
```

---

## Related
- `workers-html-rewriter-ab-testing.md`
- `workers-astro-cloudflare-d1-integration.md`

---

## Sources
- web-vitals library — https://github.com/GoogleChrome/web-vitals
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Core Web Vitals thresholds — https://web.dev/articles/vitals
- Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
