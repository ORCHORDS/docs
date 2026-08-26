# Email List Management with D1 in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need a self-hosted email subscription system backed by Cloudflare D1 with a double opt-in flow to remain GDPR-compliant. Subscribers must confirm their email via a signed token before being activated, and you need a clean export endpoint for sending campaigns.

---

## Context
Cloudflare Workers can serve as a lightweight email list management backend when combined with D1 (SQLite at the edge) and KV for ephemeral token storage. The double opt-in pattern requires generating a time-limited signed token on subscribe, emailing a confirmation link, and only activating the subscriber on `GET /confirm`. MailChannels is the standard transactional delivery layer available natively inside Workers. KV TTL handles token expiry without a cron cleanup job.

---

## Section 1 — D1 Schema & KV Namespace

```sql
-- migrations/0001_subscribers.sql
CREATE TABLE IF NOT EXISTS subscribers (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  email       TEXT NOT NULL UNIQUE,
  status      TEXT NOT NULL DEFAULT 'pending',   -- pending | active | unsubscribed
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  confirmed_at INTEGER,
  unsubscribed_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_subscribers_email  ON subscribers(email);
CREATE INDEX IF NOT EXISTS idx_subscribers_status ON subscribers(status);
```

```toml
# wrangler.toml
name = "email-list"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding     = "DB"
database_name = "email-list-db"
database_id   = "<your-d1-database-id>"

[[kv_namespaces]]
binding   = "TOKENS"
id        = "<your-kv-namespace-id>"

[vars]
FROM_EMAIL = "noreply@example.com"
BASE_URL   = "https://email-list.example.com"
```

---

## Section 2 — Implementation

```typescript
// src/index.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  TOKENS: KVNamespace;
  FROM_EMAIL: string;
  BASE_URL: string;
}

const app = new Hono<{ Bindings: Env }>();

// ── Helpers ──────────────────────────────────────────────────────────────────

async function generateToken(env: Env, email: string, action: 'confirm' | 'unsub'): Promise<string> {
  const raw = crypto.getRandomValues(new Uint8Array(24));
  const token = btoa(String.fromCharCode(...raw))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  const key = `${action}:${token}`;
  const ttl = action === 'confirm' ? 60 * 60 * 24 * 7 : 60 * 60 * 24 * 30; // 7d / 30d
  await env.TOKENS.put(key, email, { expirationTtl: ttl });
  return token;
}

async function sendEmail(
  env: Env,
  to: string,
  subject: string,
  html: string
): Promise<void> {
  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: env.FROM_EMAIL },
      subject,
      content: [{ type: 'text/html', value: html }],
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`MailChannels error ${res.status}: ${body}`);
  }
}

// ── Routes ───────────────────────────────────────────────────────────────────

/** POST /subscribe  body: { email: string } */
app.post('/subscribe', async (c) => {
  const { email } = await c.req.json<{ email: string }>();
  if (!email || !/^[^@]+@[^@]+\.[^@]+$/.test(email)) {
    return c.json({ error: 'Invalid email' }, 400);
  }

  const lower = email.toLowerCase().trim();

  await c.env.DB
    .prepare(
      `INSERT INTO subscribers (email) VALUES (?)
       ON CONFLICT(email) DO UPDATE SET
         status = CASE WHEN excluded.status = 'unsubscribed' THEN 'pending' ELSE status END`
    )
    .bind(lower)
    .run();

  const token = await generateToken(c.env, lower, 'confirm');
  const link  = `${c.env.BASE_URL}/confirm?token=${token}`;

  await sendEmail(
    c.env,
    lower,
    'Confirm your subscription',
    `<p>Click <a >here</a> to confirm your subscription. Link expires in 7 days.</p>`
  );

  return c.json({ ok: true, message: 'Confirmation email sent' });
});

/** GET /confirm?token= */
app.get('/confirm', async (c) => {
  const token = c.req.query('token');
  if (!token) return c.json({ error: 'Missing token' }, 400);

  const email = await c.env.TOKENS.get(`confirm:${token}`);
  if (!email) return c.json({ error: 'Token expired or invalid' }, 410);

  await c.env.DB
    .prepare(
      `UPDATE subscribers SET status = 'active', confirmed_at = unixepoch()
       WHERE email = ? AND status = 'pending'`
    )
    .bind(email)
    .run();

  await c.env.TOKENS.delete(`confirm:${token}`);
  return c.json({ ok: true, email });
});

/** GET /unsubscribe?token= */
app.get('/unsubscribe', async (c) => {
  const token = c.req.query('token');
  if (!token) return c.json({ error: 'Missing token' }, 400);

  const email = await c.env.TOKENS.get(`unsub:${token}`);
  if (!email) return c.json({ error: 'Token expired or invalid' }, 410);

  await c.env.DB
    .prepare(
      `UPDATE subscribers SET status = 'unsubscribed', unsubscribed_at = unixepoch()
       WHERE email = ? AND status = 'active'`
    )
    .bind(email)
    .run();

  await c.env.TOKENS.delete(`unsub:${token}`);
  return c.json({ ok: true, message: 'Unsubscribed' });
});

/** GET /export — returns active subscriber list (internal use) */
app.get('/export', async (c) => {
  const auth = c.req.header('X-Export-Secret');
  if (auth !== c.env.EXPORT_SECRET) return c.json({ error: 'Forbidden' }, 403);

  const { results } = await c.env.DB
    .prepare(`SELECT email, created_at, confirmed_at FROM subscribers WHERE status = 'active' ORDER BY confirmed_at`)
    .all<{ email: string; created_at: number; confirmed_at: number }>();

  return c.json({ count: results.length, subscribers: results });
});

export default app;
```

---

## Section 3 — Integration Testing

```typescript
// test/subscribe.test.ts  (Vitest + @cloudflare/vitest-pool-workers)
import { SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';

describe('subscribe flow', () => {
  it('POST /subscribe returns 200 for valid email', async () => {
    const res = await SELF.fetch('http://localhost/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'test@example.com' }),
    });
    expect(res.status).toBe(200);
    const body = await res.json<{ ok: boolean }>();
    expect(body.ok).toBe(true);
  });

  it('POST /subscribe returns 400 for invalid email', async () => {
    const res = await SELF.fetch('http://localhost/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'not-an-email' }),
    });
    expect(res.status).toBe(400);
  });

  it('GET /confirm returns 410 for unknown token', async () => {
    const res = await SELF.fetch('http://localhost/confirm?token=invalid');
    expect(res.status).toBe(410);
  });
});
```

---

## Anti-patterns
- **Single opt-in** — Activating subscribers immediately on `POST /subscribe` without email verification leads to list poisoning and violates GDPR consent requirements.
- **Storing tokens in D1** — Using D1 rows for short-lived tokens requires a cleanup job; KV TTL handles expiry automatically without extra load.
- **Plaintext token** — Deriving the token from `email + secret` via HMAC without storing it in KV makes revocation impossible before TTL expiry.
- **No deduplication on re-subscribe** — Failing to handle the `ON CONFLICT` case causes duplicate-key errors when a previously unsubscribed user tries to re-subscribe.

---

## Gotchas
- MailChannels `POST /tx/v1/send` is available free inside Workers but requires SPF/DKIM records on your sending domain; without them, deliverability will be poor.
- D1 `unixepoch()` returns seconds, not milliseconds; compare consistently when surfacing dates to a JavaScript `Date` constructor (multiply by 1000).
- KV `expirationTtl` minimum is 60 seconds; tokens shorter than that will be rejected at write time.
- The `ON CONFLICT` upsert only resets `status` when the existing row has `unsubscribed` status — intentionally leaves `pending` rows untouched to avoid token-flooding attacks.

---

## Verification

```bash
# Apply migration
npx wrangler d1 execute email-list-db --file=migrations/0001_subscribers.sql

# Subscribe
curl -X POST https://email-list.example.com/subscribe \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com"}'

# Confirm (replace TOKEN with value from email)
curl 'https://email-list.example.com/confirm?token=TOKEN'

# Check subscriber in D1
npx wrangler d1 execute email-list-db \
  --command "SELECT * FROM subscribers WHERE email = 'you@example.com'"

# Export active list
curl -H 'X-Export-Secret: <secret>' https://email-list.example.com/export
```

---

## Related
- `workers-transactional-email-d1-audit.md`
- `workers-email-open-tracking-pixel.md`

---

## Sources
- Cloudflare D1 Docs — https://developers.cloudflare.com/d1/
- Cloudflare KV TTL — https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- MailChannels Workers Integration — https://support.mailchannels.com/hc/en-us/articles/4565898358413
