# Email Open Tracking with 1×1 Tracking Pixel Served from Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You send transactional and marketing emails and need to know which emails are opened so you can measure delivery effectiveness, trigger follow-up sequences, and identify unengaged subscribers. You also want to track link clicks to measure conversion. You need this data stored in D1 for aggregation, with privacy controls (honoring opt-out from tracking and Apple MPP awareness), without relying on a third-party ESP analytics platform.

## Context

Email open tracking works by embedding a 1×1 transparent GIF at a unique URL in the email HTML. When the email client renders the HTML, it fetches the image, which is intercepted by a Worker. The Worker records the open event and returns the GIF. Link tracking works by replacing all links in the email with redirect URLs that pass through the Worker before forwarding to the destination.

Privacy considerations: Apple Mail Privacy Protection (MPP, iOS 15+) pre-fetches all images in emails, inflating open rates artificially. Google Image Proxy caches images so that subsequent opens from the same Gmail account show cached responses. Both must be accounted for in data interpretation. GDPR and CASL require that tracking pixels are disclosed in the privacy policy; some jurisdictions require explicit consent before behavioural tracking.

## Solution

### Wrangler Configuration

```toml
# wrangler.toml
name = "email-tracker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "TRACKING_TOKENS"
id = "<tracking-tokens-kv-id>"

[[d1_databases]]
binding = "DB"
database_name = "email-analytics"
database_id = "<your-d1-database-id>"
```

### D1 Schema

```sql
-- migrations/001_tracking.sql
CREATE TABLE IF NOT EXISTS email_sends (
  token       TEXT PRIMARY KEY,
  message_id  TEXT NOT NULL,
  recipient   TEXT NOT NULL,
  template    TEXT,
  sent_at     TEXT NOT NULL,
  tracking_opt_out INTEGER NOT NULL DEFAULT 0  -- 1 = do not track
);

CREATE TABLE IF NOT EXISTS email_opens (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  token        TEXT NOT NULL,
  opened_at    TEXT NOT NULL,
  user_agent   TEXT,
  ip_country   TEXT,
  is_bot       INTEGER NOT NULL DEFAULT 0,  -- 1 = suspected MPP/proxy
  FOREIGN KEY (token) REFERENCES email_sends(token)
);

CREATE TABLE IF NOT EXISTS link_clicks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  token        TEXT NOT NULL,
  link_id      TEXT NOT NULL,  -- identifier for the specific link
  destination  TEXT NOT NULL,
  clicked_at   TEXT NOT NULL,
  user_agent   TEXT,
  ip_country   TEXT,
  FOREIGN KEY (token) REFERENCES email_sends(token)
);

CREATE INDEX IF NOT EXISTS idx_opens_token ON email_opens(token);
CREATE INDEX IF NOT EXISTS idx_clicks_token ON link_clicks(token);
CREATE INDEX IF NOT EXISTS idx_sends_message ON email_sends(message_id);
```

### Token Generation and KV Storage

```typescript
// src/tokens.ts
export interface Env {
  TRACKING_TOKENS: KVNamespace;
  DB: D1Database;
}

export interface TrackingToken {
  token: string;
  messageId: string;
  recipient: string;
  template?: string;
  optOut: boolean;
}

const TOKEN_TTL_SECONDS = 90 * 24 * 60 * 60; // 90 days

/**
 * Generate a unique tracking token for an email send.
 * Stores token metadata in both KV (fast lookup at pixel request time)
 * and D1 (queryable analytics).
 */
export async function createTrackingToken(
  env: Env,
  messageId: string,
  recipient: string,
  template?: string
): Promise<string> {
  const token = crypto.randomUUID().replace(/-/g, '');

  const record: TrackingToken = {
    token,
    messageId,
    recipient,
    template,
    optOut: false,
  };

  await Promise.all([
    // KV for fast pixel-endpoint lookups.
    env.TRACKING_TOKENS.put(token, JSON.stringify(record), {
      expirationTtl: TOKEN_TTL_SECONDS,
    }),
    // D1 for queryable send log.
    env.DB.prepare(
      `INSERT OR IGNORE INTO email_sends
       (token, message_id, recipient, template, sent_at, tracking_opt_out)
       VALUES (?, ?, ?, ?, ?, 0)`
    )
      .bind(token, messageId, recipient, template ?? null, new Date().toISOString())
      .run(),
  ]);

  return token;
}

/**
 * Mark a token as opted out of tracking.
 * Pixel responses will still be served (so the email renders), but no open event is recorded.
 */
export async function optOutToken(env: Env, token: string): Promise<void> {
  await Promise.all([
    env.DB.prepare(
      `UPDATE email_sends SET tracking_opt_out=1 WHERE token=?`
    ).bind(token).run(),
    // Update KV record.
    env.TRACKING_TOKENS.get(token, { type: 'json' }).then(async (rec) => {
      if (rec) {
        (rec as TrackingToken).optOut = true;
        await env.TRACKING_TOKENS.put(token, JSON.stringify(rec), {
          expirationTtl: TOKEN_TTL_SECONDS,
        });
      }
    }),
  ]);
}
```

### 1x1 Transparent GIF Response

```typescript
// src/pixel.ts
// Minimal 1x1 transparent GIF (35 bytes), base64-encoded.
const TRANSPARENT_GIF_B64 =
  'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

export function transparentGifResponse(): Response {
  const bytes = Uint8Array.from(atob(TRANSPARENT_GIF_B64), (c) =>
    c.charCodeAt(0)
  );
  return new Response(bytes, {
    status: 200,
    headers: {
      'Content-Type': 'image/gif',
      // Prevent caching by email clients and proxies.
      'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
      Pragma: 'no-cache',
      Expires: '0',
    },
  });
}
```

### Bot / MPP Detection

```typescript
// src/bot-detection.ts
// Heuristics for Apple MPP and Google Image Proxy.
const BOT_UA_PATTERNS = [
  /Googlebot/i,
  /YahooMailProxy/i,
  // Apple MPP sends a specific user-agent:
  /Apple.*Mail.*Privacy/i,
  /com\.apple\.mail/i,
  // Generic image proxy signals:
  /MailgunBot/i,
  /EmailPreview/i,
];

export function isBotOpen(userAgent: string): boolean {
  return BOT_UA_PATTERNS.some((pattern) => pattern.test(userAgent));
}
```

### Tracking Pixel Endpoint

```typescript
// src/track-open.ts
import { Env } from './tokens';
import { transparentGifResponse } from './pixel';
import { isBotOpen } from './bot-detection';

/**
 * GET /t/open/{token}.gif
 * Records an open event and returns the tracking pixel.
 */
export async function handleOpenPixel(
  request: Request,
  env: Env,
  token: string
): Promise<Response> {
  // Always return the GIF immediately — never block email rendering.
  const gifResponse = transparentGifResponse();

  // Look up token from KV (fast path).
  const record = await env.TRACKING_TOKENS.get(token, { type: 'json' }) as
    | import('./tokens').TrackingToken
    | null;

  if (!record || record.optOut) {
    // Unknown token or opted-out — return pixel silently, no recording.
    return gifResponse;
  }

  const userAgent = request.headers.get('User-Agent') ?? '';
  const country = request.cf?.country ?? '';
  const isBot = isBotOpen(userAgent) ? 1 : 0;

  // Write open event to D1 (non-blocking — use waitUntil in Worker context).
  // In a fetch handler, wrap with ctx.waitUntil(); here we await for simplicity.
  await env.DB.prepare(
    `INSERT INTO email_opens (token, opened_at, user_agent, ip_country, is_bot)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(token, new Date().toISOString(), userAgent.slice(0, 500), country, isBot)
    .run();

  return gifResponse;
}
```

### Link Click Tracking

```typescript
// src/track-click.ts
import { Env } from './tokens';

/**
 * GET /t/click/{token}/{linkId}?url={destination}
 * Records a click event and redirects to the destination URL.
 */
export async function handleClickRedirect(
  request: Request,
  env: Env,
  token: string,
  linkId: string
): Promise<Response> {
  const url = new URL(request.url);
  const destination = url.searchParams.get('url');

  if (!destination) {
    return new Response('Missing url parameter', { status: 400 });
  }

  // Validate destination URL to prevent open redirect abuse.
  let destUrl: URL;
  try {
    destUrl = new URL(destination);
  } catch {
    return new Response('Invalid destination URL', { status: 400 });
  }

  // Only allow redirects to http/https.
  if (!['http:', 'https:'].includes(destUrl.protocol)) {
    return new Response('Forbidden protocol', { status: 400 });
  }

  const record = await env.TRACKING_TOKENS.get(token, { type: 'json' }) as
    | import('./tokens').TrackingToken
    | null;

  if (record && !record.optOut) {
    const userAgent = request.headers.get('User-Agent') ?? '';
    const country = request.cf?.country ?? '';

    await env.DB.prepare(
      `INSERT INTO link_clicks (token, link_id, destination, clicked_at, user_agent, ip_country)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
      .bind(
        token,
        linkId,
        destination.slice(0, 2000),
        new Date().toISOString(),
        userAgent.slice(0, 500),
        country
      )
      .run();
  }

  return Response.redirect(destination, 302);
}
```

### Unsubscribe from Tracking

```typescript
// src/unsubscribe-tracking.ts
import { Env, optOutToken } from './tokens';

/**
 * GET /t/optout/{token}
 * Removes this recipient from tracking. Separate from email unsubscribe.
 */
export async function handleTrackingOptOut(
  env: Env,
  token: string
): Promise<Response> {
  await optOutToken(env, token);
  return new Response(
    '<html><body><p>You have been removed from email open tracking. ' +
      'You will still receive emails unless you unsubscribe separately.</p></body></html>',
    { headers: { 'Content-Type': 'text/html' } }
  );
}
```

### Worker Entry Point

```typescript
// src/index.ts
import { Env } from './tokens';
import { handleOpenPixel } from './track-open';
import { handleClickRedirect } from './track-click';
import { handleTrackingOptOut } from './unsubscribe-tracking';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const parts = url.pathname.split('/').filter(Boolean);
    // parts: ['t', 'open' | 'click' | 'optout', token, ...]

    if (parts[0] !== 't') {
      return new Response('Not Found', { status: 404 });
    }

    const action = parts[1];
    const token = parts[2]?.replace(/\.gif$/, '');

    if (!token) {
      return new Response('Bad Request', { status: 400 });
    }

    if (action === 'open') {
      // Use ctx.waitUntil so the GIF is returned immediately
      // while the D1 write completes in the background.
      const gifResponse = new Response(
        Uint8Array.from(
          atob('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'),
          (c) => c.charCodeAt(0)
        ),
        {
          headers: {
            'Content-Type': 'image/gif',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
          },
        }
      );
      ctx.waitUntil(handleOpenPixel(request, env, token));
      return gifResponse;
    }

    if (action === 'click') {
      const linkId = parts[3] ?? 'unknown';
      return handleClickRedirect(request, env, token, linkId);
    }

    if (action === 'optout') {
      return handleTrackingOptOut(env, token);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

### Embedding in Email HTML

```typescript
// src/embed.ts
const TRACKER_BASE_URL = 'https://track.example.com';

/**
 * Add tracking pixel and rewrite links in an email HTML template.
 */
export function instrumentEmail(
  html: string,
  token: string
): string {
  // Add tracking pixel just before </body>.
  const pixel = `<img  width="1" height="1" alt="" style="display:none !important; width:0 !important; max-width:0 !important; height:0 !important; border:0 !important; margin:0 !important; padding:0 !important;" />`;
  let instrumented = html.replace('</body>', `${pixel}\n</body>`);

  // Rewrite <a href> links (except mailto:, tel:, unsubscribe).
  let linkIndex = 0;
  instrumented = instrumented.replace(
    /(<a\s[^>]*href=["'])([^"'#][^"']*?)(["'])/gi,
    (_match, prefix, href, suffix) => {
      if (/^(mailto:|tel:|#)/i.test(href)) return _match;
      const linkId = `l${linkIndex++}`;
      const tracked = `${TRACKER_BASE_URL}/t/click/${token}/${linkId}?url=${encodeURIComponent(href)}`;
      return `${prefix}${tracked}${suffix}`;
    }
  );

  // Add opt-out from tracking link in footer (privacy best practice).
  instrumented = instrumented.replace(
    /{\{tracking_optout_link\}}/g,
    `${TRACKER_BASE_URL}/t/optout/${token}`
  );

  return instrumented;
}
```

## Implementation Details

- Use `ctx.waitUntil()` in the open pixel handler so the GIF response is returned immediately without waiting for the D1 write. This prevents slow D1 writes from delaying email rendering in slow clients.
- The 35-byte transparent GIF is the smallest valid single-pixel GIF. It is inline in the source as a base64 constant rather than stored in R2 — R2 latency would add 10–30 ms to every pixel request.
- Token TTL in KV should match your analytics retention period. After the TTL, opens are still served (no KV hit) but not recorded. Set the KV TTL to be slightly longer than the D1 retention period.
- The `Cache-Control: no-store` header prevents intermediate proxies and CDN edge caches from serving a cached copy of the pixel, which would prevent open recording. However, Google Image Proxy and Apple MPP will still pre-fetch and potentially cache the image client-side.
- For Apple MPP detection: if the User-Agent contains `com.apple.mail` or `Apple Mail Privacy`, mark `is_bot=1` in the database. Exclude bot opens from "unique open" count but include them in a separate "delivered to Apple device" metric.

## Anti-patterns

- **Not using `ctx.waitUntil()`** — a synchronous D1 write in the pixel endpoint adds latency that is visible to the email client as slow image loading, affecting perceived rendering performance.
- **Using the same token for all links in an email** — you cannot distinguish which link was clicked. Use `linkId` per link as shown.
- **Storing destination URLs in D1 only at click time** — the URL is in the query parameter, which can be manipulated. Pre-register expected link targets at send time and validate at click time.
- **Not validating the redirect destination** — an open redirect endpoint can be abused by phishers. Validate the protocol and optionally restrict to a whitelist of allowed domains.
- **Counting Apple MPP opens as real opens for engagement scoring** — MPP fires immediately on mail receipt, not on human read. Mix MPP opens into engagement scores and your re-engagement suppression logic breaks.
- **Embedding tracking pixels without privacy policy disclosure** — violates GDPR recital 30 (tracking technologies must be disclosed).

## Gotchas

- `request.cf?.country` is available only in deployed Workers, not in `wrangler dev` local development. It is `undefined` locally; always use `?? ''` as a fallback.
- `ctx.waitUntil()` accepts a Promise. If the Promise rejects, the error is swallowed silently in production. Wrap your D1 write in try/catch and log errors to make failures visible.
- KV reads and D1 writes in the pixel endpoint run after the response is dispatched when using `waitUntil`. If the Worker is terminated early (request cancelled), the `waitUntil` may not complete. This is acceptable for analytics (occasional lost events) but not for mission-critical writes.
- The tracking pixel must be embedded inside the `<body>` tag. Some email clients strip `<head>` content. The `display:none` style is required but not sufficient — Outlook ignores `display:none` on `<img>` elements; the `width:0; height:0` properties handle Outlook.
- `encodeURIComponent` on a URL that is already partially encoded can double-encode it. Decode before re-encoding if the source URLs may contain existing percent-encoding.

## Verification

```bash
# Deploy
wrangler deploy

# Create a tracking token for a test send
curl -X POST https://track.example.com/admin/token \
  -H 'Authorization: Bearer <admin-token>' \
  -d '{"messageId":"test-001","recipient":"test@example.com"}'
# Returns: {"token": "abc123..."}

# Simulate an open
curl -v 'https://track.example.com/t/open/abc123.gif'
# Expect: 200 image/gif with Cache-Control: no-store

# Simulate a click
curl -v 'https://track.example.com/t/click/abc123/l0?url=https%3A%2F%2Forchords.com%2Fshop'
# Expect: 302 redirect to https://example.com/shop

# Check D1 for events
wrangler d1 execute email-analytics \
  --command "SELECT s.recipient, o.opened_at, o.is_bot FROM email_opens o JOIN email_sends s ON s.token=o.token ORDER BY o.opened_at DESC LIMIT 10"

# Verify opt-out
curl 'https://track.example.com/t/optout/abc123'
# Expect: HTML confirmation page

# Confirm opt-out in D1
wrangler d1 execute email-analytics \
  --command "SELECT token, tracking_opt_out FROM email_sends WHERE token='abc123'"
```

## Related

- `documentation/categories/email/workers-email-suppression-list-kv.md`
- `documentation/categories/email/workers-transactional-email-queue.md`
- `documentation/categories/email/workers-email-template-engine-r2.md`
- Cloudflare Workers `ctx.waitUntil` docs: https://developers.cloudflare.com/workers/runtime-apis/context/
- Apple Mail Privacy Protection overview: https://support.apple.com/en-us/HT212622
- GDPR Recital 30 (tracking technologies disclosure)

## Sources

- Cloudflare Workers documentation — fetch handler and ExecutionContext (2025)
- Cloudflare D1 documentation (2025)
- Apple Mail Privacy Protection technical overview (2021)
- Litmus — Email tracking and Apple MPP guide (2022)
- GDPR.eu — Recital 30 and cookie/tracking consent requirements
- RFC 2397 (data: URI scheme) — GIF encoding reference
