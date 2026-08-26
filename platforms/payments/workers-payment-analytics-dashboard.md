# Payment Analytics Data API in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need real-time payment analytics — revenue by period, conversion funnel, decline rates, AOV, currency breakdown — without exporting data to a third-party BI tool or building a dedicated analytics database. Cloudflare Analytics Engine provides a SQL-queryable time-series store that accepts writes from Workers and returns results sub-second.

---

## Context

Every payment event (initiated, authorized, captured, declined, refunded) is written to Analytics Engine as a data point with dimensions and a blobs field. A dashboard API Worker queries the Engine HTTP endpoint for aggregated metrics and returns a JSON payload consumed by your frontend dashboard.

Analytics Engine is eventually consistent (writes visible within ~30 s) and is not suitable as a financial ledger. Use D1 for authoritative records; use Analytics Engine for analytics-only queries.

---

## Solution

```typescript
// workers-payment-analytics/src/index.ts

import { Env } from './types';
import { writePaymentEvent, PaymentEvent } from './events';
import { queryDashboard } from './queries';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /events — ingest a payment event
    if (request.method === 'POST' && url.pathname === '/events') {
      const body = await request.json<PaymentEvent>();
      await writePaymentEvent(env.ANALYTICS, body);
      return new Response('Accepted', { status: 202 });
    }

    // GET /dashboard — return aggregated metrics
    if (request.method === 'GET' && url.pathname === '/dashboard') {
      const period = url.searchParams.get('period') ?? '7d';
      const data = await queryDashboard(env, period);
      return Response.json(data, {
        headers: { 'Cache-Control': 'public, max-age=60' },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

```typescript
// workers-payment-analytics/src/events.ts

export type PaymentStatus = 'initiated' | 'authorized' | 'captured' | 'declined' | 'refunded';
export type PaymentMethod = 'card' | 'bank_transfer' | 'wallet' | 'bnpl' | 'crypto';

export interface PaymentEvent {
  eventId: string;
  status: PaymentStatus;
  amountCents: number;
  currency: string;       // ISO 4217
  method: PaymentMethod;
  country: string;        // ISO 3166-1 alpha-2
  declineCode?: string;   // e.g. 'insufficient_funds'
  customerId?: string;
  orderId?: string;
}

export function writePaymentEvent(
  dataset: AnalyticsEngineDataset,
  event: PaymentEvent,
): void {
  // Analytics Engine writeDataPoint is fire-and-forget — do not await
  dataset.writeDataPoint({
    blobs:   [event.status, event.currency, event.method, event.country, event.declineCode ?? '', event.orderId ?? ''],
    doubles: [event.amountCents],
    indexes: [event.eventId],
  });
}
```

```typescript
// workers-payment-analytics/src/queries.ts

import { Env } from './types';

const PERIOD_MAP: Record<string, string> = {
  '1d':  'toStartOfHour(timestamp)',
  '7d':  'toStartOfDay(timestamp)',
  '30d': 'toStartOfDay(timestamp)',
  '90d': 'toStartOfWeek(timestamp)',
};

const PERIOD_INTERVAL: Record<string, string> = {
  '1d':  "now() - INTERVAL '1' DAY",
  '7d':  "now() - INTERVAL '7' DAY",
  '30d': "now() - INTERVAL '30' DAY",
  '90d': "now() - INTERVAL '90' DAY",
};

export interface DashboardPayload {
  revenueByPeriod: RevenueRow[];
  conversionFunnel: FunnelRow[];
  declineByReason: DeclineRow[];
  averageOrderValue: number;
  currencyBreakdown: CurrencyRow[];
  totalRevenueCents: number;
}

export interface RevenueRow  { bucket: string; capturedCents: number; }
export interface FunnelRow   { status: string; count: number; rate: number; }
export interface DeclineRow  { declineCode: string; count: number; pct: number; }
export interface CurrencyRow { currency: string; capturedCents: number; pct: number; }

export async function queryDashboard(env: Env, period: string): Promise<DashboardPayload> {
  const trunc  = PERIOD_MAP[period]  ?? PERIOD_MAP['7d'];
  const since  = PERIOD_INTERVAL[period] ?? PERIOD_INTERVAL['7d'];
  const dataset = env.CF_ACCOUNT_ID
    ? `$\{env.CF_ACCOUNT_ID}.$\{env.ANALYTICS_DATASET}`
    : env.ANALYTICS_DATASET;

  const [revenue, funnel, declines, aovRes, currencies] = await Promise.all([
    aeQuery<{ bucket: string; captured_cents: number }>(env, `
      SELECT ${trunc} AS bucket,
             SUM(_sample_interval * double1) AS captured_cents
        FROM ${dataset}
       WHERE timestamp > ${since}
         AND blob1 = 'captured'
       GROUP BY bucket
       ORDER BY bucket ASC
    `),
    aeQuery<{ status: string; cnt: number }>(env, `
      SELECT blob1 AS status, COUNT() AS cnt
        FROM ${dataset}
       WHERE timestamp > ${since}
       GROUP BY blob1
    `),
    aeQuery<{ decline_code: string; cnt: number }>(env, `
      SELECT blob5 AS decline_code, COUNT() AS cnt
        FROM ${dataset}
       WHERE timestamp > ${since}
         AND blob1 = 'declined'
         AND blob5 != ''
       GROUP BY decline_code
       ORDER BY cnt DESC
       LIMIT 10
    `),
    aeQuery<{ aov: number }>(env, `
      SELECT AVG(_sample_interval * double1) AS aov
        FROM ${dataset}
       WHERE timestamp > ${since}
         AND blob1 = 'captured'
    `),
    aeQuery<{ currency: string; captured_cents: number }>(env, `
      SELECT blob2 AS currency,
             SUM(_sample_interval * double1) AS captured_cents
        FROM ${dataset}
       WHERE timestamp > ${since}
         AND blob1 = 'captured'
       GROUP BY currency
       ORDER BY captured_cents DESC
    `),
  ]);

  // Conversion funnel rates (relative to 'initiated')
  const initiated = funnel.find((r) => r.status === 'initiated')?.cnt ?? 1;
  const funnelRows: FunnelRow[] = ['initiated', 'authorized', 'captured', 'declined', 'refunded']
    .map((status) => {
      const count = funnel.find((r) => r.status === status)?.cnt ?? 0;
      return { status, count, rate: Math.round((count / initiated) * 10_000) / 100 };
    });

  // Decline breakdown %
  const totalDeclines = declines.reduce((s, r) => s + r.cnt, 0) || 1;
  const declineRows: DeclineRow[] = declines.map((r) => ({
    declineCode: r.decline_code,
    count: r.cnt,
    pct: Math.round((r.cnt / totalDeclines) * 10_000) / 100,
  }));

  // Currency breakdown %
  const totalCaptured = currencies.reduce((s, r) => s + r.captured_cents, 0) || 1;
  const currencyRows: CurrencyRow[] = currencies.map((r) => ({
    currency: r.currency,
    capturedCents: r.captured_cents,
    pct: Math.round((r.captured_cents / totalCaptured) * 10_000) / 100,
  }));

  return {
    revenueByPeriod: revenue.map((r) => ({ bucket: r.bucket, capturedCents: r.captured_cents })),
    conversionFunnel: funnelRows,
    declineByReason: declineRows,
    averageOrderValue: aovRes[0]?.aov ?? 0,
    currencyBreakdown: currencyRows,
    totalRevenueCents: totalCaptured,
  };
}

async function aeQuery<T>(env: Env, sql: string): Promise<T[]> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'text/plain',
      },
      body: sql.trim(),
    },
  );
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Analytics Engine query failed (${resp.status}): ${err}`);
  }
  const json = await resp.json<{ data: T[] }>();
  return json.data;
}
```

```typescript
// workers-payment-analytics/src/types.ts

export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  ANALYTICS_DATASET: string;  // e.g. 'payment_events'
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;       // scoped to Analytics Engine read
}
```

---

## Implementation Details

**Analytics Engine data point layout**:

| Index | Field   | Value                                         |
|-------|---------|-----------------------------------------------|
| blob1 | status  | initiated / authorized / captured / declined / refunded |
| blob2 | currency| USD / EUR / GBP …                             |
| blob3 | method  | card / wallet / bank_transfer …               |
| blob4 | country | US / DE / GB …                               |
| blob5 | decline | insufficient_funds / do_not_honor … (empty otherwise) |
| blob6 | orderId | order reference                               |
| double1 | amountCents | integer amount in minor units          |

**wrangler.toml**:
```toml
[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "payment_events"

[vars]
ANALYTICS_DATASET = "payment_events"
CF_ACCOUNT_ID     = "<CF_ACCOUNT_ID>"

[secrets]
CF_API_TOKEN = "<AE_READ_TOKEN>"
```

**Call `writeDataPoint` synchronously** (not awaited) — the binding returns void and buffers writes internally. Awaiting it is a no-op and may confuse TypeScript strict mode.

---

## Anti-patterns

- **Do not use Analytics Engine as your billing ledger** — it is an analytics tool with eventual consistency and no transactional guarantees. Always keep D1 as the authoritative financial record.
- **Do not query Analytics Engine from the client browser directly** — your CF_API_TOKEN would be exposed. Always proxy through a Worker.
- **Do not aggregate across all time without a WHERE timestamp** — unbounded scans are slow and expensive; always scope queries to a meaningful window.
- **Do not mix currencies in a single SUM without grouping** — EUR cents and USD cents are not comparable; group by `blob2` (currency) before summing.

---

## Gotchas

- Analytics Engine SQL uses ClickHouse-flavoured SQL, not SQLite (D1). `toStartOfDay`, `toStartOfHour`, `toStartOfWeek` are ClickHouse functions — do not use SQLite date functions here.
- `_sample_interval` must multiply `double` values when sampling is active; always include it in SUM aggregations to get accurate totals.
- `writeDataPoint` silently drops data points exceeding blob/double limits (20 blobs, 20 doubles, total row ≤ 5 120 bytes). Validate payload sizes in high-throughput paths.
- Analytics Engine data is available within ~30 seconds of write; do not expect sub-second read-your-writes consistency.

---

## Verification

```bash
# Write a test event
curl -X POST https://analytics-worker.example.com/events \
  -H 'Content-Type: application/json' \
  -d '{"eventId":"evt_1","status":"captured","amountCents":4999,"currency":"USD","method":"card","country":"US"}'

# Wait ~60 seconds for AE ingestion, then query dashboard
curl 'https://analytics-worker.example.com/dashboard?period=1d'
```

---

## Related

- `documentation/categories/payments/workers-payment-fraud-detection.md`
- `documentation/categories/payments/workers-split-payment-marketplace.md`
- Cloudflare Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare Analytics Engine bindings: https://developers.cloudflare.com/analytics/analytics-engine/get-started/

---

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://clickhouse.com/docs/en/sql-reference/functions/date-time-functions
- https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
