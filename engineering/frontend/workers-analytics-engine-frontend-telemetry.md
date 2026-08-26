# Workers Analytics Engine for Frontend Custom Telemetry

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to capture custom frontend events — button clicks, feature flag exposures, error
rates, Core Web Vitals per route — without paying for a third-party analytics SaaS or
standing up a time-series database. Cloudflare Workers Analytics Engine (WAE) is a
purpose-built write-heavy, query-via-SQL service included in the Workers Paid plan.
It accepts up to 25 blobs and 20 doubles per data point, survives high write rates
(millions of writes per day), and exposes query results through a REST SQL API with
sub-second response times for typical aggregation queries over 30-day windows.

---

## Context

Workers Analytics Engine is distinct from:

- **Cloudflare Web Analytics / RUM** — page-level only, no custom dimensions.
- **KV** — not for telemetry; no aggregation, expensive at volume.
- **D1** — relational, but write throughput is limited by SQLite locking.
- **Logpush** — forwards raw logs to external storage; no built-in SQL query layer.

WAE stores data in a columnar format designed for OLAP-style aggregation queries
(`GROUP BY`, `SUM`, `COUNT`, `percentile`). Individual writes are fire-and-forget
from within a Worker — there is no response body, and the write is acknowledged
internally with no round-trip penalty to the client.

---

## Binding Setup (wrangler.toml)

```toml
# wrangler.toml (Worker or Pages Functions)
name = "frontend-api"
compatibility_date = "2025-01-01"

[[analytics_engine_datasets]]
binding = "TELEMETRY"
dataset = "frontend_events"
```

The `dataset` string is a logical namespace inside WAE. All writes from this binding
go to `frontend_events`. You can have multiple bindings pointing to different datasets.

---

## TypeScript Types and Worker Ingestion Endpoint

Define a typed event union for your frontend:

```typescript
// shared/telemetry-events.ts
export type TelemetryEvent =
  | { type: 'click'; element: string; page: string; session: string }
  | { type: 'web_vital'; metric: 'LCP' | 'INP' | 'CLS'; value: number; page: string; session: string }
  | { type: 'error'; message: string; stack?: string; page: string; session: string }
  | { type: 'feature_exposure'; flag: string; variant: string; page: string; session: string };
```

The Worker ingestion endpoint:

```typescript
// src/worker.ts
import { Hono } from 'hono';
import type { TelemetryEvent } from '../shared/telemetry-events';

type Env = {
  TELEMETRY: AnalyticsEngineDataset;
};

const app = new Hono<{ Bindings: Env }>();

app.post('/api/telemetry', async (c) => {
  const events = await c.req.json<TelemetryEvent[]>();

  for (const event of events) {
    c.env.TELEMETRY.writeDataPoint({
      blobs: [
        event.type,          // blob1 = event type
        event.page,          // blob2 = page path
        event.session,       // blob3 = session ID
        // blob4: type-specific string field
        event.type === 'click' ? event.element
          : event.type === 'web_vital' ? event.metric
          : event.type === 'feature_exposure' ? event.flag
          : (event.message ?? ''),
        // blob5: variant / stack / empty
        event.type === 'feature_exposure' ? event.variant
          : event.type === 'error' ? (event.stack ?? '')
          : '',
      ],
      doubles: [
        // double1: numeric value (vitals score, else 1 for count events)
        event.type === 'web_vital' ? event.value : 1,
      ],
      indexes: [event.session],  // enables per-session cardinality queries
    });
  }

  return c.json({ ok: true }, 202);
});

export default app;
```

`writeDataPoint` is non-blocking. The runtime batches writes internally — never
`await` it; it does not return a Promise.

---

## Frontend Batching Client

Sending one request per event is wasteful. Batch events on the client, flush on
`visibilitychange` and every 10 seconds:

```typescript
// src/lib/telemetry.ts
import type { TelemetryEvent } from '../../shared/telemetry-events';

const ENDPOINT = '/api/telemetry';
const FLUSH_INTERVAL_MS = 10_000;

class TelemetryClient {
  private queue: TelemetryEvent[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    if (typeof window === 'undefined') return;
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') this.flush();
    });
    this.timer = setInterval(() => this.flush(), FLUSH_INTERVAL_MS);
  }

  push(event: TelemetryEvent): void {
    this.queue.push(event);
    if (this.queue.length >= 50) this.flush(); // safety cap
  }

  private flush(): void {
    if (this.queue.length === 0) return;
    const payload = this.queue.splice(0);
    // Use sendBeacon for guaranteed delivery on page unload
    const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    if (navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, blob);
    } else {
      fetch(ENDPOINT, { method: 'POST', body: blob, keepalive: true });
    }
  }

  destroy(): void {
    if (this.timer) clearInterval(this.timer);
  }
}

export const telemetry = new TelemetryClient();
```

---

## Web Vitals Integration

Pipe `web-vitals` output directly into the telemetry client:

```typescript
// src/lib/web-vitals.ts
import { onLCP, onINP, onCLS } from 'web-vitals';
import { telemetry } from './telemetry';

const page = window.location.pathname;
const session = crypto.randomUUID();

onLCP(({ value }) => telemetry.push({ type: 'web_vital', metric: 'LCP', value, page, session }));
onINP(({ value }) => telemetry.push({ type: 'web_vital', metric: 'INP', value, page, session }));
onCLS(({ value }) => telemetry.push({ type: 'web_vital', metric: 'CLS', value, page, session }));
```

---

## Querying via the SQL API

WAE exposes a REST endpoint at:

```
GET https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql
```

Example: p75 INP by page over the last 7 days:

```sql
SELECT
  blob2                                         AS page,
  quantilesMerge(0.75)(doubles[1])              AS inp_p75,
  count()                                       AS samples
FROM frontend_events
WHERE
  blob1    = 'web_vital'
  AND blob4 = 'INP'
  AND timestamp > NOW() - INTERVAL '7' DAY
GROUP BY page
ORDER BY inp_p75 DESC
LIMIT 20
```

Call it from a Pages Function to power an internal dashboard:

```typescript
// functions/api/vitals.ts
export const onRequestGet: PagesFunction<Env> = async (ctx) => {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ctx.env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${ctx.env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: SQL_QUERY }),
    }
  );
  const data = await res.json();
  return Response.json(data);
};
```

---

## Anti-patterns

- **Using KV for event counts**: KV `get`/`put` costs $0.50/million reads and cannot
  aggregate. WAE writes are included in the Paid plan; use the right tool.
- **Awaiting `writeDataPoint()`**: It returns `undefined`, not a Promise. Awaiting
  it adds no value and may confuse TypeScript.
- **Sending one request per event from the browser**: This saturates the browser's
  HTTP connection pool and inflates your Worker request count. Always batch.
- **Storing PII in blobs**: WAE data is retained for 30–90 days and is not encrypted
  at the row level. Hash or omit user-identifying fields.

---

## Gotchas

- WAE datasets have a 30-day retention window by default (90 days on Enterprise).
  Do not use WAE as a permanent audit log.
- `indexes` are used for cardinality estimation (e.g., unique sessions), not as
  lookup keys. You cannot `WHERE index = ?` — use a blob field for that.
- The SQL API returns results in a non-standard JSON envelope; destructure
  `response.data` to get rows.
- WAE is not available on the Workers Free plan. Workers Paid ($5/month) is required.
- `writeDataPoint` is silently dropped if called outside a Workers execution context
  (e.g., in a Durable Object alarm that has already exceeded its CPU limit).

---

## Verification

1. Deploy the Worker, then from the browser console call:
   `fetch('/api/telemetry', { method: 'POST', body: JSON.stringify([{ type: 'click', element: 'test-btn', page: '/home', session: 'abc123' }]) })`
2. Wait ~30 seconds, then query WAE via the SQL API or `wrangler` CLI:
   `wrangler analytics-engine query --dataset frontend_events "SELECT count() FROM frontend_events WHERE blob1 = 'click'"`
3. Confirm the count increments on each flush.

---

## Related

- `beacon-api-analytics-cloudflare-workers.md` — Beacon API for unload delivery
- `web-vitals-cloudflare-rum-integration.md` — Cloudflare RUM (no-code alternative)
- `cloudflare-zaraz-third-party-script-loading.md` — Zaraz for third-party tags
- `hono-cloudflare-workers-frontend-api.md` — Hono routing on Workers

---

## Sources

- Workers Analytics Engine overview: https://developers.cloudflare.com/analytics/analytics-engine/
- WAE SQL API reference: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- WAE limits: https://developers.cloudflare.com/analytics/analytics-engine/limits/
- web-vitals library: https://github.com/GoogleChrome/web-vitals
