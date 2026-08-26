# RFC 8058 One-Click Unsubscribe with Workers and MailChannels

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Bulk senders that omit `List-Unsubscribe` headers face deliverability penalties from Gmail and Yahoo as of 2024. Implementing RFC 8058 one-click unsubscribe requires both the correct headers on outbound mail and a Worker endpoint that processes the POST request and immediately honours it.

---

## Context

RFC 8058 extends the older `List-Unsubscribe` header by adding a `List-Unsubscribe-Post` header with the value `List-Unsubscribe=One-Click`. When an email client (or mail provider acting on behalf of the recipient) POSTs `List-Unsubscribe=One-Click` to the URL in the header, the sending system must immediately suppress that address. A signed token embedded in the unsubscribe URL prevents CSRF: an HMAC-SHA256 signature over `{email}:{listId}:{timestamp}` is verified before any database write. Preferences are stored in a D1 `email_preferences` table; the suppression is checked before every MailChannels send.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "email-unsubscribe-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
UNSUBSCRIBE_BASE_URL = "https://unsubscribe.yourdomain.com"
UNSUBSCRIBE_TOKEN_TTL_SECONDS = "2592000"   # 30 days

[secrets]
# wrangler secret put UNSUB_HMAC_SECRET
UNSUB_HMAC_SECRET = ""

[[d1_databases]]
binding = "DB"
database_name = "email-db"
database_id = "YOUR_D1_DATABASE_ID"
```

```sql
CREATE TABLE IF NOT EXISTS email_preferences (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  email        TEXT    NOT NULL,
  list_id      TEXT    NOT NULL DEFAULT 'default',
  unsubscribed INTEGER NOT NULL DEFAULT 0,
  updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (email, list_id)
);

CREATE INDEX idx_prefs_email ON email_preferences(email);
```

## Section 2 — Worker implementation (send + header generation)

```typescript
export interface Env {
  DB: D1Database;
  UNSUB_HMAC_SECRET: string;
  UNSUBSCRIBE_BASE_URL: string;
  UNSUBSCRIBE_TOKEN_TTL_SECONDS: string;
}

async function sign(secret: string, data: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

async function verify(secret: string, data: string, token: string): Promise<boolean> {
  const expected = await sign(secret, data);
  return expected === token;
}

export function buildUnsubscribeUrl(
  env: Env,
  email: string,
  listId: string,
  timestamp: number
): Promise<string> {
  const data = `${email}:${listId}:${timestamp}`;
  return sign(env.UNSUB_HMAC_SECRET, data).then(
    (sig) =>
      `${env.UNSUBSCRIBE_BASE_URL}/unsubscribe?email=${encodeURIComponent(email)}` +
      `&list=${encodeURIComponent(listId)}&ts=${timestamp}&sig=${sig}`
  );
}

export async function sendWithUnsubscribeHeaders(
  env: Env,
  to: string,
  subject: string,
  htmlBody: string,
  textBody: string,
  listId = 'default'
): Promise<Response> {
  // Suppression check
  const pref = await env.DB.prepare(
    'SELECT unsubscribed FROM email_preferences WHERE email = ? AND list_id = ?'
  )
    .bind(to, listId)
    .first<{ unsubscribed: number }>();

  if (pref?.unsubscribed === 1) {
    console.log(`Suppressed send to ${to} (list: ${listId})`);
    return new Response('suppressed', { status: 200 });
  }

  const ts = Math.floor(Date.now() / 1000);
  const unsubUrl = await buildUnsubscribeUrl(env, to, listId, ts);

  const payload = {
    personalizations: [{ to: [{ email: to }] }],
    from: { email: 'noreply@yourdomain.com', name: 'Orchords' },
    subject,
    content: [
      { type: 'text/plain', value: textBody },
      { type: 'text/html', value: htmlBody },
    ],
    headers: {
      'List-Unsubscribe': `<${unsubUrl}>`,
      'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
    },
  };

  return fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
```

## Section 3 — Unsubscribe endpoint (POST handler)

```typescript
export async function handleUnsubscribePost(
  request: Request,
  env: Env
): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  const url = new URL(request.url);
  const email = url.searchParams.get('email');
  const listId = url.searchParams.get('list') ?? 'default';
  const ts = parseInt(url.searchParams.get('ts') ?? '0', 10);
  const sig = url.searchParams.get('sig');

  if (!email || !sig || !ts) {
    return new Response('Bad Request', { status: 400 });
  }

  // Validate token age
  const ttl = parseInt(env.UNSUBSCRIBE_TOKEN_TTL_SECONDS, 10);
  const now = Math.floor(Date.now() / 1000);
  if (now - ts > ttl) {
    return new Response('Token expired', { status: 410 });
  }

  // Verify HMAC signature
  const data = `${email}:${listId}:${ts}`;
  const valid = await verify(env.UNSUB_HMAC_SECRET, data, sig);
  if (!valid) {
    return new Response('Forbidden', { status: 403 });
  }

  // RFC 8058 body check: must contain List-Unsubscribe=One-Click
  const body = await request.text();
  if (!body.includes('List-Unsubscribe=One-Click')) {
    return new Response('Bad Request', { status: 400 });
  }

  await env.DB.prepare(
    `INSERT INTO email_preferences (email, list_id, unsubscribed, updated_at)
     VALUES (?, ?, 1, datetime('now'))
     ON CONFLICT(email, list_id) DO UPDATE
       SET unsubscribed = 1, updated_at = excluded.updated_at`
  )
    .bind(email, listId)
    .run();

  console.log(`Unsubscribed ${email} from list ${listId}`);
  return new Response('OK', { status: 200 });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (pathname === '/unsubscribe') return handleUnsubscribePost(request, env);
    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Anti-patterns

- **Unsubscribe link in body only** — A clickable link in the email body is not RFC 8058 compliance. Mail providers look for the `List-Unsubscribe` header and POST to it automatically; body links are a separate UX concern.
- **Unsigned unsubscribe URLs** — Without an HMAC token, any party who guesses the URL structure can unsubscribe arbitrary addresses. Always verify the signature before writing to D1.
- **Redirect to a preference page instead of returning 200** — RFC 8058 POST handlers must return `2xx` to the HTTP client, not a redirect. Redirects will confuse automated mail-provider bots.
- **Skipping the suppression check in the send path** — Recording the unsubscribe in D1 is meaningless if the send function does not read it before dispatching.

---

## Gotchas

- Gmail and Yahoo require the `List-Unsubscribe-Post` header to be present alongside `List-Unsubscribe`; either header alone is insufficient for one-click compliance.
- The HMAC secret must be stored as a Wrangler secret (`wrangler secret put UNSUB_HMAC_SECRET`), not as a plain `[vars]` entry.
- Token TTL of 30 days is a reasonable balance; shorter values cause expired tokens for slower inbox processors, longer values widen the CSRF window.
- D1 `ON CONFLICT ... DO UPDATE` requires SQLite 3.24+, which D1 supports as of the current compatibility date.
- MailChannels drops custom headers that conflict with RFC 5322 reserved names; `List-Unsubscribe` is permitted as it is a standard list-management header.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Trigger a test send and capture the List-Unsubscribe header value
curl -s -X POST https://your-worker.workers.dev/send \
     -H 'Content-Type: application/json' \
     -d '{"to":"test@example.com","subject":"Hello","text":"Hi"}' \
  | jq .

# Simulate a one-click unsubscribe POST (replace URL with the one from the header)
curl -s -X POST \
  'https://unsubscribe.yourdomain.com/unsubscribe?email=test%40example.com&list=default&ts=1724500000&sig=<SIG>' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'List-Unsubscribe=One-Click'

# Verify D1 row
npx wrangler d1 execute email-db \
  --command "SELECT * FROM email_preferences WHERE email = 'test@example.com';"
```

---

## Related

- `email-rate-limiting-kv-mailchannels-workers.md`
- `email-bounce-webhook-mailchannels-d1.md`

---

## Sources

- RFC 8058 One-Click Unsubscribe — https://www.rfc-editor.org/rfc/rfc8058
- Google Bulk Sender Requirements — https://support.google.com/mail/answer/81126
- MailChannels Send API — https://docs.mailchannels.net/transactional-email/send-email
- Cloudflare D1 — https://developers.cloudflare.com/d1/
