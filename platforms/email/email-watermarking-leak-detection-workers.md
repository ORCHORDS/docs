# Email Watermarking for Leak Detection with Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You send confidential newsletters, investor updates, or internal bulletins and need to know if a
recipient forwards the email or leaks it publicly. By embedding a unique, invisible identifier
per recipient — a "watermark" — into the HTML before delivery, any subsequent open of that
watermarked copy reveals who the original recipient was. Workers inject the watermark at send
time; a tracking Worker attributes every open back to the original recipient via D1.

## Context

Each outbound email gets a UUID that maps to the recipient in D1. The UUID is embedded in the HTML
as a 1×1 transparent tracking pixel hosted on your Workers domain. When someone opens the email
— even if forwarded — the pixel fires and the Worker records the IP, user-agent, and timestamp
against the watermark ID. Multiple opens from different IPs on a single watermark ID indicate
forwarding or leakage. The system complements, but does not replace, standard open tracking.

## D1 Schema

```sql
CREATE TABLE watermarks (
  id          TEXT PRIMARY KEY,          -- UUID v4
  email_id    TEXT NOT NULL,             -- your internal message ID
  recipient   TEXT NOT NULL,             -- original recipient address
  subject     TEXT,
  sent_at     TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE watermark_opens (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  watermark_id  TEXT NOT NULL REFERENCES watermarks(id),
  ip            TEXT,
  country       TEXT,
  user_agent    TEXT,
  opened_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_opens_watermark ON watermark_opens(watermark_id);
```

## Injecting the Watermark at Send Time

```typescript
import { randomUUID } from 'crypto'; // available in Workers

interface WatermarkOptions {
  emailId: string;
  recipient: string;
  subject: string;
  htmlBody: string;
  baseUrl: string; // e.g. "https://track.example.com"
}

async function injectWatermark(opts: WatermarkOptions, db: D1Database): Promise<string> {
  const wid = randomUUID();

  await db
    .prepare(
      `INSERT INTO watermarks (id, email_id, recipient, subject, sent_at)
       VALUES (?, ?, ?, ?, datetime('now'))`
    )
    .bind(wid, opts.emailId, opts.recipient, opts.subject)
    .run();

  // Invisible 1x1 pixel — unique per recipient
  const pixelTag = `<img
    width="1" height="1" border="0" alt=""
    style="display:block;width:1px;height:1px;border:0;margin:0;padding:0;" />`;

  // Append before </body> or before the closing </html>
  const injected = opts.htmlBody.replace(/(<\/body>|<\/html>)/i, `${pixelTag}$1`);
  return injected;
}
```

## Watermark Tracking Worker (Pixel Handler)

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/wm\/([a-f0-9-]{36})\.gif$/);

    // Always return the pixel — never 404, as MUA retries inflate data
    const GIF_1x1 = new Uint8Array([
      0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00,
      0x80, 0x00, 0x00, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x21,
      0xf9, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x2c, 0x00, 0x00,
      0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44,
      0x01, 0x00, 0x3b,
    ]);

    if (match) {
      const wid = match[1];
      const cf = request.cf as IncomingRequestCfProperties;

      // Non-blocking DB write
      const ip = request.headers.get('cf-connecting-ip') ?? '';
      const ua = request.headers.get('user-agent') ?? '';
      const country = cf?.country ?? '';

      env.ctx.waitUntil(
        env.DB.prepare(
          `INSERT INTO watermark_opens (watermark_id, ip, country, user_agent)
           VALUES (?, ?, ?, ?)`
        )
          .bind(wid, ip, country, ua)
          .run()
      );
    }

    return new Response(GIF_1x1, {
      headers: {
        'Content-Type': 'image/gif',
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        Pragma: 'no-cache',
      },
    });
  },
} satisfies ExportedHandler<Env>;
```

## Querying for Suspected Leaks

```typescript
interface LeakSuspect {
  watermarkId: string;
  recipient: string;
  subject: string;
  openCount: number;
  uniqueIps: number;
  countries: string;
}

async function detectLeaks(db: D1Database, minUniqueIps = 3): Promise<LeakSuspect[]> {
  const result = await db
    .prepare(
      `SELECT
         w.id            AS watermarkId,
         w.recipient,
         w.subject,
         COUNT(o.id)     AS openCount,
         COUNT(DISTINCT o.ip) AS uniqueIps,
         GROUP_CONCAT(DISTINCT o.country) AS countries
       FROM watermarks w
       JOIN watermark_opens o ON o.watermark_id = w.id
       GROUP BY w.id
       HAVING uniqueIps >= ?
       ORDER BY uniqueIps DESC`
    )
    .bind(minUniqueIps)
    .all<LeakSuspect>();

  return result.results;
}
```

## Alert on Leak Detection

```typescript
async function alertOnLeak(suspect: LeakSuspect, env: Env): Promise<void> {
  const body = JSON.stringify({
    text: `Watermark leak detected!\n` +
      `Recipient: ${suspect.recipient}\n` +
      `Subject: ${suspect.subject}\n` +
      `Opens: ${suspect.openCount} from ${suspect.uniqueIps} IPs (${suspect.countries})`,
  });

  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
}
```

## Anti-patterns

- **Using the same watermark ID for all recipients**: Defeats the entire purpose; each recipient
  must have a unique UUID.
- **Blocking on pixel response until DB write completes**: Use `waitUntil()` — never delay the
  image response for analytics writes.
- **Storing PII (email addresses) only in the watermark URL**: Keep recipient data in D1 only;
  the URL carries only the opaque UUID.
- **Counting every open as a leak**: Privacy-focused MUAs pre-fetch images; use unique IP count,
  not raw open count, as the leak signal.

## Gotchas

- Apple MPP (Mail Privacy Protection) pre-fetches pixels from Apple IPs — always filter out
  Apple proxy IP ranges before counting unique IPs for leak detection.
- Some corporate email gateways strip `<img>` tags — the pixel will never fire for those recipients.
  Combine with link-based watermarks for redundancy.
- Watermark opens can arrive weeks or months later if the email is archived and reopened.
- The 1×1 GIF must always return 200 — returning 404 causes most MUAs to stop retrying, meaning
  future opens of the same email won't be recorded.
- D1 free tier has 100,000 rows/day write limit; high-volume sends need batching or a KV counter.

## Verification

```bash
# Insert a test watermark manually
wrangler d1 execute TRACKING_DB --command \
  "INSERT INTO watermarks(id,email_id,recipient,subject,sent_at) VALUES('test-uuid-1234','msg1','you@test.com','Test','2026-08-23T00:00:00')"

# Trigger the pixel
curl -I "https://track.example.com/wm/test-uuid-1234.gif"

# Check recorded open
wrangler d1 execute TRACKING_DB --command \
  "SELECT * FROM watermark_opens WHERE watermark_id='test-uuid-1234'"
```

## Related

- `email-open-tracking.md`
- `email-open-click-analytics-engine.md`
- `analytics-engine-email-tracking.md`
- `email-click-tracking-privacy-preserving-workers.md`
- `apple-mail-privacy-protection-metrics.md`

## Sources

- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare Workers Runtime API — https://developers.cloudflare.com/workers/runtime-apis/
- Apple MPP IP ranges — https://developer.apple.com/news/network-transition/
- RFC 5322 — Internet Message Format
