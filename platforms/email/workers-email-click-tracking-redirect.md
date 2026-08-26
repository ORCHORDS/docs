# Email Click Tracking with Redirect via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You want to measure which links inside your campaign emails are clicked, by whom, and how often, without relying on a third-party ESP. Every link in an outgoing email should be wrapped so clicks are recorded and the user is immediately 302-redirected to the original destination.

---

## Context
Each outbound link is rewritten to `GET /track/click/{trackId}?url={encodedUrl}` before sending. The Worker records the event in a D1 `email_events` table (shared with the open-tracking article) and issues a 302. To avoid inflated counts from email prefetch crawlers, clicks are deduplicated within a 60-second window using a KV key. Campaign-level click rate analytics are computed with a single SQL query against D1.

---

## Section 1 — D1 Schema & Wrangler Config

```sql
-- email_events table (shared with workers-email-open-tracking-pixel.md)
CREATE TABLE IF NOT EXISTS email_events (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  track_id    TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  event_type  TEXT NOT NULL,
  url         TEXT,
  ip          TEXT,
  user_agent  TEXT,
  ts          INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_events_campaign ON email_events(campaign_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_click_url ON email_events(track_id, url);
```

```toml
# wrangler.toml additions
[[kv_namespaces]]
binding = "CLICK_DEDUP"
id      = "<your-kv-namespace-id>"

[vars]
BASE_URL         = "https://track.example.com"
DEDUP_WINDOW_SEC = "60"
```

---

## Section 2 — Implementation

```typescript
// src/click-tracking.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  CLICK_DEDUP: KVNamespace;
  BASE_URL: string;
  DEDUP_WINDOW_SEC: string;
}

const app = new Hono<{ Bindings: Env }>();

function isValidUrl(raw: string): boolean {
  try {
    const u = new URL(raw);
    return u.protocol === 'https:' || u.protocol === 'http:';
  } catch {
    return false;
  }
}

async function isDuplicate(
  kv: KVNamespace,
  trackId: string,
  url: string,
  windowSec: number
): Promise<boolean> {
  const key = `click:${trackId}:${encodeURIComponent(url)}`;
  const existing = await kv.get(key);
  if (existing !== null) return true;
  await kv.put(key, '1', { expirationTtl: windowSec });
  return false;
}

/**
 * GET /track/click/:trackId?url={encoded}
 * trackId format: {campaignId}_{recipientToken}
 */
app.get('/track/click/:trackId', async (c) => {
  const trackId  = c.req.param('trackId');
  const rawUrl   = c.req.query('url') ?? '';
  const ua       = c.req.header('User-Agent') ?? null;
  const ip       = c.req.header('CF-Connecting-IP') ?? null;
  const windowSec = parseInt(c.env.DEDUP_WINDOW_SEC, 10);

  if (!isValidUrl(rawUrl)) {
    return new Response('Invalid or missing url parameter', { status: 400 });
  }

  const destination = decodeURIComponent(rawUrl);
  const parts       = trackId.split('_');
  const campaignId  = parts[0] ?? 'unknown';

  const dedup = await isDuplicate(c.env.CLICK_DEDUP, trackId, destination, windowSec);

  if (!dedup) {
    await c.env.DB
      .prepare(
        `INSERT INTO email_events (track_id, campaign_id, event_type, url, ip, user_agent)
         VALUES (?, ?, 'click', ?, ?, ?)`
      )
      .bind(trackId, campaignId, destination, ip, ua)
      .run();
  }

  return new Response(null, {
    status: 302,
    headers: { Location: destination },
  });
});

/**
 * GET /analytics/clicks?campaign=campaignId
 */
app.get('/analytics/clicks', async (c) => {
  const campaign = c.req.query('campaign');
  if (!campaign) return c.json({ error: 'campaign required' }, 400);

  const rows = await c.env.DB
    .prepare(
      `SELECT
         url,
         COUNT(*)               AS total_clicks,
         COUNT(DISTINCT track_id) AS unique_clicks,
         MIN(ts)                AS first_click_ts,
         MAX(ts)                AS last_click_ts
       FROM email_events
       WHERE campaign_id = ? AND event_type = 'click'
       GROUP BY url
       ORDER BY unique_clicks DESC`
    )
    .bind(campaign)
    .all<{ url: string; total_clicks: number; unique_clicks: number; first_click_ts: number; last_click_ts: number }>();

  return c.json({ campaign, links: rows.results });
});

export default app;

export function wrapLinks(
  html: string,
  baseUrl: string,
  campaignId: string,
  recipientToken: string
): string {
  const trackId = `${campaignId}_${recipientToken}`;
  return html.replace(/]+)"/g, (_match, originalUrl: string) => {
    const wrapped = `${baseUrl}/track/click/${encodeURIComponent(trackId)}?url=${encodeURIComponent(originalUrl)}`;
    return ``;
  });
}
```

---

## Section 3 — Testing

```typescript
// test/click-tracking.test.ts
import { SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';

describe('click tracking', () => {
  const destination = 'https://example.com/products';
  const trackId     = 'summer2026_tok_abc123';
  const trackUrl    = `/track/click/${trackId}?url=${encodeURIComponent(destination)}`;

  it('redirects to destination URL', async () => {
    const res = await SELF.fetch(`http://localhost${trackUrl}`, { redirect: 'manual' });
    expect(res.status).toBe(302);
    expect(res.headers.get('Location')).toBe(destination);
  });

  it('returns 400 for missing url', async () => {
    const res = await SELF.fetch(`http://localhost/track/click/${trackId}`);
    expect(res.status).toBe(400);
  });
});
```

```bash
# Manual verification
curl -I 'https://track.example.com/track/click/summer2026_tok_abc123?url=https%3A%2F%2Forchords.com%2Fproducts'

# Analytics per campaign
curl 'https://track.example.com/analytics/clicks?campaign=summer2026'

# Check KV dedup key
npx wrangler kv key get --binding=CLICK_DEDUP 'click:summer2026_tok_abc123:https%3A%2F%2Forchords.com%2Fproducts'
```

---

## Anti-patterns
- **Open-redirecting without validation** — Accepting any `url` parameter without protocol/format validation allows your domain to be abused as an open redirector.
- **Deduplicating by IP alone** — Corporate proxies share one IP; use `trackId + url` as the dedup key so different recipients clicking the same link are each counted.
- **URL-encoding the trackId in the path and not the query** — Path-encoded slashes may be decoded by some proxies; keep opaque tokens URL-safe (no slashes) or base64url-encode them.
- **Storing raw destination URLs in the path** — Long URLs break CDN path length limits; always put the destination in the `url` query parameter.

---

## Gotchas
- KV `expirationTtl` of 60 seconds means a second click within one minute is silently dropped from the DB — this is intentional but affects absolute click counts.
- The `CF-Connecting-IP` header is set by Cloudflare's edge and is trustworthy inside Workers; do not fall back to `X-Forwarded-For` as it can be spoofed.
- Regex-based link wrapping (`wrapLinks`) will not replace links in `<a>` tags that use single quotes or no quotes; use an HTML parser for production-grade wrapping.
- 302 (Found) is used intentionally so browsers do not cache the redirect; using 301 would cache the redirect and skip tracking on subsequent clicks.

---

## Verification

```bash
# Confirm click recorded in D1
npx wrangler d1 execute email-tracking-db \
  --command "SELECT track_id, url, ip, ts FROM email_events WHERE event_type = 'click' ORDER BY ts DESC LIMIT 10"

# Per-campaign click breakdown
npx wrangler d1 execute email-tracking-db \
  --command "SELECT url, COUNT(*) n FROM email_events WHERE campaign_id='summer2026' AND event_type='click' GROUP BY url"
```

---

## Related
- `workers-email-open-tracking-pixel.md`
- `workers-transactional-email-d1-audit.md`

---

## Sources
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- OWASP Open Redirect — https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
- Cloudflare D1 — https://developers.cloudflare.com/d1/
