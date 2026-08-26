# Email Open and Click Tracking with Cloudflare Analytics Engine

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

## Symptom

You are tracking email opens and clicks by redirecting through a Cloudflare Worker, but
writing each event to D1 causes row-lock contention at scale and makes time-series
queries slow. A campaign that sends one million emails can generate millions of tracking
events within the first hour. You need a write-optimised, queryable store that handles
this throughput without manual aggregation cron jobs.

## Context

Cloudflare Analytics Engine is a time-series append store built into the Workers platform.
It accepts event data points via `env.DATASET.writeDataPoint()` and exposes them for
querying through a SQL API (`/v1/accounts/{id}/analytics_engine/sql`). Unlike D1 it is
optimised for extremely high-throughput append-only writes (millions per day on paid plans)
and retains raw data for up to 90 days. Email open and click tracking maps naturally:
each event is one write with the message ID, campaign slug, recipient hash, and event type
as indexed dimensions.

Privacy note: email addresses are PII under GDPR and CCPA. Store only SHA-256 hashes
of the lowercased address. Never write the raw address to Analytics Engine, which is
queryable by anyone with your API token and is not row-level deletable.

Key constraints:
- `writeDataPoint()` is fire-and-forget; it returns void and errors are not surfaced.
- Up to 20 blob fields (`blob1`–`blob20`) and 20 double fields (`double1`–`double20`).
- The SQL API is queried from your backend — not from inside a Worker — using a
  Cloudflare API token scoped to `Analytics Engine: Read`.
- Analytics Engine is only available on Workers Paid plans.
- Data appears in the SQL API approximately 60 seconds after the write, not instantly.

## Architecture

```
Recipient opens email
       │
       │   GET /track/open?t={signed_token}
       ▼
Cloudflare Worker (edge, ~1 ms added latency)
  1. Verify HMAC-SHA256 token
  2. writeDataPoint() to Analytics Engine   ← non-blocking, ~0 ms
  3. Return 1×1 transparent GIF immediately
       │
       │   ~60 s propagation delay
       ▼
Analytics Engine (time-series store)
  SELECT blob2 AS campaign, COUNT() AS events ...

Recipient clicks tracked link
       │
       │   GET /track/click?t={token}&l={link_id}&u={destination_url}
       ▼
Cloudflare Worker
  1. Verify token
  2. writeDataPoint() with event_type='click'
  3. HTTP 302 → destination_url
```

## Signed Tracking Token

Embed a signed JWT-like token in tracking URLs to prevent forged opens. Sign at send time
with the message ID, campaign, and recipient hash. Verify in the Worker before writing
to Analytics Engine.

```typescript
interface TrackingPayload {
  msgId:         string;
  campaign:      string;
  recipientHash: string;
}

async function createTrackingToken(
  payload: TrackingPayload,
  secret: string,
): Promise<string> {
  const data = JSON.stringify(payload);
  const key  = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(data),
  );
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)));
  // URL-safe base64 of the JSON envelope
  return btoa(JSON.stringify({ data, sig: sigB64 }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function verifyTrackingToken(
  token: string,
  secret: string,
): Promise<TrackingPayload | null> {
  try {
    // Restore standard base64
    const b64 = token.replace(/-/g, '+').replace(/_/g, '/');
    const { data, sig } = JSON.parse(atob(b64));
    const key = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify'],
    );
    const sigBytes = Uint8Array.from(atob(sig), c => c.charCodeAt(0));
    const valid = await crypto.subtle.verify(
      'HMAC',
      key,
      sigBytes,
      new TextEncoder().encode(data),
    );
    return valid ? (JSON.parse(data) as TrackingPayload) : null;
  } catch {
    return null;
  }
}

// Call at send time — store the hash, never the raw address
async function hashRecipient(email: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(email.toLowerCase().trim()),
  );
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}
```

## Writing Events to Analytics Engine

```typescript
export interface Env {
  EMAIL_ANALYTICS:  AnalyticsEngineDataset;
  TRACKING_SECRET:  string;
}

function writeEmailEvent(
  ae:            AnalyticsEngineDataset,
  type:          'open' | 'click',
  campaign:      string,
  msgId:         string,
  recipientHash: string,
  linkId?:       string,
): void {
  ae.writeDataPoint({
    blobs: [
      type,              // blob1: 'open' | 'click'
      campaign,          // blob2: campaign slug — also the index for fast GROUP BY
      msgId,             // blob3: message ID
      recipientHash,     // blob4: SHA-256 of lowercased email
      linkId ?? '',      // blob5: link ID for click events, empty for opens
    ],
    doubles: [
      1,                 // double1: event count (always 1; SUM() gives totals)
    ],
    indexes: [campaign], // single index; pick your most-queried dimension
  });
  // writeDataPoint() returns void — errors do not throw
}
```

## Worker Handler: Open Pixel

```typescript
// 43-byte 1×1 transparent GIF
const TRANSPARENT_GIF = new Uint8Array([
  0x47,0x49,0x46,0x38,0x39,0x61,0x01,0x00,0x01,0x00,0x80,0x00,0x00,
  0xFF,0xFF,0xFF,0x00,0x00,0x00,0x21,0xF9,0x04,0x00,0x00,0x00,0x00,
  0x00,0x2C,0x00,0x00,0x00,0x00,0x01,0x00,0x01,0x00,0x00,0x02,0x02,
  0x44,0x01,0x00,0x3B,
]);

async function handleOpen(
  request: Request,
  env: Env,
): Promise<Response> {
  const url   = new URL(request.url);
  const token = url.searchParams.get('t');

  if (token) {
    const payload = await verifyTrackingToken(token, env.TRACKING_SECRET);
    if (payload) {
      writeEmailEvent(
        env.EMAIL_ANALYTICS,
        'open',
        payload.campaign,
        payload.msgId,
        payload.recipientHash,
      );
    }
    // Invalid tokens are silently ignored — the pixel is returned anyway
    // so the recipient does not see a broken image.
  }

  return new Response(TRANSPARENT_GIF, {
    headers: {
      'Content-Type':  'image/gif',
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      'Pragma':        'no-cache',
    },
  });
}
```

## Worker Handler: Click Redirect

```typescript
async function handleClick(
  request: Request,
  env: Env,
): Promise<Response> {
  const url         = new URL(request.url);
  const token       = url.searchParams.get('t');
  const linkId      = url.searchParams.get('l') ?? 'unknown';
  const destination = url.searchParams.get('u');

  // Validate the destination URL before redirecting
  if (!destination) return new Response('Bad Request', { status: 400 });
  let destUrl: URL;
  try {
    destUrl = new URL(destination);
  } catch {
    return new Response('Bad Request', { status: 400 });
  }
  // Allow only https:// destinations to prevent open-redirect abuse
  if (destUrl.protocol !== 'https:') {
    return new Response('Forbidden', { status: 403 });
  }

  if (token) {
    const payload = await verifyTrackingToken(token, env.TRACKING_SECRET);
    if (payload) {
      writeEmailEvent(
        env.EMAIL_ANALYTICS,
        'click',
        payload.campaign,
        payload.msgId,
        payload.recipientHash,
        linkId,
      );
    }
  }

  return Response.redirect(destination, 302);
}
```

## Worker Entry Point

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === '/track/open')  return handleOpen(request, env);
    if (pathname === '/track/click') return handleClick(request, env);

    return new Response('Not Found', { status: 404 });
  },
};
```

## wrangler.toml

```toml
name = "email-tracker"
main = "src/worker.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "EMAIL_ANALYTICS"
dataset = "email_tracking"

# Set via: wrangler secret put TRACKING_SECRET
```

## Querying the Analytics Engine SQL API

Query from your backend API (Node.js, Python, etc.) — not from inside a Worker — using
a Cloudflare API token with `Analytics Engine: Read` scope.

```typescript
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN  = process.env.CF_AE_READ_TOKEN!;

async function queryAE(sql: string): Promise<unknown> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method:  'POST',
      headers: {
        Authorization: `Bearer ${CF_API_TOKEN}`,
        'Content-Type': 'text/plain',
      },
      body: sql,
    },
  );
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Analytics Engine error ${res.status}: ${err}`);
  }
  return res.json();
}

// ── Opens and clicks per campaign, last 7 days ────────────────────────────────
const summary = await queryAE(`
  SELECT
    blob2              AS campaign,
    blob1              AS event_type,
    SUM(double1)       AS total_events,
    COUNT(DISTINCT blob4) AS unique_recipients
  FROM email_tracking
  WHERE timestamp > NOW() - INTERVAL '7' DAY
  GROUP BY blob2, blob1
  ORDER BY total_events DESC
`);

// ── Top clicked links, last 30 days ───────────────────────────────────────────
const topLinks = await queryAE(`
  SELECT
    blob2        AS campaign,
    blob5        AS link_id,
    SUM(double1) AS clicks,
    COUNT(DISTINCT blob4) AS unique_clickers
  FROM email_tracking
  WHERE blob1 = 'click'
    AND timestamp > NOW() - INTERVAL '30' DAY
  GROUP BY blob2, blob5
  ORDER BY clicks DESC
  LIMIT 50
`);

// ── Hourly open rate for a single campaign (combine with D1 send count) ───────
const hourly = await queryAE(`
  SELECT
    toStartOfHour(timestamp) AS hour,
    SUM(double1)             AS opens
  FROM email_tracking
  WHERE blob1 = 'open'
    AND blob2 = 'welcome-series-01'
    AND timestamp > NOW() - INTERVAL '48' HOUR
  GROUP BY hour
  ORDER BY hour
`);
```

## Anti-patterns

- **Writing raw email addresses to blobs**: Analytics Engine data is queryable by anyone
  with an API token and cannot be row-deleted. Always SHA-256 hash the lowercased address
  before writing.
- **Using Analytics Engine as a suppression list**: It is append-only with no per-row
  deletes. Maintain suppressions in D1 where you can `DELETE` or `UPDATE` rows.
- **Counting raw `SUM(double1)` as unique opens**: A single recipient may load the pixel
  multiple times (preview panes, security scanners, Gmail image proxy). Use
  `COUNT(DISTINCT blob4)` (recipient hash) for unique opener counts.
- **Setting `Cache-Control: max-age=...` on the tracking pixel**: A cached GIF is served
  from the CDN edge without executing the Worker; the open is never recorded. Always set
  `no-store`.
- **Chaining redirects**: Click tracking URLs that bounce through multiple redirect hops
  add latency visible to the recipient. The Worker should issue a single `302` directly to
  the destination.
- **Using Analytics Engine for sub-minute dashboards**: Data is visible ~60 seconds after
  write. For real-time dashboards use a KV counter or Durable Object alongside AE.

## Gotchas

- **Bot inflation**: Microsoft SafeLinks, Proofpoint URL Defence, and Gmail's image proxy
  all fire open/click events before the human recipient acts. Filter bot UA strings server-
  side or use `COUNT(DISTINCT blob4)` with a per-campaign short-window deduplication
  query to detect non-human spikes.
- **`indexes` is a single string**: `writeDataPoint` accepts `indexes: string[]` in the
  type definition but Cloudflare recommends populating only `indexes[0]`. Using multiple
  indexes does not error but only the first is used by the query planner.
- **Apple MPP inflates opens**: Apple Mail pre-fetches the tracking pixel on Apple's
  servers, not the recipient's device. AE open counts are therefore inflated for Apple Mail
  users. Treat open metrics as directional signals, not precise reach figures.
- **Plan requirement**: Analytics Engine is not available on the Workers Free tier.
  Attempting `writeDataPoint()` on a free plan silently fails; no data is written and no
  error is thrown.
- **Cross-dataset JOINs are unsupported**: The SQL API cannot JOIN across multiple
  datasets. To correlate send counts (stored in D1) with open counts (in AE) you must
  query both and merge at the application layer.
- **90-day retention**: Raw data points older than 90 days are dropped. If you need
  longer retention, export nightly aggregates from AE SQL API to D1 or R2.

## Verification

```bash
# 1. Deploy the Worker
wrangler deploy

# 2. Generate a test token (Node.js)
node -e "
const p = JSON.stringify({msgId:'test-001',campaign:'smoke-test',recipientHash:'abc123'});
const env = Buffer.from(JSON.stringify({data:p, sig:'test'})).toString('base64url');
console.log(env);
"
# (Use a real HMAC-signed token in production; this is for smoke-test only)

# 3. Request the open pixel
curl -si "https://email-tracker.your-subdomain.workers.dev/track/open?t=TEST_TOKEN" | head -10
# Expected: HTTP/2 200, Content-Type: image/gif

# 4. Request a click redirect
curl -si "https://email-tracker.your-subdomain.workers.dev/track/click?t=TEST_TOKEN&l=cta-1&u=https://example.com" | head -5
# Expected: HTTP/2 302, Location: https://example.com

# 5. Wait ~60 s, then query Analytics Engine
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_AE_READ_TOKEN" \
  -H "Content-Type: text/plain" \
  -d "SELECT blob1 AS type, COUNT() AS n FROM email_tracking WHERE timestamp > NOW() - INTERVAL '5' MINUTE GROUP BY blob1"
# Expected: rows for 'open' and 'click' with n >= 1
```

## Related

- `email-open-tracking` — general open tracking patterns and Apple MPP implications
- `email-click-tracking` — click redirect patterns and URL sanitisation
- `apple-mail-privacy-protection-metrics` — why raw open counts are unreliable
- `email-analytics-metrics` — metric definitions and benchmark reference
- `disposable-email-domain-detection-workers` — pre-send recipient validation at the edge
- `transactional-queue-cloudflare-queues` — queuing send events for D1 send-count writes

## Sources

- [Cloudflare Analytics Engine overview](https://developers.cloudflare.com/analytics/analytics-engine/)
- [Analytics Engine SQL API reference](https://developers.cloudflare.com/analytics/analytics-engine/sql-api/)
- [writeDataPoint() Workers API](https://developers.cloudflare.com/analytics/analytics-engine/get-started/)
- [Workers Web Crypto API](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/)
- [Cloudflare open-redirect prevention](https://developers.cloudflare.com/workers/examples/redirect/)
