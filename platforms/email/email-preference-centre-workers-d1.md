# Email Preference Centre with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Users want granular control over which email types they receive — weekly digest, product updates,
transactional receipts, promotional offers — rather than a binary unsubscribe. You need a hosted
preference page, a signed token flow so it works without login, and a D1-backed store that your
sending Workers query before dispatching any email.

## Context

A preference centre differs from a simple unsubscribe list: it captures consent at the category
level. GDPR Article 7 and CASL require demonstrable, specific consent. CAN-SPAM allows a global
unsubscribe but preference centres keep subscribers engaged on their own terms. The signed token
prevents CSRF and enumeration — no authentication needed.

---

## 1. D1 Schema

```sql
CREATE TABLE email_categories (
  id          TEXT PRIMARY KEY,   -- e.g. 'marketing', 'digest', 'transactional'
  label       TEXT NOT NULL,
  description TEXT,
  mandatory   INTEGER NOT NULL DEFAULT 0  -- 1 = cannot be disabled (e.g. password reset)
);

CREATE TABLE email_preferences (
  subscriber_id  TEXT NOT NULL,
  category_id    TEXT NOT NULL REFERENCES email_categories(id),
  subscribed     INTEGER NOT NULL DEFAULT 1,  -- 1 = yes, 0 = no
  updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (subscriber_id, category_id)
);

-- Seed categories
INSERT INTO email_categories VALUES
  ('transactional', 'Account & Security',   'Password resets, receipts', 1),
  ('digest',        'Weekly Digest',         'Your weekly summary',       0),
  ('product',       'Product Updates',       'New features and releases', 0),
  ('marketing',     'Promotions & Offers',   'Deals and announcements',   0);
```

---

## 2. Signed Token Generation

```typescript
// src/token.ts

const HMAC_ALGO = { name: 'HMAC', hash: 'SHA-256' } as const;

async function importSecret(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    HMAC_ALGO,
    false,
    ['sign', 'verify']
  );
}

/** Create a URL-safe token: base64url(subscriberId:expiry):signature */
export async function createPreferenceToken(
  subscriberId: string,
  secret: string,
  ttlSeconds = 604_800  // 7 days
): Promise<string> {
  const expiry = Math.floor(Date.now() / 1000) + ttlSeconds;
  const payload = `${subscriberId}:${expiry}`;
  const key = await importSecret(secret);
  const sig = await crypto.subtle.sign(
    HMAC_ALGO,
    key,
    new TextEncoder().encode(payload)
  );
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  const payloadB64 = btoa(payload)
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  return `${payloadB64}.${sigB64}`;
}

/** Verify token; returns subscriberId or null */
export async function verifyPreferenceToken(
  token: string,
  secret: string
): Promise<string | null> {
  try {
    const [payloadB64, sigB64] = token.split('.');
    const payload = atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/'));
    const [subscriberId, expiryStr] = payload.split(':');

    if (Date.now() / 1000 > Number(expiryStr)) return null;

    const sigBytes = Uint8Array.from(
      atob(sigB64.replace(/-/g, '+').replace(/_/g, '/')),
      (c) => c.charCodeAt(0)
    );

    const key = await importSecret(secret);
    const valid = await crypto.subtle.verify(
      HMAC_ALGO,
      key,
      sigBytes,
      new TextEncoder().encode(payload)
    );

    return valid ? subscriberId : null;
  } catch {
    return null;
  }
}
```

---

## 3. Preference API Worker

```typescript
// src/worker.ts
import { verifyPreferenceToken } from './token';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/preferences') {
      if (request.method === 'GET')  return handleGet(url, env);
      if (request.method === 'POST') return handlePost(request, url, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function resolveSubscriber(
  url: URL, env: Env
): Promise<string | Response> {
  const token = url.searchParams.get('token');
  if (!token)
    return new Response('Missing token', { status: 400 });

  const subscriberId = await verifyPreferenceToken(token, env.PREFERENCE_SECRET);
  if (!subscriberId)
    return new Response('Invalid or expired token', { status: 401 });

  return subscriberId;
}

async function handleGet(url: URL, env: Env): Promise<Response> {
  const result = await resolveSubscriber(url, env);
  if (result instanceof Response) return result;
  const subscriberId = result;

  const { results: cats } = await env.DB.prepare(
    `SELECT c.id, c.label, c.description, c.mandatory,
            COALESCE(p.subscribed, 1) AS subscribed
     FROM email_categories c
     LEFT JOIN email_preferences p
       ON p.category_id = c.id AND p.subscriber_id = ?
     ORDER BY c.mandatory DESC, c.label ASC`
  ).bind(subscriberId).all();

  return Response.json({ subscriberId, categories: cats });
}

async function handlePost(
  request: Request, url: URL, env: Env
): Promise<Response> {
  const result = await resolveSubscriber(url, env);
  if (result instanceof Response) return result;
  const subscriberId = result;

  const updates = await request.json<Array<{
    categoryId: string; subscribed: boolean;
  }>>();

  const stmts = updates.map(({ categoryId, subscribed }) =>
    env.DB.prepare(
      `INSERT INTO email_preferences (subscriber_id, category_id, subscribed, updated_at)
       VALUES (?, ?, ?, datetime('now'))
       ON CONFLICT(subscriber_id, category_id)
       DO UPDATE SET subscribed = excluded.subscribed,
                     updated_at = excluded.updated_at`
    ).bind(subscriberId, categoryId, subscribed ? 1 : 0)
  );

  // Reject attempts to disable mandatory categories
  const mandatory = await env.DB.prepare(
    `SELECT id FROM email_categories WHERE mandatory = 1`
  ).all<{ id: string }>();
  const mandatoryIds = new Set(mandatory.results.map((r) => r.id));

  const forbidden = updates.find(
    (u) => mandatoryIds.has(u.categoryId) && !u.subscribed
  );
  if (forbidden)
    return new Response(`Category '${forbidden.categoryId}' cannot be disabled`, { status: 422 });

  await env.DB.batch(stmts);

  return Response.json({ ok: true, updated: updates.length });
}
```

---

## 4. Sending Guard — Check Preferences Before Dispatch

```typescript
// src/send-guard.ts
import type { Env } from './types';

export async function isSubscribed(
  subscriberId: string,
  categoryId: string,
  env: Env
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT subscribed FROM email_preferences
     WHERE subscriber_id = ? AND category_id = ?`
  ).bind(subscriberId, categoryId).first<{ subscribed: number }>();

  // Default: subscribed = 1 if no explicit preference row
  return row === null ? true : row.subscribed === 1;
}

// Usage in any send Worker:
// if (!(await isSubscribed(userId, 'digest', env))) return;
```

---

## 5. One-Click Global Unsubscribe (RFC 8058)

```typescript
// Handle POST /unsubscribe?token=<token> — required for Gmail/Yahoo bulk senders
async function handleOneClickUnsubscribe(
  request: Request, url: URL, env: Env
): Promise<Response> {
  if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

  const result = await resolveSubscriber(url, env);
  if (result instanceof Response) return result;
  const subscriberId = result;

  // Unsubscribe from all non-mandatory categories
  await env.DB.prepare(
    `INSERT INTO email_preferences (subscriber_id, category_id, subscribed, updated_at)
     SELECT ?, id, 0, datetime('now') FROM email_categories WHERE mandatory = 0
     ON CONFLICT(subscriber_id, category_id)
     DO UPDATE SET subscribed = 0, updated_at = datetime('now')`
  ).bind(subscriberId).run();

  return new Response('Unsubscribed', { status: 200 });
}
```

---

## Anti-patterns

- **Single boolean unsubscribe flag**: Coarse-grained; once unsubscribed users cannot re-engage with categories they do care about.
- **No token expiry**: Links in old emails remain valid indefinitely — an attacker who intercepts an email can alter preferences.
- **Defaulting mandatory=0 for transactional categories**: Password resets and security alerts must always send; gate them explicitly.
- **Storing preferences in KV**: KV lacks atomic upsert; D1's `ON CONFLICT DO UPDATE` ensures consistency under concurrent form submissions.

## Gotchas

- The default subscribed=1 assumption (no row = subscribed) means you must explicitly write `subscribed=0` rows for opt-outs; never rely on row absence to mean opted-out.
- Include `List-Unsubscribe: <URL>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers in every non-transactional email pointing at your `/unsubscribe` endpoint.
- Token-only preference pages are GDPR-sufficient for re-confirming existing consent but not for collecting fresh consent from new subscribers.
- The preference page URL must be HTTPS; some ISPs reject `List-Unsubscribe` headers containing plain HTTP URLs.

## Verification

```bash
# Generate a test token (run in a local Worker test or REPL)
# Then call the API
curl "https://prefs.your-worker.dev/preferences?token=<token>"

# Check stored preferences for a subscriber
wrangler d1 execute email-db --command \
  "SELECT * FROM email_preferences WHERE subscriber_id = 'user-123'"

# Verify mandatory guard: try disabling 'transactional'
curl -X POST "https://prefs.your-worker.dev/preferences?token=<token>" \
  -H "Content-Type: application/json" \
  -d '[{"categoryId":"transactional","subscribed":false}]'
# Expect 422
```

## Related

- `email-preference-center.md`
- `one-click-unsubscribe-rfc8058-gdpr.md`
- `email-consent-audit-trail-d1.md`
- `email-suppression-list-kv-workers.md`
- `gdpr-email-consent.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://datatracker.ietf.org/doc/html/rfc8058
- https://gdpr.eu/article-7-how-to-get-consent/
