# Per-Recipient Email Rate Limiting with KV, MailChannels, and Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Without rate limits a single bug or abusive caller can send thousands of emails to the same recipient within minutes, triggering spam filters and MailChannels quota overages. A KV sliding-window counter keyed per recipient per day rejects excess sends before they reach MailChannels and an hourly sub-limit handles burst abuse.

---

## Context

Cloudflare KV is well-suited for lightweight counters: writes are fast, the value TTL handles automatic counter expiry, and Workers can read and conditionally write in the same request without extra infrastructure. Two counters are maintained per recipient: a daily counter (`ratelimit:{email}:YYYY-MM-DD`) expiring at midnight UTC and an hourly counter (`ratelimit:{email}:YYYY-MM-DDTHH`) expiring at the end of the current hour. If either counter exceeds its threshold the send is rejected. Permitted sends are logged to D1 `email_send_log` for audit. A Cron Trigger runs daily to emit send-volume metrics to Analytics Engine and optionally reset KV counters ahead of their TTL for emergency suppression.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "email-ratelimit-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
DAILY_LIMIT  = "50"
HOURLY_LIMIT = "10"

[[kv_namespaces]]
binding = "RATE_KV"
id = "YOUR_KV_NAMESPACE_ID"

[[d1_databases]]
binding = "DB"
database_name = "email-db"
database_id = "YOUR_D1_DATABASE_ID"

[[analytics_engine_datasets]]
binding = "EMAIL_METRICS"
dataset = "email_send_volume"

[triggers]
crons = ["0 1 * * *"]   # 01:00 UTC daily
```

```sql
CREATE TABLE IF NOT EXISTS email_send_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  recipient   TEXT    NOT NULL,
  template    TEXT,
  sent_at     TEXT    NOT NULL DEFAULT (datetime('now')),
  status      TEXT    NOT NULL DEFAULT 'sent',   -- 'sent' | 'rate_limited'
  daily_count INTEGER,
  hourly_count INTEGER
);

CREATE INDEX idx_sendlog_recipient ON email_send_log(recipient);
CREATE INDEX idx_sendlog_sent_at   ON email_send_log(sent_at);
```

## Section 2 — Rate-limit check and send path

```typescript
export interface Env {
  RATE_KV: KVNamespace;
  DB: D1Database;
  EMAIL_METRICS: AnalyticsEngineDataset;
  DAILY_LIMIT: string;
  HOURLY_LIMIT: string;
}

interface RateLimitResult {
  allowed: boolean;
  dailyCount: number;
  hourlyCount: number;
  reason?: string;
}

function dayKey(email: string, now: Date): string {
  const d = now.toISOString().slice(0, 10); // YYYY-MM-DD
  return `ratelimit:${email}:${d}`;
}

function hourKey(email: string, now: Date): string {
  const h = now.toISOString().slice(0, 13); // YYYY-MM-DDTHH
  return `ratelimit:${email}:${h}`;
}

function secondsUntilMidnightUTC(now: Date): number {
  const midnight = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1)
  );
  return Math.ceil((midnight.getTime() - now.getTime()) / 1000);
}

function secondsUntilNextHour(now: Date): number {
  const nextHour = new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate(),
      now.getUTCHours() + 1
    )
  );
  return Math.ceil((nextHour.getTime() - now.getTime()) / 1000);
}

async function checkAndIncrement(
  kv: KVNamespace,
  email: string,
  dailyLimit: number,
  hourlyLimit: number
): Promise<RateLimitResult> {
  const now = new Date();
  const dk = dayKey(email, now);
  const hk = hourKey(email, now);

  const [rawDay, rawHour] = await Promise.all([
    kv.get(dk),
    kv.get(hk),
  ]);

  const dailyCount = parseInt(rawDay ?? '0', 10);
  const hourlyCount = parseInt(rawHour ?? '0', 10);

  if (dailyCount >= dailyLimit) {
    return { allowed: false, dailyCount, hourlyCount, reason: 'daily_limit_exceeded' };
  }
  if (hourlyCount >= hourlyLimit) {
    return { allowed: false, dailyCount, hourlyCount, reason: 'hourly_limit_exceeded' };
  }

  // Increment both counters atomically (best-effort — KV is eventually consistent)
  await Promise.all([
    kv.put(dk, String(dailyCount + 1), {
      expirationTtl: secondsUntilMidnightUTC(now) + 60,
    }),
    kv.put(hk, String(hourlyCount + 1), {
      expirationTtl: secondsUntilNextHour(now) + 60,
    }),
  ]);

  return { allowed: true, dailyCount: dailyCount + 1, hourlyCount: hourlyCount + 1 };
}

async function logSend(
  db: D1Database,
  recipient: string,
  template: string | null,
  status: string,
  dailyCount: number,
  hourlyCount: number
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO email_send_log (recipient, template, status, daily_count, hourly_count)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(recipient, template, status, dailyCount, hourlyCount)
    .run();
}

export async function sendWithRateLimit(
  env: Env,
  recipient: string,
  subject: string,
  htmlBody: string,
  textBody: string,
  template?: string
): Promise<{ status: number; reason?: string }> {
  const dailyLimit = parseInt(env.DAILY_LIMIT, 10);
  const hourlyLimit = parseInt(env.HOURLY_LIMIT, 10);

  const rateResult = await checkAndIncrement(
    env.RATE_KV,
    recipient,
    dailyLimit,
    hourlyLimit
  );

  if (!rateResult.allowed) {
    await logSend(
      env.DB,
      recipient,
      template ?? null,
      'rate_limited',
      rateResult.dailyCount,
      rateResult.hourlyCount
    );
    env.EMAIL_METRICS.writeDataPoint({
      blobs: [recipient, rateResult.reason ?? 'rate_limited'],
      doubles: [1],
      indexes: [recipient],
    });
    return { status: 429, reason: rateResult.reason };
  }

  const payload = {
    personalizations: [{ to: [{ email: recipient }] }],
    from: { email: 'noreply@yourdomain.com', name: 'Orchords' },
    subject,
    content: [
      { type: 'text/plain', value: textBody },
      { type: 'text/html', value: htmlBody },
    ],
  };

  const resp = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  await logSend(
    env.DB,
    recipient,
    template ?? null,
    resp.ok ? 'sent' : `error_${resp.status}`,
    rateResult.dailyCount,
    rateResult.hourlyCount
  );

  env.EMAIL_METRICS.writeDataPoint({
    blobs: [recipient, resp.ok ? 'sent' : 'error'],
    doubles: [1],
    indexes: [recipient],
  });

  return { status: resp.ok ? 202 : 502 };
}
```

## Section 3 — Cron handler for daily reporting and counter reset

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }
    const body = await request.json<{
      to: string;
      subject: string;
      html: string;
      text: string;
      template?: string;
    }>();
    const result = await sendWithRateLimit(
      env,
      body.to,
      body.subject,
      body.html,
      body.text,
      body.template
    );
    return new Response(JSON.stringify(result), {
      status: result.status === 429 ? 429 : 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Report yesterday's send volume from D1
    ctx.waitUntil(
      (async () => {
        const yesterday = new Date(Date.now() - 86_400_000)
          .toISOString()
          .slice(0, 10);

        const rows = await env.DB.prepare(
          `SELECT status, COUNT(*) AS cnt
           FROM email_send_log
           WHERE sent_at >= ? AND sent_at < ?
           GROUP BY status`
        )
          .bind(`${yesterday} 00:00:00`, `${yesterday} 23:59:59`)
          .all<{ status: string; cnt: number }>();

        for (const row of rows.results) {
          env.EMAIL_METRICS.writeDataPoint({
            blobs: ['daily_summary', row.status, yesterday],
            doubles: [row.cnt],
            indexes: ['summary'],
          });
        }

        console.log(`Daily email report written for ${yesterday}:`, rows.results);
      })()
    );
  },
};
```

---

## Anti-patterns

- **Using KV for strict atomic counters** — KV is eventually consistent; two concurrent requests can both read `0` and both write `1`, effectively bypassing the limit for a brief window. For strict enforcement use Durable Objects with `blockConcurrencyWhile`.
- **Setting counter TTL to a fixed large value** — A fixed TTL does not align with day or hour boundaries. Compute the TTL as seconds until midnight or the next hour so counters reset on schedule rather than rolling 24/1-hour windows.
- **Logging every send to D1 synchronously on the hot path** — For very high-volume senders, batch D1 writes using `ctx.waitUntil` or a Queue to keep p99 latency low.
- **Not emitting metrics** — Without Analytics Engine data points, rate-limiting decisions are invisible. Always record both `rate_limited` and `sent` events so dashboards can surface abuse patterns.

---

## Gotchas

- KV `put` with `expirationTtl` must be at least 60 seconds; the extra 60-second buffer in the TTL calculation prevents premature expiry at exactly midnight/hour boundary.
- `AnalyticsEngineDataset.writeDataPoint` is fire-and-forget and does not return a Promise; do not `await` it or check its return value.
- The Cron Trigger `0 1 * * *` fires at 01:00 UTC, giving a 1-hour buffer after midnight for any stragglers in the previous day's log.
- `DAILY_LIMIT` and `HOURLY_LIMIT` are strings in `[vars]`; always `parseInt(..., 10)` before comparison.
- Concurrent requests to the same recipient within the same millisecond can over-count by 1–2; add a small tolerance (e.g. `>= dailyLimit - 2`) if this is a concern for low-limit settings.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Send within the limit
curl -s -X POST https://your-worker.workers.dev/ \
     -H 'Content-Type: application/json' \
     -d '{"to":"alice@example.com","subject":"Hello","html":"<p>Hi</p>","text":"Hi"}'

# Exhaust the hourly limit (run 11 times if HOURLY_LIMIT=10)
for i in $(seq 1 11); do
  curl -s -X POST https://your-worker.workers.dev/ \
       -H 'Content-Type: application/json' \
       -d '{"to":"alice@example.com","subject":"Burst","html":"<p>Burst</p>","text":"Burst"}'
done

# Inspect KV counters
DATE=$(date -u +%Y-%m-%d)
HOUR=$(date -u +%Y-%m-%dT%H)
npx wrangler kv key get --namespace-id YOUR_KV_NAMESPACE_ID "ratelimit:alice@example.com:$DATE"
npx wrangler kv key get --namespace-id YOUR_KV_NAMESPACE_ID "ratelimit:alice@example.com:$HOUR"

# Check D1 audit log
npx wrangler d1 execute email-db \
  --command "SELECT status, COUNT(*) FROM email_send_log GROUP BY status;"

# Trigger the cron manually
npx wrangler cron trigger email-ratelimit-worker
```

---

## Related

- `email-unsubscribe-list-header-workers.md`
- `email-bounce-webhook-mailchannels-d1.md`
- `email-template-rendering-workers-r2.md`

---

## Sources

- Cloudflare KV — https://developers.cloudflare.com/kv/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- MailChannels Send API — https://docs.mailchannels.net/transactional-email/send-email
- Cloudflare D1 — https://developers.cloudflare.com/d1/
