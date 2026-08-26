# Email Campaign Revenue Attribution — Workers + Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Marketing reports show open rates and click rates but not revenue. You need
to know which campaigns and which subject-line variants drove actual purchases
— not proxy metrics — so that budget follows the emails that convert, not the
ones that get clicked and abandoned.

---

## Context

Analytics Engine (AE) is Cloudflare's time-series columnar store, writable
from Workers at up to 25 data points per event at microsecond resolution.
A two-Worker pipeline emits `email_click` events on link rewrites and
`purchase_completed` events on checkout confirmation. A third Worker joins them
by a session token written to a cookie at click time. The join is done at query
time with GraphQL or the AE REST API, without a database.

---

## Attribution Token Flow

```
Newsletter send
  └─ Link rewritten to: /r?c={campaignId}&v={variantId}&tok={attributionToken}
        ↓
  Redirect Worker
    • Writes AE event: email_click { campaignId, variantId, tok }
    • Sets cookie:  email_attr={tok}; Max-Age=604800 (7 days)
        ↓
  Checkout confirmation page hits
  /api/purchase Worker
    • Reads cookie email_attr
    • Writes AE event: purchase_completed { tok, orderId, revenue }
```

No join table needed — both events share `tok` as a blobs[0] dimension.

---

## Redirect Worker — Emit Click Event

```typescript
// src/workers/email-redirect.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const campaignId = url.searchParams.get('c') ?? 'unknown';
    const variantId  = url.searchParams.get('v') ?? 'control';
    const tok        = url.searchParams.get('tok') ?? crypto.randomUUID();
    const dest       = url.searchParams.get('dest') ?? 'https://example.com';

    env.ANALYTICS.writeDataPoint({
      blobs:   [tok, campaignId, variantId, new URL(dest).hostname],
      doubles: [1],
      indexes: [campaignId],
    });

    const headers = new Headers({
      Location: dest,
      'Set-Cookie': `email_attr=${tok}; Max-Age=604800; Path=/; HttpOnly; Secure; SameSite=Lax`,
    });

    return new Response(null, { status: 302, headers });
  },
};
```

---

## Purchase Worker — Emit Revenue Event

```typescript
// src/workers/purchase-complete.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

interface PurchasePayload {
  orderId: string;
  revenue: number;   // in minor currency unit (cents)
  currency: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const body = await request.json<PurchasePayload>();
    const cookie = request.headers.get('Cookie') ?? '';
    const tok = cookie.match(/email_attr=([^;]+)/)?.[1] ?? 'organic';

    env.ANALYTICS.writeDataPoint({
      blobs:   [tok, body.orderId, body.currency, 'purchase'],
      doubles: [body.revenue / 100, 1],  // doubles[0]=revenue_usd, doubles[1]=order_count
      indexes: [tok],
    });

    return new Response(JSON.stringify({ ok: true }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Querying Attribution — AE SQL API

```typescript
// src/attribution-report.ts
export async function fetchCampaignRevenue(
  accountId: string,
  apiToken: string,
  datasetId: string,
  since: string,   // ISO 8601 e.g. "2026-08-01T00:00:00Z"
): Promise<CampaignRevenueRow[]> {
  // Step 1 — clicks per campaign
  const clickQuery = `
    SELECT blob2 AS campaign_id, blob3 AS variant_id,
           SUM(_sample_interval) AS clicks
    FROM   ${datasetId}
    WHERE  blob4 != 'purchase'
      AND  timestamp > toDateTime('${since}')
    GROUP  BY campaign_id, variant_id
    ORDER  BY clicks DESC
  `;

  // Step 2 — revenue joined by token
  // AE does not support cross-event JOINs in SQL; correlate client-side.
  const revenueQuery = `
    SELECT blob1 AS tok,
           SUM(double1) AS revenue,
           SUM(double2) AS orders
    FROM   ${datasetId}
    WHERE  blob4 = 'purchase'
      AND  timestamp > toDateTime('${since}')
    GROUP  BY tok
  `;

  const [clicksRes, revenueRes] = await Promise.all([
    aeQuery(accountId, apiToken, clickQuery),
    aeQuery(accountId, apiToken, revenueQuery),
  ]);

  return mergeClicksAndRevenue(clicksRes, revenueRes);
}

async function aeQuery(accountId: string, token: string, sql: string): Promise<unknown[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  if (!res.ok) throw new Error(`AE query failed: ${await res.text()}`);
  const data = await res.json<{ data: unknown[] }>();
  return data.data;
}
```

---

## Merging Results Client-Side

```typescript
// src/attribution-report.ts (continued)
interface AEClickRow { campaign_id: string; variant_id: string; clicks: number }
interface AERevenueRow { tok: string; revenue: number; orders: number }
export interface CampaignRevenueRow {
  campaignId: string; variantId: string; clicks: number;
  revenue: number; orders: number; revenuePerClick: number;
}

function mergeClicksAndRevenue(
  clicks: AEClickRow[],
  revenues: AERevenueRow[]
): CampaignRevenueRow[] {
  // This is a simplified merge — in production correlate tok → campaignId
  // by emitting campaignId on the purchase event too (blob2).
  return clicks.map((c) => {
    const matchedRevenue = revenues
      .filter((r) => r.tok.startsWith(c.campaign_id))   // token prefix convention
      .reduce((sum, r) => ({ revenue: sum.revenue + r.revenue, orders: sum.orders + r.orders }),
              { revenue: 0, orders: 0 });
    return {
      campaignId: c.campaign_id,
      variantId: c.variant_id,
      clicks: c.clicks,
      revenue: matchedRevenue.revenue,
      orders: matchedRevenue.orders,
      revenuePerClick: c.clicks > 0 ? matchedRevenue.revenue / c.clicks : 0,
    };
  });
}
```

---

## Anti-patterns

- **Using only click events as a revenue proxy** — click-to-purchase rate
  varies wildly by campaign type; measure actual revenue, not clicks.
- **Cookie-based attribution with SameSite=Strict** — the redirect from the
  email client to your site is a cross-site top-level navigation; `Strict`
  drops the cookie before it is set. Use `Lax`.
- **Long attribution windows (90 days)** — a purchase 90 days after an email
  click has almost no causal connection. Cap attribution at 7–14 days.

---

## Gotchas

- AE does not support `JOIN` across different event types in a single SQL
  query. The two-query + client-side merge pattern above is the correct
  approach until multi-dataset JOINs land.
- `writeDataPoint` is fire-and-forget; it does not throw on failure. Log
  separately if you need write confirmation.
- AE samples high-volume datasets. For purchase events (low volume, high
  value) this is unlikely to matter, but verify `_sample_interval` in results
  and sum with it as a weight if sampling is active.

---

## Verification

```bash
# Simulate a click
curl -i "https://workers.example.com/r?c=camp-001&v=subject-a&tok=tok-xyz&dest=https://shop.example.com"
# Expect: 302 + Set-Cookie: email_attr=tok-xyz

# Simulate a purchase
curl -X POST https://workers.example.com/api/purchase \
  -H "Cookie: email_attr=tok-xyz" \
  -H "Content-Type: application/json" \
  -d '{"orderId":"ord-001","revenue":4999,"currency":"USD"}'

# Query AE for revenue (after ~30 s propagation delay)
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -d '{"query":"SELECT blob1, SUM(double1) AS rev FROM email_events WHERE blob4='"'"'purchase'"'"' GROUP BY blob1"}'
```

---

## Related

- `email-a-b-subject-testing-workers-analytics-engine.md`
- `email-click-tracking-privacy-preserving-workers.md`
- `email-open-click-analytics-engine.md`

---

## Sources

- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- AE SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- AE Workers binding — https://developers.cloudflare.com/analytics/analytics-engine/get-started/
