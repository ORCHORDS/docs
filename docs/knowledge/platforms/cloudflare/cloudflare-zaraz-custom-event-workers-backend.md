# Zaraz Custom Events — Workers Backend with D1 Persistence

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to capture custom `zaraz.track()` events from the browser, store them in a D1 database for durable analytics, and aggregate them server-side — without sending raw user data to a third-party vendor. You also need consent-aware filtering so events are only stored when the user has granted analytics consent.

## Context

- Platform: Cloudflare Zaraz + Workers + D1
- Zaraz action type: "Send Request" pointing at a Worker route
- Consent framework: Zaraz's built-in consent modal (or custom)
- Schema: D1 table for raw events + materialized aggregation view

---

## Section 1 — Zaraz `track()` and the Payload Shape

```javascript
// Browser-side: fire a custom event
zaraz.track('purchase', {
  value: 49.99,
  currency: 'USD',
  product_id: 'prod_abc123',
  // zaraz automatically appends: system.timestamp, system.page.url, etc.
});
```

Zaraz posts the event to your Worker endpoint as JSON. The default payload shape:

```json
{
  "system": {
    "timestamp": 1724500000000,
    "page": { "url": "https://shop.example.com/checkout", "title": "Checkout" },
    "device": { "userAgent": "...", "language": "en-US", "screenWidth": 1440 },
    "consent": { "analyticsStorage": true, "adStorage": false }
  },
  "track": "purchase",
  "properties": {
    "value": 49.99,
    "currency": "USD",
    "product_id": "prod_abc123"
  }
}
```

---

## Section 2 — D1 Schema

```sql
-- migrations/001_events.sql
CREATE TABLE IF NOT EXISTS zaraz_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  event_name  TEXT    NOT NULL,
  page_url    TEXT,
  properties  TEXT    NOT NULL,  -- JSON blob
  consented   INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL   -- Unix ms
);

CREATE INDEX IF NOT EXISTS idx_zaraz_events_name
  ON zaraz_events (event_name);

CREATE INDEX IF NOT EXISTS idx_zaraz_events_created
  ON zaraz_events (created_at);

-- Aggregation helper (run on demand or via scheduled Worker)
CREATE VIEW IF NOT EXISTS zaraz_event_counts AS
SELECT
  event_name,
  COUNT(*)          AS total,
  SUM(consented)    AS consented_total,
  DATE(created_at / 1000, 'unixepoch') AS day
FROM zaraz_events
GROUP BY event_name, day;
```

Apply via wrangler:

```bash
wrangler d1 execute prod-analytics --file=migrations/001_events.sql
```

---

## Section 3 — Worker Endpoint

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  ZARAZ_SECRET: string;  // shared secret set in Zaraz action headers
}

const ALLOWED_EVENTS = new Set([
  'purchase', 'add_to_cart', 'page_view', 'sign_up',
]);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Method guard
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    // 2. Shared-secret auth (set X-Zaraz-Secret in the Zaraz action)
    const secret = <redacted-secret>'x-zaraz-secret');
    if (secret !== env.ZARAZ_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }

    // 3. Parse body
    let payload: ZarazPayload;
    try {
      payload = await request.json() as ZarazPayload;
    } catch {
      return new Response('Bad JSON', { status: 400 });
    }

    // 4. Consent-aware filtering
    const consented = payload.system?.consent?.analyticsStorage === true ? 1 : 0;

    // 5. Event allowlist
    const eventName = payload.track;
    if (!ALLOWED_EVENTS.has(eventName)) {
      // Accept the request but don't persist unknown events
      return new Response(JSON.stringify({ ok: true, stored: false }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // 6. Persist to D1
    try {
      await env.DB.prepare(
        `INSERT INTO zaraz_events (event_name, page_url, properties, consented, created_at)
         VALUES (?, ?, ?, ?, ?)`
      ).bind(
        eventName,
        payload.system?.page?.url ?? null,
        JSON.stringify(payload.properties ?? {}),
        consented,
        payload.system?.timestamp ?? Date.now()
      ).run();
    } catch (err) {
      console.error('[zaraz] D1 insert failed:', err);
      return new Response('Internal Error', { status: 500 });
    }

    return new Response(JSON.stringify({ ok: true, stored: true }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};

interface ZarazPayload {
  track: string;
  properties?: Record<string, unknown>;
  system?: {
    timestamp?: number;
    page?: { url?: string; title?: string };
    consent?: { analyticsStorage?: boolean; adStorage?: boolean };
  };
}
```

---

## Section 4 — Zaraz Action Configuration

In the Cloudflare dashboard under **Zaraz → Tools → Add Tool → Custom HTML / Send Request**:

1. **Trigger**: All page events + custom event `purchase`, `add_to_cart`, etc.
2. **URL**: `https://analytics-worker.example.com/zaraz`
3. **Method**: POST
4. **Headers**:
   - `Content-Type: application/json`
   - `X-Zaraz-Secret: <redacted-secret>
5. **Body**: `{{ system.zarazPayload | json }}`

For consent filtering, wrap the action in a Zaraz consent purpose (e.g., `analyticsStorage`) so Zaraz itself suppresses the network call when consent is denied — the Worker's check is a defense-in-depth fallback.

---

## Section 5 — Analytics Aggregation Query

```typescript
// src/analytics.ts — expose aggregated stats via a GET endpoint
export async function handleAnalytics(env: { DB: D1Database }): Promise<Response> {
  const { results } = await env.DB
    .prepare(
      `SELECT event_name, COUNT(*) as total,
              SUM(consented) as consented_total
       FROM zaraz_events
       WHERE created_at > ?
       GROUP BY event_name
       ORDER BY total DESC`
    )
    .bind(Date.now() - 7 * 24 * 60 * 60 * 1000) // last 7 days
    .all();

  return new Response(JSON.stringify({ window: '7d', events: results }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## Anti-patterns

- Persisting all events regardless of consent — always check `consent.analyticsStorage` before writing PII-adjacent data.
- Trusting the client-sent consent flag without server-side validation — use the Zaraz consent system to suppress the network call entirely at the source.
- Storing raw `properties` without sanitizing user-controlled strings — validate length and type before INSERT.
- Using a single large D1 table without indexes — add indexes on `event_name` and `created_at` for query performance.
- Skipping the shared-secret header — anyone who discovers your Worker URL can flood D1 with junk events.

## Gotchas

- Zaraz fires `track()` calls client-side; if the user navigates away before the network request completes, the event may be lost — consider `navigator.sendBeacon` via a custom Zaraz component.
- D1 free tier has row-write limits; for high-traffic sites, batch inserts or use a KV queue buffer.
- `system.zarazPayload` in the Zaraz body template is the full serialized payload; test with the Zaraz Preview tool to confirm the exact shape.
- Zaraz injects its own system fields; do not duplicate them in `zaraz.track()` properties.
- The Worker route must be on the same Cloudflare zone as the Zaraz configuration, or CORS headers must be added.

## Verification

```bash
# Send a test event manually
curl -X POST https://analytics-worker.example.com/zaraz \
  -H 'Content-Type: application/json' \
  -H 'X-Zaraz-Secret: your-secret-here' \
  -d '{
    "track": "purchase",
    "properties": {"value": 9.99, "currency": "USD"},
    "system": {
      "timestamp": 1724500000000,
      "page": {"url": "https://shop.example.com"},
      "consent": {"analyticsStorage": true}
    }
  }'

# Query stored events
wrangler d1 execute prod-analytics \
  --command "SELECT event_name, COUNT(*) FROM zaraz_events GROUP BY event_name;"

# Check the aggregated stats endpoint
curl https://analytics-worker.example.com/analytics | jq .
```

## Related

- `documentation/docs/policies/cloudflare/workers-d1-alarms-scheduled-mutations.md`
- `documentation/docs/policies/cloudflare/cloudflare-pages-functions-middleware-chain.md`

## Sources

- https://developers.cloudflare.com/zaraz/reference/zaraz-track/
- https://developers.cloudflare.com/zaraz/advanced/use-workers-with-zaraz/
- https://developers.cloudflare.com/zaraz/consent-management/
- https://developers.cloudflare.com/d1/
