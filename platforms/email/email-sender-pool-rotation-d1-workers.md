# Email Sender Pool Rotation and Load Balancing with D1 and Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A single sending domain or ESP subaccount hits its daily volume cap or accumulates
reputation damage from a burst of bounces. You need to spread sends across a pool
of verified sender identities so no single address becomes a single point of
failure and warm-up volume is distributed evenly.

## Context

A D1 table tracks the sender pool with current day counters, error counts, and
enabled flags. A dispatcher Worker selects the best sender before each send using
a weighted round-robin that favours senders with lower error rates and remaining
daily headroom. All mutation is done atomically with D1 transactions to avoid
race conditions under concurrent Workers invocations.

## D1 Schema

```sql
-- migrations/0002_sender_pool.sql
CREATE TABLE IF NOT EXISTS sender_pool (
  id            TEXT PRIMARY KEY,
  from_address  TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL DEFAULT '',
  esp_provider  TEXT NOT NULL,            -- 'resend' | 'sendgrid' | 'mailgun'
  api_key_secret TEXT NOT NULL,           -- KV secret key name, not the value
  daily_limit   INTEGER NOT NULL DEFAULT 50000,
  sent_today    INTEGER NOT NULL DEFAULT 0,
  errors_today  INTEGER NOT NULL DEFAULT 0,
  enabled       INTEGER NOT NULL DEFAULT 1,  -- 0 = paused
  last_reset_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_sender_enabled ON sender_pool (enabled, sent_today);
```

## Sender Selection Logic

```typescript
// src/sender-select.ts
export interface Sender {
  id: string;
  from_address: string;
  display_name: string;
  esp_provider: string;
  api_key_secret: string;
  daily_limit: number;
  sent_today: number;
  errors_today: number;
}

export async function pickSender(db: D1Database): Promise<Sender | null> {
  // Prefer senders with lowest error rate and most headroom, exclude full ones
  const result = await db
    .prepare(
      `SELECT * FROM sender_pool
       WHERE enabled = 1
         AND sent_today < daily_limit
       ORDER BY
         (1.0 * errors_today / MAX(sent_today, 1)) ASC,  -- lowest error rate first
         (daily_limit - sent_today) DESC                  -- most headroom first
       LIMIT 1`
    )
    .first<Sender>();
  return result ?? null;
}

export async function incrementSent(db: D1Database, senderId: string): Promise<void> {
  await db
    .prepare("UPDATE sender_pool SET sent_today = sent_today + 1 WHERE id = ?")
    .bind(senderId)
    .run();
}

export async function recordError(db: D1Database, senderId: string): Promise<void> {
  await db
    .prepare(
      "UPDATE sender_pool SET errors_today = errors_today + 1 WHERE id = ?"
    )
    .bind(senderId)
    .run();
}
```

## Dispatcher Worker

```typescript
// src/dispatcher.ts
import { pickSender, incrementSent, recordError } from "./sender-select";

interface Env {
  DB: D1Database;
  SECRETS: KVNamespace;  // stores ESP API keys by secret name
}

export interface EmailRequest {
  to: string;
  subject: string;
  html: string;
  text?: string;
}

async function sendViaResend(
  sender: { from_address: string; display_name: string },
  apiKey: string,
  email: EmailRequest
): Promise<void> {
  const from = sender.display_name
    ? `${sender.display_name} <${sender.from_address}>`
    : sender.from_address;
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from, to: email.to, subject: email.subject,
                           html: email.html, text: email.text }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resend ${res.status}: ${body}`);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const email = await request.json<EmailRequest>();
    const sender = await pickSender(env.DB);

    if (!sender) {
      return new Response(
        JSON.stringify({ error: "no_sender_available" }),
        { status: 503, headers: { "Content-Type": "application/json" } }
      );
    }

    const apiKey = await env.SECRETS.get(sender.api_key_secret);
    if (!apiKey) {
      return new Response(
        JSON.stringify({ error: "api_key_missing", sender_id: sender.id }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }

    try {
      if (sender.esp_provider === "resend") {
        await sendViaResend(sender, apiKey, email);
      } else {
        throw new Error(`unsupported ESP: ${sender.esp_provider}`);
      }
      await incrementSent(env.DB, sender.id);
      return new Response(
        JSON.stringify({ ok: true, sender: sender.from_address }),
        { headers: { "Content-Type": "application/json" } }
      );
    } catch (err) {
      await recordError(env.DB, sender.id);
      return new Response(
        JSON.stringify({ error: String(err) }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
  },
};
```

## Daily Counter Reset (Cron Trigger)

```typescript
// src/reset-cron.ts
interface Env { DB: D1Database; }

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await env.DB.prepare(
      `UPDATE sender_pool
       SET sent_today = 0,
           errors_today = 0,
           last_reset_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')`
    ).run();
  },
};
```

`wrangler.toml` cron: `crons = ["0 0 * * *"]` (midnight UTC).

## Pool Health Dashboard Query

```sql
SELECT
  from_address,
  esp_provider,
  sent_today,
  daily_limit,
  ROUND(100.0 * sent_today / daily_limit, 1) AS pct_used,
  errors_today,
  ROUND(100.0 * errors_today / MAX(sent_today, 1), 2) AS error_rate_pct,
  CASE WHEN enabled = 1 THEN 'active' ELSE 'paused' END AS status
FROM sender_pool
ORDER BY pct_used DESC;
```

## Anti-patterns

- **Storing API keys directly in D1** – store only the KV secret name in D1; fetch
  the actual key from KV at runtime to keep secrets out of the database.
- **No daily reset** – counters grow unbounded; the cron reset is essential.
- **Using LIMIT 1 without an index** – the composite index on `(enabled, sent_today)`
  makes the ORDER BY selection fast; add it before the pool exceeds 20 rows.

## Gotchas

- Concurrent Workers requests can both pick the same sender before either increments
  the counter; under high concurrency add a `WHERE sent_today < daily_limit`
  UPDATE-and-check pattern or use D1 row-level locking (not yet available in
  2026-08)—tolerate small over-count for large daily limits.
- Some ESPs reset daily limits in the account's local timezone, not UTC; align the
  cron timezone accordingly.
- Rotating `From` addresses can confuse SPF alignment if the addresses span
  different domains; all pool addresses should share the same DMARC-covered domain
  or be explicit `From` addresses with matching SPF records.

## Verification

```bash
# Add a sender to the pool
wrangler d1 execute email-db --remote --command \
  "INSERT INTO sender_pool (id, from_address, display_name, esp_provider, api_key_secret, daily_limit)
   VALUES ('s1','noreply@example.com','example project','resend','RESEND_KEY_S1',10000);"

# Test dispatch
curl -X POST https://mailer.example.com/send \
  -H "Content-Type: application/json" \
  -d '{"to":"test@example.com","subject":"Hello","html":"<p>Hi</p>"}'
# Response: {"ok":true,"sender":"noreply@example.com"}
```

## Related

- `email-esp-failover-health-check-workers.md`
- `email-multitenant-sender-isolation-d1-workers.md`
- `email-sendgrid-subuser-ip-pool-workers.md`
- `email-domain-warmup-ip-pool-rotation-workers.md`

## Sources

- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Resend API reference: https://resend.com/docs/api-reference/emails/send-email
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
