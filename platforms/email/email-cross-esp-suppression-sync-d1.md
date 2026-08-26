# Cross-ESP Suppression List Synchronisation with D1 and Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

When you send transactional email through one ESP (e.g., Postmark) and marketing through another (e.g., SendGrid), unsubscribes and bounces recorded by one are invisible to the other, causing suppressed recipients to receive mail through the alternate channel. You need a centralised D1 suppression table that receives webhooks from all ESPs, deduplicates entries, and pushes suppressions outbound to every active ESP via their suppression APIs whenever a new address is added.

## Context

Each ESP exposes inbound webhook events for bounces, spam complaints, and unsubscribes, and a REST API for programmatic suppression management. A single Cloudflare Worker handles all inbound webhook event types, normalises them into a canonical suppression record, writes to D1, and then fans-out to the suppression APIs of every other ESP. Workers KV caches recently seen event IDs for idempotency. A separate `GET /suppressed/:email` route allows application code to do a pre-send suppression check against the central D1 store without hitting each ESP independently.

## D1 Schema

```sql
-- migrations/0001_suppressions.sql
CREATE TABLE suppressions (
  id           TEXT PRIMARY KEY,           -- UUID
  email        TEXT NOT NULL,
  reason       TEXT NOT NULL,             -- bounce | complaint | unsubscribe | manual
  source_esp   TEXT NOT NULL,             -- sendgrid | postmark | resend | ses
  raw_event    TEXT,                      -- JSON blob of original webhook payload
  created_at   TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_suppressions_email ON suppressions (email);

CREATE TABLE suppression_sync_log (
  id           TEXT PRIMARY KEY,
  email        TEXT NOT NULL,
  target_esp   TEXT NOT NULL,
  success      INTEGER NOT NULL,
  error_msg    TEXT,
  synced_at    TEXT NOT NULL
);
```

## Inbound Webhook Normalisation

```typescript
// src/normalise.ts
export type Reason = 'bounce' | 'complaint' | 'unsubscribe' | 'manual';
export interface CanonicalSuppression {
  email: string;
  reason: Reason;
  sourceEsp: string;
}

export function normaliseSendGrid(body: Record<string, unknown>[]): CanonicalSuppression[] {
  return body.flatMap((ev) => {
    const email = ev['email'] as string;
    const event = ev['event'] as string;
    if (event === 'bounce' || event === 'blocked') return [{ email, reason: 'bounce', sourceEsp: 'sendgrid' }];
    if (event === 'spamreport') return [{ email, reason: 'complaint', sourceEsp: 'sendgrid' }];
    if (event === 'unsubscribe' || event === 'group_unsubscribe') return [{ email, reason: 'unsubscribe', sourceEsp: 'sendgrid' }];
    return [];
  });
}

export function normalisePostmark(body: Record<string, unknown>): CanonicalSuppression[] {
  const type = body['Type'] as string;
  const email = (body['Email'] ?? body['Recipient']) as string;
  if (!email) return [];
  if (type === 'HardBounce' || type === 'SoftBounce') return [{ email, reason: 'bounce', sourceEsp: 'postmark' }];
  if (type === 'SpamComplaint') return [{ email, reason: 'complaint', sourceEsp: 'postmark' }];
  if (type === 'Unsubscribe') return [{ email, reason: 'unsubscribe', sourceEsp: 'postmark' }];
  return [];
}

export function normaliseResend(body: Record<string, unknown>): CanonicalSuppression[] {
  const type = body['type'] as string;
  const emailField = (body['data'] as Record<string, unknown>)?.['email'] as string ?? '';
  if (!emailField) return [];
  if (type === 'email.bounced') return [{ email: emailField, reason: 'bounce', sourceEsp: 'resend' }];
  if (type === 'email.complained') return [{ email: emailField, reason: 'complaint', sourceEsp: 'resend' }];
  return [];
}
```

## D1 Write and Fan-out to Peer ESPs

```typescript
// src/sync.ts
export interface Env {
  DB: D1Database;
  DEDUP_KV: KVNamespace;
  SENDGRID_API_KEY: string;
  POSTMARK_SERVER_TOKEN: string;
  RESEND_API_KEY: string;
}

export async function upsertSuppression(
  env: Env,
  sup: CanonicalSuppression,
  rawEvent: unknown
): Promise<boolean> {
  const normalEmail = sup.email.toLowerCase().trim();
  const existing = await env.DB.prepare(
    'SELECT id FROM suppressions WHERE email = ?'
  ).bind(normalEmail).first<{ id: string }>();
  if (existing) return false; // already suppressed globally

  await env.DB.prepare(
    `INSERT INTO suppressions (id, email, reason, source_esp, raw_event, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(), normalEmail, sup.reason, sup.sourceEsp,
    JSON.stringify(rawEvent), new Date().toISOString()
  ).run();
  return true;
}

async function pushToEsp(
  env: Env, email: string, targetEsp: string
): Promise<{ success: boolean; error?: string }> {
  try {
    if (targetEsp === 'sendgrid') {
      const res = await fetch('https://api.sendgrid.com/v3/asm/suppressions/global', {
        method: 'POST',
        headers: { Authorization: `Bearer ${env.SENDGRID_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipient_emails: [email] }),
      });
      if (!res.ok) throw new Error(`SendGrid: ${res.status} ${await res.text()}`);
    } else if (targetEsp === 'postmark') {
      const res = await fetch('https://api.postmarkapp.com/suppressions/delete', {
        method: 'POST', // Postmark uses POST for addition to suppression list
        headers: { 'X-Postmark-Server-Token': env.POSTMARK_SERVER_TOKEN, 'Content-Type': 'application/json' },
        body: JSON.stringify({ Suppressions: [{ EmailAddress: email }] }),
      });
      if (!res.ok) throw new Error(`Postmark: ${res.status} ${await res.text()}`);
    } else if (targetEsp === 'resend') {
      const res = await fetch('https://api.resend.com/contacts', {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, unsubscribed: true }),
      });
      if (!res.ok) throw new Error(`Resend: ${res.status} ${await res.text()}`);
    }
    return { success: true };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

export async function fanOutSuppression(
  env: Env,
  email: string,
  sourceEsp: string
): Promise<void> {
  const peers = ['sendgrid', 'postmark', 'resend'].filter((e) => e !== sourceEsp);
  await Promise.all(
    peers.map(async (targetEsp) => {
      const result = await pushToEsp(env, email, targetEsp);
      await env.DB.prepare(
        `INSERT INTO suppression_sync_log (id, email, target_esp, success, error_msg, synced_at)
         VALUES (?, ?, ?, ?, ?, ?)`
      ).bind(
        crypto.randomUUID(), email, targetEsp,
        result.success ? 1 : 0, result.error ?? null, new Date().toISOString()
      ).run();
    })
  );
}
```

## Worker Fetch Handler

```typescript
// src/worker.ts
import { normaliseSendGrid, normalisePostmark, normaliseResend } from './normalise';
import { upsertSuppression, fanOutSuppression, type Env } from './sync';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'GET' && url.pathname.startsWith('/suppressed/')) {
      const email = decodeURIComponent(url.pathname.slice('/suppressed/'.length)).toLowerCase();
      const row = await env.DB.prepare('SELECT reason FROM suppressions WHERE email = ?')
        .bind(email).first<{ reason: string }>();
      return Response.json({ suppressed: !!row, reason: row?.reason ?? null });
    }

    if (request.method === 'POST') {
      const body = await request.json<Record<string, unknown> | Record<string, unknown>[]>();
      let suppressions: CanonicalSuppression[] = [];

      if (url.pathname === '/webhooks/sendgrid') {
        suppressions = normaliseSendGrid(Array.isArray(body) ? body : [body]);
      } else if (url.pathname === '/webhooks/postmark') {
        suppressions = normalisePostmark(body as Record<string, unknown>);
      } else if (url.pathname === '/webhooks/resend') {
        suppressions = normaliseResend(body as Record<string, unknown>);
      } else {
        return new Response('Not found', { status: 404 });
      }

      for (const sup of suppressions) {
        const isNew = await upsertSuppression(env, sup, body);
        if (isNew) await fanOutSuppression(env, sup.email.toLowerCase(), sup.sourceEsp);
      }
      return Response.json({ ok: true, processed: suppressions.length });
    }

    return new Response('Method not allowed', { status: 405 });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Storing suppressions in each ESP's native list only — a new ESP added to the stack starts with an empty suppression list and will send to previously suppressed addresses.
- Blocking the inbound webhook response until fan-out completes — ESP webhooks expect a fast 2xx; move fan-out to a Cloudflare Queue if latency is a concern.
- Normalising email addresses without lowercasing — `User@Example.com` and `user@example.com` will create duplicate rows and duplicate suppression pushes.

## Gotchas

- Postmark's suppression endpoint path and HTTP method differ by message stream type (transactional vs. broadcast) — check the API docs for the stream you're using.
- SendGrid's global suppression list is separate from group-level unsubscribes; push to the global list to ensure all future sends are blocked, not just the unsubscribed group.

## Verification

```bash
# Simulate a SendGrid bounce webhook
curl -X POST https://suppression.example.com/webhooks/sendgrid \
  -H 'Content-Type: application/json' \
  -d '[{"email":"bounced@example.com","event":"bounce","type":"permanent"}]'

# Verify central D1 record was created
wrangler d1 execute EMAIL_DB \
  --command "SELECT email, reason, source_esp FROM suppressions WHERE email='bounced@example.com'"

# Check suppression via pre-send lookup
curl https://suppression.example.com/suppressed/bounced%40example.com
# Expect: {"suppressed":true,"reason":"bounce"}
```

## Related

- `email/suppression-list-management.md`
- `email/bounce-suppression-d1.md`
- `email/bounce-handling-hard-soft.md`
- `email/email-esp-failover-health-check-workers.md`

## Sources

- https://docs.sendgrid.com/api-reference/suppressions-global-suppressions
- https://postmarkapp.com/developer/api/suppressions-api
- https://resend.com/docs/api-reference/contacts/update-contact
- https://developers.cloudflare.com/d1/get-started/
