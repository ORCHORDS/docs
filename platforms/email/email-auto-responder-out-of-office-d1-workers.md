# Out-of-Office Auto-Responder with D1 and Email Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Users need an automated out-of-office reply sent when inbound email arrives during a defined absence window. The same sender must not receive duplicate replies within 24 hours, and OOO schedules must be manageable via an API without redeployment.

## Context

An Email Worker checks D1 `ooo_schedules` for each inbound message recipient. If the current UTC time falls within the user's schedule (accounting for their timezone), a reply is sent via MailChannels with the `Auto-Submitted: auto-replied` header. A KV key per `(recipient, sender)` pair enforces the 24-hour rate limit. An admin API Worker exposes CRUD endpoints for schedule management.

Requirements:
- Email Worker + Admin API Worker
- D1 database bound as `DB`
- KV namespace bound as `OOO_RATE_KV`
- MailChannels send permission

## D1 Schema

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS ooo_schedules (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  email      TEXT    NOT NULL UNIQUE,
  start_date TEXT    NOT NULL,  -- ISO 8601 date: '2026-09-01'
  end_date   TEXT    NOT NULL,  -- ISO 8601 date: '2026-09-15'
  message    TEXT    NOT NULL,
  timezone   TEXT    NOT NULL DEFAULT 'UTC'
);
CREATE INDEX IF NOT EXISTS idx_ooo_email ON ooo_schedules(email);
```

## Email Worker — OOO Check and Auto-Reply

```typescript
import type { EmailMessage } from 'cloudflare:email';

export interface Env {
  DB: D1Database;
  OOO_RATE_KV: KVNamespace;
}

const RATE_LIMIT_TTL_SECONDS = 86400; // 24 hours

export default {
  async email(message: EmailMessage, env: Env): Promise<void> {
    const recipient = message.to;
    const sender = message.from;

    // Skip automated messages to avoid reply loops
    const autoSubmitted = message.headers.get('Auto-Submitted');
    if (autoSubmitted && autoSubmitted !== 'no') {
      await message.forward(recipient);
      return;
    }

    // Look up OOO schedule for recipient
    const schedule = await env.DB.prepare(
      `SELECT message, start_date, end_date, timezone
       FROM ooo_schedules WHERE email = ? LIMIT 1`
    ).bind(recipient).first<{ message: string; start_date: string; end_date: string; timezone: string }>();

    if (!schedule) {
      // No OOO configured — forward normally
      await message.forward(recipient);
      return;
    }

    const nowUtc = new Date();
    const start = new Date(`${schedule.start_date}T00:00:00Z`);
    const end = new Date(`${schedule.end_date}T23:59:59Z`);

    if (nowUtc < start || nowUtc > end) {
      // Outside the OOO window
      await message.forward(recipient);
      return;
    }

    // Enforce 24-hour rate limit per (recipient, sender) pair
    const rateLimitKey = `ooo:${recipient}:${sender}`;
    const alreadySent = await env.OOO_RATE_KV.get(rateLimitKey);

    if (!alreadySent) {
      await sendAutoReply(sender, recipient, schedule.message);
      await env.OOO_RATE_KV.put(rateLimitKey, '1', { expirationTtl: RATE_LIMIT_TTL_SECONDS });
    }

    // Always forward the original message to the user's mailbox
    await message.forward(recipient);
  },
};

async function sendAutoReply(to: string, from: string, oooMessage: string): Promise<void> {
  await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: from },
      subject: 'Out of Office',
      content: [{ type: 'text/plain', value: oooMessage }],
      headers: { 'Auto-Submitted': 'auto-replied' },
    }),
  });
}
```

## Admin API Worker — CRUD for Schedules

```typescript
// admin-api/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const email = url.searchParams.get('email');

    if (request.method === 'GET' && url.pathname === '/ooo') {
      const row = await env.DB.prepare(
        `SELECT * FROM ooo_schedules WHERE email = ?`
      ).bind(email).first();
      return Response.json(row ?? { error: 'not found' }, { status: row ? 200 : 404 });
    }

    if (request.method === 'PUT' && url.pathname === '/ooo') {
      const body = await request.json<{ start_date: string; end_date: string; message: string; timezone: string }>();
      await env.DB.prepare(
        `INSERT INTO ooo_schedules (email, start_date, end_date, message, timezone)
         VALUES (?, ?, ?, ?, ?)
         ON CONFLICT(email) DO UPDATE SET
           start_date = excluded.start_date,
           end_date   = excluded.end_date,
           message    = excluded.message,
           timezone   = excluded.timezone`
      ).bind(email, body.start_date, body.end_date, body.message, body.timezone ?? 'UTC').run();
      return new Response('OK', { status: 200 });
    }

    if (request.method === 'DELETE' && url.pathname === '/ooo') {
      await env.DB.prepare(`DELETE FROM ooo_schedules WHERE email = ?`).bind(email).run();
      return new Response('Deleted', { status: 200 });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Anti-patterns

- Do not reply to messages where `Auto-Submitted` is set — this causes infinite reply loops with other auto-responders.
- Do not store rate-limit state in D1 when KV TTL is available; D1 does not natively expire rows.
- Do not use local time comparison without timezone conversion; always normalize to UTC for comparisons.
- Do not skip forwarding the original message — the user still needs to receive their mail.

## Gotchas

- MailChannels `from` must be a verified sending domain; using the recipient's address as `from` requires domain verification.
- KV `expirationTtl` is in seconds and has a minimum of 60; it is not a hard guarantee of exactly 24h.
- Email Workers run on the Cloudflare edge; `new Date()` returns the current UTC time, not the user's local time.
- The `ON CONFLICT` upsert requires the `email` column to have a `UNIQUE` constraint (included in the schema above).

## Verification

```bash
# Insert a test schedule via the admin API
curl -X PUT 'https://admin-api.yourdomain.com/ooo?email=user@yourdomain.com' \
  -H 'Content-Type: application/json' \
  -d '{"start_date":"2026-08-24","end_date":"2026-08-31","message":"I am OOO.","timezone":"UTC"}'

# Confirm the schedule is stored in D1
wrangler d1 execute ooo-db --command "SELECT * FROM ooo_schedules;"

# Send a test email to the configured address and observe wrangler tail
wrangler tail ooo-worker --format pretty

# Confirm rate-limit key is present in KV after first auto-reply
wrangler kv key list --namespace-id <your-kv-id>
```

## Related

- `email-digest-batching-queues-d1-workers.md`
- `email-alias-routing-kv-workers.md`
- [Cloudflare Email Workers docs](https://developers.cloudflare.com/email-routing/email-workers/)

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://api.mailchannels.net/tx/v1/documentation
