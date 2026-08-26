# Email Preview Link Tracking Workers KV

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Marketing and transactional emails contain a "View in browser" preview link. You want to know exactly when, how often, and from which country that link is opened — without relying on the ESP's own pixel, which is blocked by Apple Mail Privacy Protection.

## Context
A Cloudflare Worker intercepts every preview link request, logs an Analytics Engine event with geo and user-agent metadata, then streams the pre-rendered HTML from R2 (or KV for small payloads) to the viewer. KV stores short-lived token-to-message-id mappings so the Worker can attribute the view to the correct campaign and recipient without exposing internal IDs in the URL. Because the Worker sits on your own domain, it is not filtered by corporate email proxies that block third-party trackers.

## Token Flow

```
Send time:  Worker mints a short token → stores in KV (token → {messageId, recipientId, campaignId}, TTL 30 days)
            Email body:  https://preview.yourdomain.com/v/{token}

View time:  Viewer GETs /v/{token}
            Worker reads KV → resolves metadata → logs Analytics Engine event
            Worker fetches HTML from R2 / KV → streams to viewer
            Worker returns HTML with no additional tracking pixels
```

## D1 + KV Token Schema

```typescript
// types.ts
export interface PreviewToken {
  messageId: string;
  recipientId: string;
  campaignId: string;
  htmlKey: string;   // R2 / KV key for the rendered HTML
  createdAt: string;
}
```

## Token Minting at Send Time

```typescript
// mint-preview.ts
import { Env, PreviewToken } from './types';

export async function mintPreviewToken(
  env: Env,
  payload: Omit<PreviewToken, 'createdAt'>
): Promise<string> {
  const token = crypto.randomUUID().replace(/-/g, '');
  const value: PreviewToken = { ...payload, createdAt: new Date().toISOString() };
  // 30-day TTL: preview links are valid for one month
  await env.PREVIEW_TOKENS.put(`preview:${token}`, JSON.stringify(value), {
    expirationTtl: 60 * 60 * 24 * 30,
  });
  return token;
}

export function previewUrl(baseUrl: string, token: string): string {
  return `${baseUrl}/v/${token}`;
}
```

## Preview Worker

```typescript
// worker.ts
import { Env, PreviewToken } from './types';

export interface Env {
  PREVIEW_TOKENS: KVNamespace;
  EMAIL_HTML: R2Bucket;        // fallback: KVNamespace EMAIL_HTML_KV
  EMAIL_ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/v\/([a-f0-9]{32})$/);
    if (!match) return new Response('Not Found', { status: 404 });

    const token = match[1];
    const raw = await env.PREVIEW_TOKENS.get(`preview:${token}`);
    if (!raw) {
      return new Response(
        `<html><body style="font-family:sans-serif;padding:2rem">
           <p>This preview link has expired or is invalid.</p>
         </body></html>`,
        { status: 410, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
      );
    }

    const meta: PreviewToken = JSON.parse(raw);

    // Log the preview view — fire-and-forget so it doesn't block render
    ctx.waitUntil(logPreviewView(request, meta, env));

    // Fetch pre-rendered HTML from R2
    const obj = await env.EMAIL_HTML.get(meta.htmlKey);
    if (!obj) return new Response('Email content not found', { status: 404 });

    const htmlBody = await obj.text();

    return new Response(htmlBody, {
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'private, no-store',  // never CDN-cache personalised content
        'X-Robots-Tag': 'noindex, nofollow',
      },
    });
  },
};

async function logPreviewView(
  request: Request,
  meta: PreviewToken,
  env: Env
): Promise<void> {
  const cf = (request as any).cf ?? {};
  const ua = request.headers.get('User-Agent') ?? '';

  env.EMAIL_ANALYTICS.writeDataPoint({
    blobs: [
      meta.campaignId,
      meta.recipientId,
      meta.messageId,
      cf.country ?? 'XX',
      cf.city ?? '',
      cf.timezone ?? '',
      ua.slice(0, 200),
      detectClient(ua),
    ],
    doubles: [1],
    indexes: [meta.campaignId],
  });
}

function detectClient(ua: string): string {
  if (/Outlook/i.test(ua)) return 'Outlook';
  if (/Thunderbird/i.test(ua)) return 'Thunderbird';
  if (/iPhone|iPad/i.test(ua)) return 'Apple Mobile';
  if (/Macintosh.*AppleWebKit/i.test(ua)) return 'Apple Mail';
  if (/Android/i.test(ua)) return 'Android';
  if (/Chrome/i.test(ua)) return 'Chrome';
  if (/Firefox/i.test(ua)) return 'Firefox';
  return 'Unknown';
}
```

## Analytics Engine Query

```sql
-- Preview open rate by campaign (Cloudflare Workers Analytics Engine SQL API)
SELECT
  blob1                           AS campaign_id,
  COUNT()                         AS total_views,
  COUNT(DISTINCT blob2)           AS unique_recipients,
  COUNT(DISTINCT blob4)           AS countries_reached,
  toStartOfHour(timestamp)        AS hour
FROM EMAIL_ANALYTICS
WHERE timestamp > NOW() - INTERVAL '7' DAY
  AND blob1 = 'camp_abc123'
GROUP BY campaign_id, hour
ORDER BY hour DESC;
```

## HTML Storage at Send Time

```typescript
// store-html.ts
export async function storeEmailHtml(
  env: { EMAIL_HTML: R2Bucket },
  messageId: string,
  html: string
): Promise<string> {
  const key = `emails/${messageId}.html`;
  await env.EMAIL_HTML.put(key, html, {
    httpMetadata: { contentType: 'text/html; charset=utf-8' },
    customMetadata: { storedAt: new Date().toISOString() },
  });
  return key;
}
```

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "PREVIEW_TOKENS"
id = "YOUR_KV_ID"

[[r2_buckets]]
binding = "EMAIL_HTML"
bucket_name = "email-html-store"

[[analytics_engine_datasets]]
binding = "EMAIL_ANALYTICS"
dataset = "email_preview_views"
```

## Anti-patterns
- Embedding the `messageId` or `recipientId` directly in the URL path — exposes internal IDs and allows enumeration; use an opaque random token mapped via KV instead.
- Setting `Cache-Control: public` on the preview response — CDN nodes will serve the same cached HTML to different recipients, defeating per-recipient personalisation.
- Skipping the 410 Gone response on missing token — returning 200 with an error message causes email clients to mark the link as "working" and suppress re-fetch attempts.
- Storing large HTML bodies (> 25 MB) in KV — KV value limit is 25 MB; use R2 for all HTML above 1 MB.
- Opening the preview URL in a server-side pre-fetch for spam scanning (Outlook Safe Links, etc.) — deduplicate by counting only views where the `User-Agent` does not match known scanner patterns before recording as a recipient open.

## Gotchas
- KV `expirationTtl` is set at write time and cannot be extended; if a campaign runs longer than 30 days, re-mint the token before it expires or increase the initial TTL.
- R2 `get()` returns `null` for missing objects; always null-check before calling `.text()` to avoid an uncaught `TypeError`.
- Analytics Engine `writeDataPoint` is fire-and-forget inside `ctx.waitUntil()` — it does not throw on failure; instrument a separate Logpush rule if you need guaranteed delivery of every event.
- The `request.cf` object is undefined in `wrangler dev --local`; add a fallback `?? {}` everywhere you access it.
- Bot scanners from corporate mail gateways often hit the preview URL before the human does; filter them out in your queries by excluding `blob8 = 'Unknown'` or matching known scanner UA strings.

## Verification
1. Mint a token with `mintPreviewToken`, construct the URL, and open it in a browser; confirm you receive the HTML and a 200 response.
2. Query Analytics Engine within 60 seconds and verify a row appears for the correct `campaign_id`.
3. Open the URL a second time; confirm `total_views = 2` but `unique_recipients = 1` in the query.
4. Wait for the token TTL to expire (or delete the KV key manually) and reload the URL; confirm you receive 410.
5. Inspect R2 bucket in the dashboard to confirm the HTML object is stored under `emails/{messageId}.html`.

## Related
- `email-click-tracking-privacy-preserving-workers.md`
- `analytics-engine-email-tracking.md`
- `email-open-click-analytics-engine.md`
- `email-transactional-template-personalization-r2-workers.md`
- `email-link-rewriting-utm-workers.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/analytics/analytics-engine/
