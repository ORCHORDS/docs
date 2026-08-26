# email-verification-otp-workers

**Issue:** Email OTP flows built in Cloudflare Workers are vulnerable
           to abuse, expire too early for mobile users, and deep links
           break in Gmail and iOS Mail apps
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Users report that OTP codes expire before they can type them, or that
"verify email" deep links do not open the app on mobile and instead
open a browser tab.  Abuse reports show scripted accounts generating
thousands of OTP request per hour from disposable email domains,
consuming ESP sending quota and triggering complaint thresholds.

## Context

Cloudflare Workers are stateless between requests.  OTP state (the
code, expiry, attempt count) must be persisted externally.  D1 is
the right store for OTPs because it supports atomic updates and SQL
constraints, unlike KV which has no compare-and-swap.  The flow has
three phases: generate and send, verify, and clean up.  Each phase
has distinct abuse vectors: send abuse (spam the generation endpoint),
brute-force (try all 6-digit codes), and replay (reuse an already-
verified token).

## OTP generation and D1 storage

Use a cryptographically random 6-digit code.  Do not use Math.random().
Store the hash, not the plaintext, so a D1 read leak does not expose
live codes.

```js
// Generate OTP
function generateOtp() {
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  return String(buf[0] % 1_000_000).padStart(6, '0');
}

// Hash before storing (HMAC-SHA-256 keyed to user ID)
async function hashOtp(otp, userId, env) {
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(env.OTP_HASH_KEY),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  );
  const sig = await crypto.subtle.sign(
    'HMAC', key, new TextEncoder().encode(`${userId}:${otp}`),
  );
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}
```

D1 schema—one row per pending verification:

```sql
CREATE TABLE email_otps (
  id          TEXT PRIMARY KEY,     -- UUID
  user_id     TEXT NOT NULL,
  email       TEXT NOT NULL,
  code_hash   TEXT NOT NULL,
  attempts    INTEGER DEFAULT 0,
  created_at  INTEGER NOT NULL,     -- Unix epoch ms
  expires_at  INTEGER NOT NULL,
  verified_at INTEGER               -- NULL = not yet verified
);
CREATE INDEX idx_otps_user ON email_otps (user_id);
CREATE INDEX idx_otps_email ON email_otps (email);
```

Insert with a 15-minute TTL; mobile users open email slowly and
15 minutes is the minimum that avoids re-send friction:

```js
await env.DB.prepare(
  'INSERT INTO email_otps '
+ '(id, user_id, email, code_hash, created_at, expires_at) '
+ 'VALUES (?, ?, ?, ?, ?, ?)',
).bind(crypto.randomUUID(), userId, email, hash,
       Date.now(), Date.now() + 15 * 60 * 1000).run();
```

## Rate limiting by email domain

Disposable-address domains generate high OTP volume with zero real
users.  Rate-limit at the domain level using KV counters:

```
┌─────────────────────────┬──────────┬─────────────────────────┐
│ KV key                  │ Limit    │ Window                  │
├─────────────────────────┼──────────┼─────────────────────────┤
│ otp:dom:<domain>:h      │ 50       │ 1 hour (domain)         │
│ otp:u:<userId>:h        │ 3        │ 1 hour (user)           │
│ otp:blocklist:<domain>  │ blocked  │ persistent (manual)     │
└─────────────────────────┴──────────┴─────────────────────────┘
```

```js
async function domainAllowed(email, env) {
  const domain = email.split('@')[1]?.toLowerCase() ?? '';
  if (await env.RATE_KV.get(`otp:blocklist:${domain}`)) return false;
  const key = `otp:dom:${domain}:h`;
  const n = parseInt(await env.RATE_KV.get(key) ?? '0', 10);
  if (n >= 50) return false;
  await env.RATE_KV.put(key, String(n + 1),
    { expirationTtl: n === 0 ? 3600 : undefined });
  return true;
}
```

Populate the blocklist from open-source disposable-domain lists via
a daily Cron Trigger worker.

## Verification endpoint

Always increment `attempts` before comparing the hash to prevent a
timing oracle.  Reject if expired or attempts >= 5:

```js
export async function verifyOtp(userId, code, env) {
  const row = await env.DB.prepare(
    'SELECT id, code_hash, expires_at, attempts FROM email_otps '
  + 'WHERE user_id = ? AND verified_at IS NULL '
  + 'ORDER BY created_at DESC LIMIT 1',
  ).bind(userId).first();
  if (!row) return { ok: false, reason: 'not_found' };
  if (Date.now() > row.expires_at) return { ok: false, reason: 'expired' };
  if (row.attempts >= 5) return { ok: false, reason: 'locked' };
  await env.DB.prepare(
    'UPDATE email_otps SET attempts = attempts + 1 WHERE id = ?',
  ).bind(row.id).run();
  if (await hashOtp(code, userId, env) !== row.code_hash)
    return { ok: false, reason: 'invalid' };
  await env.DB.prepare(
    'UPDATE email_otps SET verified_at = ? WHERE id = ?',
  ).bind(Date.now(), row.id).run();
  return { ok: true };
}
```

## Mobile deep link handling

OTP emails that include a `myapp://verify?code=123456` custom-scheme
button fail silently in Gmail (Android/iOS) and Outlook Mobile, which
strip non-http(s) hrefs entirely.  Use an HTTPS Universal Link as the
primary button target:

```html
<a href="https://example.com/verify?code={{code}}">Verify email</a>
```

The landing page at `/verify` reads the code and either redirects to
the custom scheme if the app is installed, or shows a web fallback
that completes verification in the browser.  Publish
`/.well-known/apple-app-site-association` (JSON, `Content-Type:
application/json`) via a Cloudflare Pages static file to support iOS
Universal Links.

## Resend logic and abuse prevention

Allow resend only after a 60-second cooldown.  Query D1 for the
most recent OTP row; reject if `Date.now() - created_at < 60_000`.
Then re-run `domainAllowed()` before inserting the new OTP row.
Invalidate any previous unverified row for the same user in the
same query batch:

```js
await env.DB.prepare(
  'UPDATE email_otps SET verified_at = -1 '
+ 'WHERE user_id = ? AND email = ? AND verified_at IS NULL',
).bind(userId, email).run();
// -1 sentinel marks "superseded" to distinguish from "not yet verified"
```

## Anti-patterns

- Storing the plaintext OTP in D1—a compromised database read gives
  attackers all live codes.  Always store the hash.
- Using a 4-digit code to reduce user friction—brute-force space is
  10 000; an attacker hits all values in seconds at 5-attempts-per-
  code limit if codes are not locked after failures.
- Relying on KV for atomic attempt counting—KV has no compare-and-
  swap; use D1 SQL `UPDATE … WHERE attempts < 5` instead.
- Setting expiry to 5 minutes—mobile users frequently switch apps,
  check email, and return; 15 minutes balances security and UX.
- Not invalidating old OTPs when a new one is issued—multiple live
  codes for one user multiplies the brute-force attack surface.

## Gotchas

- D1 `first()` returns `null` if no row matches; always null-check
  before accessing row properties.
- Cloudflare Workers have no persistent in-memory state between
  requests; never cache OTPs in a module-level variable.
- Universal Links require an `apple-app-site-association` JSON file
  at `https://example.com/.well-known/apple-app-site-association`
  served with `Content-Type: application/json`.  Host it via
  Cloudflare Pages or a Workers route.

## Verification

```bash
# Send OTP
curl -X POST https://api.example.com/auth/otp/send \
  -d '{"userId":"u1","email":"test@example.com"}'

# Verify (use code from inbox)
curl -X POST https://api.example.com/auth/otp/verify \
  -d '{"userId":"u1","code":"<code>"}' # Expected: {"ok":true}

# Confirm brute-force lock after 5 wrong attempts
for i in $(seq 1 6); do curl -s -X POST \
  https://api.example.com/auth/otp/verify \
  -d '{"userId":"u1","code":"000000"}'; done
# 6th response: {"ok":false,"reason":"locked"}

# Inspect D1 row
wrangler d1 execute DB --command \
  "SELECT attempts, verified_at FROM email_otps
   WHERE user_id='u1' ORDER BY created_at DESC LIMIT 1"
```

## Related

- `documentation/docs/policies/email/magic-link-email.md`
- `documentation/docs/policies/email/email-verification-flow.md`
- `documentation/docs/policies/email/transactional-email-rate-limiting-workers.md`
- `documentation/docs/policies/cloudflare/d1-patterns.md`

## Source URLs

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://developer.apple.com/documentation/xcode/supporting-associated-domains
- https://developer.android.com/training/app-links
- https://datatracker.ietf.org/doc/html/rfc6238  (TOTP reference)
