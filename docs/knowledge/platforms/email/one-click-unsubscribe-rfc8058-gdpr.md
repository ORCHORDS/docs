# Email Unsubscribe Flow GDPR Compliance with One-Click RFC 8058

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Gmail and Yahoo started enforcing one-click unsubscribe for bulk senders in February 2024, requiring senders to honour unsubscribe requests within two business days. Many senders still rely on link-click redirects to a preference page, which fails the one-click requirement and increases spam complaints. Additionally, the GDPR's right to withdraw consent (Art. 7(3)) means the unsubscribe must be technically trivial, irreversible without re-consent, and auditable. A Cloudflare Worker that handles RFC 8058 `List-Unsubscribe-Post` requests and records GDPR-compliant opt-out evidence closes both compliance gaps simultaneously.

## Context

RFC 8058 (January 2017) defines the `List-Unsubscribe-Post` header that allows a mail client (not the user's browser) to send a direct HTTP POST to the sender's endpoint with the body `List-Unsubscribe=One-Click`. The receiving Worker must suppress the subscriber in under 24 hours (Google's effective requirement). Unlike the RFC 2369 `List-Unsubscribe` mailto or HTTP GET mechanism, the POST carries no personally-identifiable information in the URL path itself — the subscriber identity is encoded in an HMAC-signed token embedded in the URL, making the endpoint non-enumerable. Combined with a D1 audit table recording the unsubscribe event's timestamp, origin, and consent version, this satisfies GDPR Art. 7(3) withdrawal evidence requirements.

## Header Injection at Send Time

Every bulk or marketing email must include both `List-Unsubscribe` and `List-Unsubscribe-Post` headers. The unsubscribe URL must encode the subscriber identity as a signed token, not a raw user ID.

```typescript
// src/headers.ts
import { createHmac } from 'node:crypto';

interface UnsubscribeToken {
  userId:     string;
  listId:     string;
  issuedAt:   number;   // epoch seconds
}

export function signToken(payload: UnsubscribeToken, secret: string): string {
  const data = JSON.stringify(payload);
  const b64  = btoa(data).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const sig  = createHmac('sha256', secret).update(b64).digest('hex').slice(0, 16);
  return `${b64}.${sig}`;
}

export function verifyToken(
  token: string,
  secret: string,
  maxAgeSeconds = 7 * 24 * 3600
): UnsubscribeToken | null {
  const [b64, sig] = token.split('.');
  if (!b64 || !sig) return null;
  const expected = createHmac('sha256', secret).update(b64).digest('hex').slice(0, 16);
  if (sig !== expected) return null;
  try {
    const payload: UnsubscribeToken = JSON.parse(atob(b64.replace(/-/g, '+').replace(/_/g, '/')));
    if (Date.now() / 1000 - payload.issuedAt > maxAgeSeconds) return null;
    return payload;
  } catch {
    return null;
  }
}

export function buildUnsubscribeHeaders(
  userId: string,
  listId: string,
  baseUrl: string,
  secret: string
): Record<string, string> {
  const token = signToken({ userId, listId, issuedAt: Math.floor(Date.now() / 1000) }, secret);
  const url   = `${baseUrl}/unsubscribe?token=${token}`;

  return {
    'List-Unsubscribe':      `<${url}>, <mailto:unsub@example.com?subject=unsubscribe>`,
    'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
    'List-ID':               `<${listId}.example.com>`,
  };
}
```

### Integration with SendGrid / Resend

```typescript
// src/send-bulk.ts
import { buildUnsubscribeHeaders } from './headers';

export async function sendBulkEmail(
  apiKey: string,
  to: string,
  userId: string,
  listId: string,
  subject: string,
  htmlBody: string,
  env: { UNSUB_BASE_URL: string; UNSUB_SECRET: string }
): Promise<void> {
  const unsubHeaders = buildUnsubscribeHeaders(
    userId, listId, env.UNSUB_BASE_URL, env.UNSUB_SECRET
  );

  await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: 'newsletter@example.com' },
      subject,
      headers: unsubHeaders,
      content: [
        { type: 'text/plain', value: stripHtml(htmlBody) },
        { type: 'text/html',  value: appendUnsubFooter(htmlBody, unsubHeaders['List-Unsubscribe']) },
      ],
    }),
  });
}

function appendUnsubFooter(html: string, listUnsubHeader: string): string {
  // Extract the HTTPS URL from the header value  <url>, <mailto:...>
  const httpsMatch = listUnsubHeader.match(/<(https?:[^>]+)>/);
  const url = httpsMatch ? httpsMatch[1] : '#';

  // Mobile-safe footer: single column, 14px min, tap-friendly CTA
  const footer = `
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="margin-top:32px;border-top:1px solid #e5e5e5">
  <tr><td align="center" style="padding:20px 16px">
    <p style="font-size:13px;color:#777;margin:0 0 10px;line-height:1.5">
      You are receiving this email because you subscribed to our newsletter.
    </p>
    <a
       style="display:inline-block;padding:12px 24px;background:#333;color:#fff;
              font-size:14px;font-family:Arial,sans-serif;text-decoration:none;
              border-radius:4px;min-width:44px;text-align:center">
      Unsubscribe
    </a>
  </td></tr>
</table>`;

  return html.replace(/<\/body>/i, `${footer}</body>`);
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}
```

## Worker — RFC 8058 One-Click Endpoint

```typescript
// src/unsubscribe-worker.ts
import { verifyToken } from './headers';

export interface Env {
  DB:           D1Database;
  UNSUB_SECRET: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // RFC 8058 one-click: mail client sends POST with body List-Unsubscribe=One-Click
    if (req.method === 'POST' && url.pathname === '/unsubscribe') {
      return handleOneClick(req, env, url);
    }

    // Browser unsubscribe confirmation page (GET from email link click)
    if (req.method === 'GET' && url.pathname === '/unsubscribe') {
      return handleBrowserUnsubscribe(req, env, url);
    }

    // Re-subscribe (GDPR: withdrawal is reversible by re-consent only)
    if (req.method === 'POST' && url.pathname === '/resubscribe') {
      return handleResubscribe(req, env);
    }

    return new Response('Not found', { status: 404 });
  },
};

async function handleOneClick(req: Request, env: Env, url: URL): Promise<Response> {
  // Validate Content-Type per RFC 8058 §3
  const ct = req.headers.get('Content-Type') ?? '';
  if (!ct.includes('application/x-www-form-urlencoded')) {
    return new Response('Bad Request: wrong Content-Type', { status: 400 });
  }

  const body   = await req.text();
  const params = new URLSearchParams(body);
  if (params.get('List-Unsubscribe') !== 'One-Click') {
    return new Response('Bad Request: invalid body', { status: 400 });
  }

  const token   = url.searchParams.get('token') ?? '';
  const payload = verifyToken(token, env.UNSUB_SECRET);
  if (!payload) {
    return new Response('Unauthorized: invalid or expired token', { status: 401 });
  }

  await recordUnsubscribe(env.DB, payload.userId, payload.listId, {
    method:     'rfc8058_one_click',
    ip:         req.headers.get('CF-Connecting-IP') ?? '',
    userAgent:  req.headers.get('User-Agent') ?? '',
    epoch:      Math.floor(Date.now() / 1000),
  });

  // RFC 8058 §3: respond 200 OK with no body (mail client ignores response body)
  return new Response(null, { status: 200 });
}

async function handleBrowserUnsubscribe(req: Request, env: Env, url: URL): Promise<Response> {
  const token   = url.searchParams.get('token') ?? '';
  const payload = verifyToken(token, env.UNSUB_SECRET);
  if (!payload) {
    return new Response(errorPage('Invalid or expired unsubscribe link.'), {
      status: 400,
      headers: { 'Content-Type': 'text/html' },
    });
  }

  await recordUnsubscribe(env.DB, payload.userId, payload.listId, {
    method:    'browser_click',
    ip:        req.headers.get('CF-Connecting-IP') ?? '',
    userAgent: req.headers.get('User-Agent') ?? '',
    epoch:     Math.floor(Date.now() / 1000),
  });

  return new Response(confirmPage(token), {
    status: 200,
    headers: { 'Content-Type': 'text/html' },
  });
}

async function handleResubscribe(req: Request, env: Env): Promise<Response> {
  const { userId, listId, consentVer } = await req.json<{
    userId: string; listId: string; consentVer: string;
  }>();
  await env.DB.prepare(`
    INSERT INTO opt_out_log (user_id, list_id, method, resubscribed_at, consent_ver)
    VALUES (?, ?, 'resubscribe', unixepoch(), ?)
    ON CONFLICT DO NOTHING
  `).bind(userId, listId, consentVer).run();
  await env.DB.prepare(`
    UPDATE subscriptions SET opted_in = 1, consent_ver = ?, updated_at = unixepoch()
    WHERE user_id = ? AND list_id = ?
  `).bind(consentVer, userId, listId).run();
  return Response.json({ status: 'resubscribed' });
}

async function recordUnsubscribe(
  db: D1Database,
  userId: string,
  listId: string,
  meta: { method: string; ip: string; userAgent: string; epoch: number }
): Promise<void> {
  await db.batch([
    db.prepare(`
      INSERT OR REPLACE INTO subscriptions (user_id, list_id, opted_in, updated_at)
      VALUES (?, ?, 0, ?)
    `).bind(userId, listId, meta.epoch),
    db.prepare(`
      INSERT INTO opt_out_log (user_id, list_id, method, unsub_ip, user_agent, unsub_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `).bind(userId, listId, meta.method, meta.ip, meta.userAgent, meta.epoch),
  ]);
}
```

## D1 Schema for GDPR Audit Trail

```sql
-- migrations/0001_unsubscribe.sql

CREATE TABLE IF NOT EXISTS subscriptions (
  user_id     TEXT NOT NULL,
  list_id     TEXT NOT NULL,
  opted_in    INTEGER NOT NULL DEFAULT 1,
  consent_ver TEXT,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (user_id, list_id)
);

-- Immutable audit log — never UPDATE or DELETE rows here
CREATE TABLE IF NOT EXISTS opt_out_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT NOT NULL,
  list_id      TEXT NOT NULL,
  method       TEXT NOT NULL,   -- 'rfc8058_one_click' | 'browser_click' | 'resubscribe' | 'api'
  unsub_ip     TEXT,
  user_agent   TEXT,
  consent_ver  TEXT,            -- populated for resubscribe rows
  unsub_at     INTEGER NOT NULL DEFAULT (unixepoch()),
  resubscribed_at INTEGER       -- epoch of re-consent, NULL while still opted-out
);

CREATE INDEX idx_optout_user ON opt_out_log (user_id, list_id, unsub_at DESC);
CREATE INDEX idx_optout_time ON opt_out_log (unsub_at);
```

## Suppression Check Before Send

```typescript
// src/suppression.ts
export async function isSuppressed(
  db: D1Database,
  userId: string,
  listId: string
): Promise<boolean> {
  const row = await db
    .prepare('SELECT opted_in FROM subscriptions WHERE user_id = ? AND list_id = ?')
    .bind(userId, listId)
    .first<{ opted_in: number }>();
  if (!row) return false;        // no record = not yet subscribed = allow
  return row.opted_in === 0;
}
```

## Confirmation Page — Mobile-Safe HTML

```typescript
function confirmPage(token: string): string {
  return `<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unsubscribed</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:24px 16px;background:#f9fafb;font-family:Arial,sans-serif}
.card{max-width:480px;margin:40px auto;background:#fff;border-radius:8px;
      padding:32px 24px;box-shadow:0 1px 4px rgba(0,0,0,.12)}
h1{font-size:22px;margin:0 0 12px;color:#111}
p{font-size:15px;color:#444;line-height:1.6;margin:0 0 20px}
.btn{display:inline-block;padding:12px 24px;background:#2563eb;color:#fff;
     font-size:15px;border-radius:6px;text-decoration:none;
     min-height:44px;line-height:20px}
@media(prefers-color-scheme:dark){
  body{background:#1a1a1a}
  .card{background:#252525;box-shadow:0 1px 4px rgba(0,0,0,.4)}
  h1{color:#f0f0f0} p{color:#aaa}
}
</style>
</head><body>
<div class="card">
  <h1>You have been unsubscribed</h1>
  <p>You will no longer receive emails from this list. This change takes effect immediately.</p>
  <p>Changed your mind?</p>
  <a  class="btn">Re-subscribe</a>
</div>
</body></html>`;
}

function errorPage(msg: string): string {
  return `<!DOCTYPE html><html lang="en"><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Error</title>
</head><body style="font-family:Arial;padding:24px">
<h1 style="color:#b91c1c">Unsubscribe failed</h1>
<p>${msg}</p>
</body></html>`;
}
```

## Mobile vs Desktop Rendering Considerations

- **Unsubscribe footer CTA**: minimum 44 px tap height; use `display:inline-block` with `padding:12px 24px` so it renders correctly in Outlook (which ignores CSS `height` on links).
- **Footer font size**: 13 px is the CASL/CAN-SPAM minimum for legible footer text; go no smaller — iOS Mail's auto-zoom kicks in at < 13 px and may reflow the layout.
- **Confirmation page**: single-column, max-width 480 px, 15 px body text ensures the confirmation is legible on a 375 px wide iPhone SE viewport without horizontal scroll.
- **Dark mode confirmation page**: add `@media (prefers-color-scheme: dark)` block — iOS Safari and Chrome Android both respect it; the user may open the link directly from the email client in dark mode.
- **Re-subscribe link**: must be a standard `<a>` anchor that initiates a POST via a confirmation form, not a GET — prevent accidental re-subscription by link prefetch bots.

## Anti-patterns

- **Honouring RFC 8058 POST but not updating the suppression list atomically**: if the Worker updates the DB but then crashes before the suppression check is propagated to the send queue, the user receives another email before the next queue cycle.
- **Requiring a login to unsubscribe**: GDPR Recital 42 and CAN-SPAM both prohibit placing barriers on the unsubscribe path; one-click must require no authentication beyond the signed token.
- **Accepting GET requests as one-click unsubscribes**: link prefetch tools (Google AMP Email, iOS Mail) pre-fetch all links in emails; a GET-based unsubscribe will unsubscribe users without their intent. RFC 8058 requires POST.
- **Deleting opt-out records**: GDPR Art. 7(1) requires demonstrable consent and withdrawal evidence. Suppress by setting `opted_in = 0` and appending to the immutable audit log; never DELETE.
- **Short token TTL for browser unsubscribe links**: tokens embedded in sent emails must be valid for at least 90 days (users often read newsletters weeks after sending). Use a generous TTL — 1 year is common.

## Gotchas

- Gmail requires `List-Unsubscribe-Post` to be present in addition to `List-Unsubscribe` before surfacing the one-click button in the UI. The `List-Unsubscribe` HTTPS URL must use the same registered sending domain (or a sub-domain) — a different domain triggers Gmail's "may be phishing" warning.
- Some mail clients (Outlook desktop) do not render the native one-click button regardless of the headers — the in-email footer link remains the primary unsubscribe path for Outlook users.
- The RFC 8058 POST body is `application/x-www-form-urlencoded` with the exact value `List-Unsubscribe=One-Click`. Do not expect JSON.
- Yahoo requires both the HTTPS List-Unsubscribe URL and the mailto option to be present.
- D1 `batch()` is not a true ACID transaction in all cases; for write consistency across both the `subscriptions` and `opt_out_log` tables, wrap in `db.exec('BEGIN')` ... `COMMIT` if the D1 driver in your Worker version supports it; otherwise use batch as an approximation.

## Verification

```bash
# Test RFC 8058 POST
TOKEN=$(node -e "console.log(require('./src/headers').signToken({userId:'u1',listId:'newsletter',issuedAt:Math.floor(Date.now()/1000)},'secret'))")
curl -X POST "https://your-worker.workers.dev/unsubscribe?token=$TOKEN" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'List-Unsubscribe=One-Click' \
  -v   # expect HTTP 200

# Verify suppression record
npx wrangler d1 execute DB --command \
  "SELECT * FROM subscriptions WHERE user_id='u1';"

# Check audit log
npx wrangler d1 execute DB --command \
  "SELECT * FROM opt_out_log WHERE user_id='u1' ORDER BY unsub_at DESC;"
```

## Related

- `list-unsubscribe-header.md`
- `gdpr-email-consent.md`
- `bulk-email-compliance-can-spam-gdpr.md`
- `suppression-list-management.md`
- `mobile-push-email-preference-d1-schema.md`
- `email-preference-center.md`

## Sources

- RFC 8058 — One-Click Unsubscribe for Email Marketing (January 2017)
- RFC 2369 — The Use of URLs as Meta-Syntax for Core Mail List Commands
- GDPR Article 7(3) — Right to withdraw consent
- Google Bulk Sender Requirements 2024 — https://support.google.com/mail/answer/81126
- Yahoo Sender Requirements — https://senders.yahooinc.com/
