# One-Click Unsubscribe (RFC 8058) in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Gmail and Yahoo Mail now require bulk senders to support one-click unsubscribe (RFC 8058) or risk deliverability degradation. Your current unsubscribe flow requires recipients to click a link, log in, and navigate a preferences page — a multi-step process that increases spam complaints. You need to implement `List-Unsubscribe` and `List-Unsubscribe-Post` headers, a POST handler that processes one-click unsubscribes, signed tokens to prevent unauthorized removal of arbitrary addresses, a D1 suppression list, a re-subscribe flow, and a CAN-SPAM-compliant export endpoint.

---

## Context

RFC 8058 defines `List-Unsubscribe-Post` with the body `List-Unsubscribe=One-Click` to signal that a POST to the unsubscribe URL should immediately remove the recipient with no additional confirmation page. Mail clients (Gmail, Apple Mail, Yahoo) display a native "Unsubscribe" button when this header pair is detected. Signed tokens using HMAC-SHA256 ensure that only the original recipient (or the mail client acting on their behalf) can trigger an unsubscribe for a given email address.

Prerequisites:
- D1 database bound as `DB`
- Workers secret `UNSUB_SECRET` for HMAC signing
- `BASE_URL` environment variable for constructing unsubscribe URLs

---

## Solution

```typescript
// wrangler.toml (excerpt)
// [vars]
// BASE_URL = "https://email.example.com"
//
// [[d1_databases]]
// binding = "DB"
// database_name = "email-db"
// database_id = "<your-d1-id>"

export interface Env {
  DB: D1Database;
  UNSUB_SECRET: string;
  BASE_URL: string;
}

// ── D1 schema ─────────────────────────────────────────────────────────────────
// CREATE TABLE IF NOT EXISTS unsubscribes (
//   email         TEXT NOT NULL,
//   list_id       TEXT NOT NULL DEFAULT 'global',
//   unsubscribed_at TEXT NOT NULL,
//   method        TEXT NOT NULL,  -- 'one-click' | 'link' | 'manual' | 'bounce'
//   resubscribed_at TEXT,
//   PRIMARY KEY (email, list_id)
// );
// CREATE TABLE IF NOT EXISTS unsubscribe_audit (
//   id        TEXT PRIMARY KEY,
//   email     TEXT NOT NULL,
//   list_id   TEXT NOT NULL,
//   action    TEXT NOT NULL,   -- 'unsubscribe' | 'resubscribe'
//   method    TEXT NOT NULL,
//   ip_hash   TEXT,
//   created_at TEXT NOT NULL
// );

// ── HMAC helpers ──────────────────────────────────────────────────────────────
async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify']
  );
}

async function makeToken(
  key: CryptoKey,
  email: string,
  listId: string,
  action: 'unsub' | 'resub'
): Promise<string> {
  const payload = `${action}:${listId}:${email}`;
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  const b64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
  // Token = base64url(email):base64url(listId):action:sig
  const eb64 = btoa(email).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  const lb64 = btoa(listId).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  return `${eb64}.${lb64}.${action}.${b64}`;
}

async function verifyToken(
  key: CryptoKey,
  token: string
): Promise<{ email: string; listId: string; action: string } | null> {
  const parts = token.split('.');
  if (parts.length !== 4) return null;
  const [eb64, lb64, action, sigB64] = parts;

  let email: string;
  let listId: string;
  try {
    email = atob(eb64.replace(/-/g, '+').replace(/_/g, '/'));
    listId = atob(lb64.replace(/-/g, '+').replace(/_/g, '/'));
  } catch {
    return null;
  }

  const payload = `${action}:${listId}:${email}`;
  const normalised = sigB64.replace(/-/g, '+').replace(/_/g, '/');
  const sigBytes = Uint8Array.from(atob(normalised), (c) => c.charCodeAt(0));

  const valid = await crypto.subtle.verify(
    'HMAC',
    key,
    sigBytes,
    new TextEncoder().encode(payload)
  );
  if (!valid) return null;

  return { email, listId, action };
}

// ── Header generation (call before sending each email) ───────────────────────
export async function buildUnsubscribeHeaders(
  env: Env,
  email: string,
  listId = 'global'
): Promise<Record<string, string>> {
  const key = await hmacKey(env.UNSUB_SECRET);
  const token = await makeToken(key, email, listId, 'unsub');
  const unsubUrl = `${env.BASE_URL}/unsubscribe/${token}`;
  return {
    // RFC 2369 — traditional mailto + HTTP URL pair
    'List-Unsubscribe': `<mailto:unsub@example.com?subject=unsub>, <${unsubUrl}>`,
    // RFC 8058 — signals one-click POST support to mail clients
    'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
  };
}

// ── Suppression check (call before every send) ───────────────────────────────
export async function isSuppressed(
  db: D1Database,
  email: string,
  listId = 'global'
): Promise<boolean> {
  const { results } = await db
    .prepare(
      `SELECT 1 FROM unsubscribes
       WHERE email = ? AND (list_id = ? OR list_id = 'global')
         AND resubscribed_at IS NULL
       LIMIT 1`
    )
    .bind(email.toLowerCase(), listId)
    .all();
  return results.length > 0;
}

// ── Core unsubscribe / resubscribe logic ──────────────────────────────────────
async function recordUnsubscribe(
  db: D1Database,
  email: string,
  listId: string,
  method: string,
  ipHash: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.batch([
    db
      .prepare(
        `INSERT INTO unsubscribes (email, list_id, unsubscribed_at, method)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(email, list_id) DO UPDATE
           SET unsubscribed_at = excluded.unsubscribed_at,
               method = excluded.method,
               resubscribed_at = NULL`
      )
      .bind(email.toLowerCase(), listId, now, method),
    db
      .prepare(
        `INSERT INTO unsubscribe_audit (id, email, list_id, action, method, ip_hash, created_at)
         VALUES (?, ?, ?, 'unsubscribe', ?, ?, ?)`
      )
      .bind(crypto.randomUUID(), email.toLowerCase(), listId, method, ipHash, now),
  ]);
}

async function recordResubscribe(
  db: D1Database,
  email: string,
  listId: string,
  ipHash: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.batch([
    db
      .prepare(
        `UPDATE unsubscribes SET resubscribed_at = ? WHERE email = ? AND list_id = ?`
      )
      .bind(now, email.toLowerCase(), listId),
    db
      .prepare(
        `INSERT INTO unsubscribe_audit (id, email, list_id, action, method, ip_hash, created_at)
         VALUES (?, ?, ?, 'resubscribe', 'link', ?, ?)`
      )
      .bind(crypto.randomUUID(), email.toLowerCase(), listId, ipHash, now),
  ]);
}

async function hashIp(ip: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(ip));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
}

// ── Worker fetch handler ──────────────────────────────────────────────────────
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const ip = request.headers.get('cf-connecting-ip') ?? '';
    const ipHash = await hashIp(ip);
    const key = await hmacKey(env.UNSUB_SECRET);

    // ── POST /unsubscribe/:token — RFC 8058 one-click ─────────────────────────
    // Gmail sends: POST /unsubscribe/<token>  body: List-Unsubscribe=One-Click
    const postMatch = url.pathname.match(/^\/unsubscribe\/([A-Za-z0-9._-]+)$/);
    if (postMatch && request.method === 'POST') {
      const token = postMatch[1];
      const parsed = await verifyToken(key, token);
      if (!parsed || parsed.action !== 'unsub') {
        return new Response('Invalid or expired token', { status: 403 });
      }
      // Validate RFC 8058 body (optional but recommended)
      const body = await request.text();
      if (!body.includes('List-Unsubscribe=One-Click')) {
        return new Response('Invalid one-click payload', { status: 400 });
      }
      await recordUnsubscribe(env.DB, parsed.email, parsed.listId, 'one-click', ipHash);
      return new Response(null, { status: 204 });
    }

    // ── GET /unsubscribe/:token — traditional link click ──────────────────────
    if (postMatch && request.method === 'GET') {
      const token = postMatch[1];
      const parsed = await verifyToken(key, token);
      if (!parsed || parsed.action !== 'unsub') {
        return new Response('Invalid or expired token', { status: 403 });
      }
      await recordUnsubscribe(env.DB, parsed.email, parsed.listId, 'link', ipHash);
      // Generate a re-subscribe token and present a simple confirmation page
      const resubToken = await makeToken(key, parsed.email, parsed.listId, 'resub');
      const resubUrl = `${env.BASE_URL}/resubscribe/${resubToken}`;
      return new Response(
        `<!doctype html><html><body>
<p>You have been unsubscribed from <strong>${parsed.listId}</strong> mailings.</p>
<p>Changed your mind? <a >Re-subscribe</a></p>
</body></html>`,
        { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
      );
    }

    // ── GET /resubscribe/:token ───────────────────────────────────────────────
    const resubMatch = url.pathname.match(/^\/resubscribe\/([A-Za-z0-9._-]+)$/);
    if (resubMatch && request.method === 'GET') {
      const token = resubMatch[1];
      const parsed = await verifyToken(key, token);
      if (!parsed || parsed.action !== 'resub') {
        return new Response('Invalid token', { status: 403 });
      }
      await recordResubscribe(env.DB, parsed.email, parsed.listId, ipHash);
      return new Response(
        `<!doctype html><html><body><p>You have been re-subscribed to <strong>${parsed.listId}</strong> mailings.</p></body></html>`,
        { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
      );
    }

    // ── GET /suppression-list?list_id=global — CAN-SPAM export ───────────────
    if (url.pathname === '/suppression-list' && request.method === 'GET') {
      const listId = url.searchParams.get('list_id') ?? 'global';
      // Require internal auth (e.g. shared secret header)
      if (request.headers.get('x-internal-key') !== env.UNSUB_SECRET) {
        return new Response('Unauthorized', { status: 401 });
      }
      const { results } = await env.DB
        .prepare(
          `SELECT email, list_id, unsubscribed_at, method
           FROM unsubscribes
           WHERE (list_id = ? OR list_id = 'global') AND resubscribed_at IS NULL
           ORDER BY unsubscribed_at DESC`
        )
        .bind(listId)
        .all<{ email: string; list_id: string; unsubscribed_at: string; method: string }>();
      const csv = [
        'email,list_id,unsubscribed_at,method',
        ...results.map((r) => `${r.email},${r.list_id},${r.unsubscribed_at},${r.method}`),
      ].join('\n');
      return new Response(csv, {
        headers: {
          'Content-Type': 'text/csv',
          'Content-Disposition': `attachment; filename="suppression-${listId}.csv"`,
        },
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Implementation Details

- **Token structure**: `base64url(email).base64url(listId).action.hmac-sig`. This is URL-safe without percent-encoding and self-contained — no database lookup is needed to validate the token, only HMAC verification.
- **RFC 8058 compliance**: the `List-Unsubscribe-Post: List-Unsubscribe=One-Click` header must appear alongside `List-Unsubscribe` with an HTTPS URL. The POST handler must respond with 2xx and unsubscribe without presenting a confirmation page.
- **Global vs. list-scoped suppression**: storing `list_id = 'global'` suppresses the recipient from all mailings. List-specific unsubscribes (`list_id = 'newsletter'`) only block that list. The `isSuppressed` function checks both.
- **Audit trail**: `unsubscribe_audit` preserves every action with IP hash and method, satisfying CAN-SPAM's requirement to honour unsubscribe requests within 10 business days and retain proof of compliance.
- **Re-subscribe token**: a separate HMAC token with `action = 'resub'` prevents the unsubscribe link from being reused to re-subscribe (or vice versa).

---

## Anti-patterns

- **No signature on unsubscribe URLs** — any party can unsubscribe arbitrary email addresses by guessing or scraping message IDs.
- **Requiring login to unsubscribe** — RFC 8058 explicitly forbids this for one-click endpoints. It also increases spam complaint rates.
- **Not checking suppression before every send** — the suppression check must be in the critical path of the send, not just at list-export time. A batch job that exports the list daily leaves a window where suppressed recipients receive emails.
- **Storing email in the token plaintext without encoding** — the `@` character and dots in email addresses require careful handling in URL path segments. Always base64url-encode.

---

## Gotchas

- Gmail's one-click unsubscribe handler may send the POST from a Google IP, not the recipient's IP. Do not use IP-based rate limiting on the unsubscribe endpoint — rate-limit by token instead (mark each token as used in KV after first redemption if you want single-use tokens).
- The `List-Unsubscribe` header requires the HTTPS URL to respond to both GET (for traditional clients) and POST (for RFC 8058 clients). Some ESPs strip these headers — verify with the MailChannels or SendGrid API that the headers are preserved.
- D1 `ON CONFLICT ... DO UPDATE` syntax follows SQLite upsert semantics. The `excluded.` table prefix references the values from the attempted insert.
- CAN-SPAM requires processing unsubscribe requests within 10 business days. With this implementation, suppression is immediate. Ensure your sending pipeline's `isSuppressed` check is called at send time, not at list-compilation time hours earlier.

---

## Verification

```bash
# Build an unsubscribe URL (using a local script)
node -e "
const crypto = require('crypto');
const secret = process.env.UNSUB_SECRET;
const email = 'test@example.com';
const listId = 'global';
const payload = 'unsub:' + listId + ':' + email;
const sig = crypto.createHmac('sha256', secret).update(payload).digest('base64url');
const eb64 = Buffer.from(email).toString('base64url');
const lb64 = Buffer.from(listId).toString('base64url');
console.log('Token:', eb64 + '.' + lb64 + '.unsub.' + sig);
"

# Test RFC 8058 one-click POST
curl -X POST 'https://email.example.com/unsubscribe/<token>' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'List-Unsubscribe=One-Click'

# Verify suppression
wrangler d1 execute email-db --command \
  "SELECT * FROM unsubscribes WHERE email = 'test@example.com';"

# Export suppression list
curl -H 'x-internal-key: <UNSUB_SECRET>' \
  'https://email.example.com/suppression-list?list_id=global'
```

---

## Related

- `workers-transactional-email-queue.md` — calling `isSuppressed` before enqueuing a send
- `workers-email-template-versioning.md` — embedding the unsubscribe URL as a `{{unsubscribe_url}}` template variable
- RFC 8058: https://www.rfc-editor.org/rfc/rfc8058
- RFC 2369: https://www.rfc-editor.org/rfc/rfc2369

---

## Sources

- https://developers.cloudflare.com/d1/worker-api/d1-client-api/
- https://www.rfc-editor.org/rfc/rfc8058
- https://support.google.com/mail/answer/81126 (Gmail bulk sender requirements)
- https://senders.yahooinc.com/best-practices/ (Yahoo bulk sender requirements)
