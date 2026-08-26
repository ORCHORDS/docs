# Email Open Tracking with 1×1 Pixel in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You send transactional and marketing emails and have no visibility into whether recipients actually open them. You need per-email open tracking using a 1×1 transparent tracking pixel, bot-filtered open deduplication, an Analytics Engine dataset for aggregated metrics, and an API endpoint that returns open-rate statistics by campaign.

---

## Context

Email open tracking works by embedding a tiny transparent image URL unique to each sent message. When the email client loads the image, the Worker records an open event. The challenge is distinguishing real human opens from email prefetching bots and spam scanners. Analytics Engine provides a cost-efficient columnar write path (no reads in the hot path), while D1 stores deduplicated open records for accurate per-email counts.

Prerequisites:
- Analytics Engine dataset bound as `AE` (via `[[analytics_engine_datasets]]` in wrangler.toml)
- D1 database bound as `DB`
- KV namespace bound as `OPEN_KV` for temporary dedup window (optional; D1 alone works)
- A short-lived signed URL mechanism (HMAC-SHA256 using a Workers secret)

---

## Solution

```typescript
// wrangler.toml (excerpt)
// [[analytics_engine_datasets]]
// binding = "AE"
// dataset = "email_opens"

export interface Env {
  AE: AnalyticsEngineDataset;
  DB: D1Database;
  OPEN_KV: KVNamespace;
  PIXEL_SECRET: string; // Workers secret for HMAC signing
  BASE_URL: string;    // e.g. https://track.example.com
}

// ── D1 schema ─────────────────────────────────────────────────────────────────
// CREATE TABLE IF NOT EXISTS email_opens (
//   id           TEXT PRIMARY KEY,
//   message_id   TEXT NOT NULL,
//   campaign_id  TEXT,
//   recipient    TEXT NOT NULL,
//   opened_at    TEXT NOT NULL,
//   ip_hash      TEXT,
//   user_agent   TEXT
// );
// CREATE INDEX IF NOT EXISTS idx_opens_message   ON email_opens(message_id);
// CREATE INDEX IF NOT EXISTS idx_opens_campaign  ON email_opens(campaign_id);
// CREATE INDEX IF NOT EXISTS idx_opens_recipient ON email_opens(message_id, recipient);

// ── 1×1 transparent GIF (base64, 35 bytes) ───────────────────────────────────
const TRANSPARENT_GIF_B64 =
  'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
const PIXEL_BYTES = Uint8Array.from(
  atob(TRANSPARENT_GIF_B64),
  (c) => c.charCodeAt(0)
);

// ── HMAC signing helpers ──────────────────────────────────────────────────────
async function importKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify']
  );
}

async function signPayload(key: CryptoKey, payload: string): Promise<string> {
  const sig = await crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(payload)
  );
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

async function verifyPayload(
  key: CryptoKey,
  payload: string,
  sig: string
): Promise<boolean> {
  const normalised = sig.replace(/-/g, '+').replace(/_/g, '/');
  const sigBytes = Uint8Array.from(atob(normalised), (c) => c.charCodeAt(0));
  return crypto.subtle.verify(
    'HMAC',
    key,
    sigBytes,
    new TextEncoder().encode(payload)
  );
}

// ── Pixel URL generation (called before send) ────────────────────────────────
export async function generatePixelUrl(
  env: Env,
  messageId: string,
  campaignId: string,
  recipient: string
): Promise<string> {
  const key = await importKey(env.PIXEL_SECRET);
  const payload = `${messageId}:${campaignId}:${recipient}`;
  const sig = await signPayload(key, payload);
  // Embed params in URL; recipient is base64url-encoded to avoid @ in path
  const encodedRecipient = btoa(recipient).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  return `${env.BASE_URL}/pixel/${messageId}/${campaignId}/${encodedRecipient}/${sig}.gif`;
}

// ── Bot filtering heuristics ─────────────────────────────────────────────────
const BOT_UA_PATTERNS = [
  /bot/i,
  /crawl/i,
  /spider/i,
  /preview/i,
  /prefetch/i,
  /scan/i,
  /checker/i,
  /validator/i,
  /gmail image proxy/i,   // Google Image Proxy (still a human open, keep this commented if you want to count it)
  /yahoo! slurp/i,
  /bingbot/i,
];

function isBotUserAgent(ua: string | null): boolean {
  if (!ua) return false;
  return BOT_UA_PATTERNS.some((p) => p.test(ua));
}

// Rapid successive opens heuristic: if same message+recipient opened within 2s, likely a scanner
async function isRapidSuccessiveOpen(
  kv: KVNamespace,
  messageId: string,
  recipient: string
): Promise<boolean> {
  const kvKey = `open:${messageId}:${recipient}`;
  const existing = await kv.get(kvKey);
  if (existing !== null) return true; // seen within TTL window
  await kv.put(kvKey, '1', { expirationTtl: 2 }); // 2-second window
  return false;
}

// ── Deduplication (one open per message+recipient per day) ───────────────────
async function isDuplicate(
  db: D1Database,
  messageId: string,
  recipient: string
): Promise<boolean> {
  const today = new Date().toISOString().slice(0, 10);
  const { results } = await db
    .prepare(
      `SELECT 1 FROM email_opens
       WHERE message_id = ? AND recipient = ? AND opened_at >= ?
       LIMIT 1`
    )
    .bind(messageId, recipient, today)
    .all();
  return results.length > 0;
}

// ── Analytics Engine write ────────────────────────────────────────────────────
function recordOpenEvent(
  ae: AnalyticsEngineDataset,
  messageId: string,
  campaignId: string,
  recipient: string,
  isBot: boolean
): void {
  ae.writeDataPoint({
    blobs: [messageId, campaignId, recipient, isBot ? 'bot' : 'human'],
    doubles: [1],
    indexes: [campaignId],
  });
}

// ── Hash IP for privacy ───────────────────────────────────────────────────────
async function hashIp(ip: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(ip)
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 16); // truncate for privacy
}

// ── Worker fetch handler ──────────────────────────────────────────────────────
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // ── Route: GET /pixel/:messageId/:campaignId/:encodedRecipient/:sig.gif ──
    const pixelMatch = url.pathname.match(
      /^\/pixel\/([^/]+)\/([^/]+)\/([^/]+)\/([^/]+)\.gif$/
    );
    if (pixelMatch) {
      const [, messageId, campaignId, encodedRecipient, sig] = pixelMatch;
      const recipient = atob(encodedRecipient.replace(/-/g, '+').replace(/_/g, '/'));

      // Always respond with the pixel immediately; tracking is done in waitUntil
      const pixelResponse = new Response(PIXEL_BYTES, {
        status: 200,
        headers: {
          'Content-Type': 'image/gif',
          'Cache-Control': 'no-store, no-cache, must-revalidate',
          'Pragma': 'no-cache',
        },
      });

      ctx.waitUntil(
        (async () => {
          // 1. Verify HMAC signature
          const cryptoKey = await importKey(env.PIXEL_SECRET);
          const payload = `${messageId}:${campaignId}:${recipient}`;
          const valid = await verifyPayload(cryptoKey, payload, sig);
          if (!valid) return;

          const ua = request.headers.get('user-agent');
          const ip = request.headers.get('cf-connecting-ip') ?? '';

          // 2. Bot UA filter
          if (isBotUserAgent(ua)) {
            recordOpenEvent(env.AE, messageId, campaignId, recipient, true);
            return;
          }

          // 3. Rapid successive open filter
          if (await isRapidSuccessiveOpen(env.OPEN_KV, messageId, recipient)) return;

          // 4. Dedup per-day per-recipient
          if (await isDuplicate(env.DB, messageId, recipient)) return;

          // 5. Write canonical open to D1
          const ipHash = await hashIp(ip);
          await env.DB
            .prepare(
              `INSERT INTO email_opens (id, message_id, campaign_id, recipient, opened_at, ip_hash, user_agent)
               VALUES (?, ?, ?, ?, ?, ?, ?)`
            )
            .bind(
              crypto.randomUUID(),
              messageId,
              campaignId,
              recipient,
              new Date().toISOString(),
              ipHash,
              ua ?? ''
            )
            .run();

          // 6. Write to Analytics Engine (fast columnar path)
          recordOpenEvent(env.AE, messageId, campaignId, recipient, false);
        })()
      );

      return pixelResponse;
    }

    // ── Route: GET /stats/:campaignId — open rate for a campaign ─────────────
    const statsMatch = url.pathname.match(/^\/stats\/([^/]+)$/);
    if (statsMatch && request.method === 'GET') {
      const [, campaignId] = statsMatch;
      const { results } = await env.DB
        .prepare(
          `SELECT
             COUNT(DISTINCT recipient)    AS unique_opens,
             COUNT(*)                     AS total_opens,
             MIN(opened_at)               AS first_open,
             MAX(opened_at)               AS last_open
           FROM email_opens
           WHERE campaign_id = ?`
        )
        .bind(campaignId)
        .all<{
          unique_opens: number;
          total_opens: number;
          first_open: string;
          last_open: string;
        }>();
      return Response.json(results[0] ?? { unique_opens: 0, total_opens: 0 });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Implementation Details

- **Pixel URL structure**: `/{messageId}/{campaignId}/{base64url(recipient)}/{hmac-sig}.gif`. The HMAC prevents forged pixel requests from inflating open counts by third parties.
- **`ctx.waitUntil`**: the pixel response is sent immediately (important for UX and deliverability scoring — slow pixel responses can cause email clients to skip loading), while all tracking logic runs asynchronously.
- **Analytics Engine vs. D1**: AE is used for the high-frequency write path (every open event, including bots and duplicates) to power real-time aggregation queries via the AE SQL API. D1 stores only deduplicated human opens for accurate per-email counts.
- **Bot heuristics**: the two-second rapid-successive-open filter catches URL scanners that fire multiple requests in quick succession. The User-Agent denylist catches known crawlers. Neither is perfect — iOS Mail Privacy Protection proxies all image loads through Apple servers; treat all iOS Mail opens as potentially bot-proxied.
- **IP hashing**: storing a truncated SHA-256 of the IP allows geographic dedup (same IP opening 100 times in 1 second is a scanner) without retaining PII.

---

## Anti-patterns

- **Relying solely on open tracking to measure engagement** — open tracking is inherently unreliable due to image blocking, proxy prefetching (Apple MPP), and Gmail image caching. Complement with click tracking.
- **Not signing pixel URLs** — unsigned pixel URLs allow anyone to fabricate opens by guessing message IDs.
- **Blocking the pixel response on D1 writes** — D1 write latency (10-50ms) will delay the GIF response and may cause email clients to time out and skip the pixel load entirely.
- **Counting every pixel load as an open** — each email client re-fetch, spam scanner, and CDN node hitting the URL will inflate counts without deduplication.

---

## Gotchas

- KV `expirationTtl` has a minimum of 60 seconds in production; the 2-second rapid-open window shown above works in preview environments but will behave as 60 seconds in production. Adjust the heuristic or use an in-memory Map keyed by request ID for sub-minute windows (memory is reset on Worker cold start, but that is acceptable for a heuristic).
- `cf-connecting-ip` is only set when the Worker is deployed behind Cloudflare's proxy (orange-cloud). In local `wrangler dev` it is absent.
- Analytics Engine `writeDataPoint` is fire-and-forget inside `waitUntil`; it does not throw on failure, so errors are silent. Monitor the AE dataset health via the Cloudflare dashboard.
- The `atob`/`btoa` functions in Workers operate on Latin-1, not UTF-8. Email addresses containing non-ASCII characters must be percent-encoded before base64 encoding.

---

## Verification

```bash
# Generate a test pixel URL (run from a local script with PIXEL_SECRET set)
node -e "
const crypto = require('crypto');
const secret = process.env.PIXEL_SECRET;
const payload = 'msg-001:camp-001:test@example.com';
const sig = crypto.createHmac('sha256', secret).update(payload).digest('base64url');
const encoded = Buffer.from('test@example.com').toString('base64url');
console.log('https://track.example.com/pixel/msg-001/camp-001/' + encoded + '/' + sig + '.gif');
"

# Curl the pixel and verify 200 + GIF content-type
curl -I 'https://track.example.com/pixel/...'

# Check opens in D1
wrangler d1 execute email-db --command \
  "SELECT campaign_id, COUNT(*) AS opens FROM email_opens GROUP BY campaign_id;"

# Open rate via stats API
curl https://track.example.com/stats/camp-001
```

---

## Related

- `workers-transactional-email-queue.md` — injecting the pixel URL into the HTML body before enqueuing
- `workers-email-template-versioning.md` — appending `<img >` as a template variable
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/

---

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
