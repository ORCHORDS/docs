# session-cookies-vs-jwt

**Issue:** Why session cookies (not JWT) for a 21+ social platform
**Date:** 2026-08-09
**Status:** documented (architectural decision)

## Symptom
You build a consumer app with JWT for auth. Six months later, an
employee is terminated. You need to revoke their session
immediately. You cannot — JWTs are self-contained and valid until
expiry (typically 1h+). The terminated employee still has access
until they log out or the token expires.

## Root cause
JWT (JSON Web Token) is **stateless** — the token itself contains
the user's identity + claims. The server doesn't store the token
or its revocation state. To "revoke" a JWT, you'd need:
- A server-side revocation list (defeats the purpose)
- Short token expiry + refresh token (operational overhead)
- A versioned `iat` claim + a global "ban all tokens issued before
  time T" mechanism (coarse-grained, kills all users)

For a 21+ social platform where trust & safety requires
**immediate, individual revocation**, stateless JWT is the wrong
default.

**Source:** OWASP Session Management Cheat Sheet:
https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

> "JWTs are not a session management mechanism by themselves, and
> should not be used as such. ... Server-side sessions are the
> recommended approach."

## Fix
Use **server-side sessions** with an opaque session ID in a cookie:

```ts
// On login: create row in `sessions` table, return ID
const sessionId = crypto.randomUUID();
await env.DB.prepare(
  `INSERT INTO sessions (id, user_id, tenant_id, expires_at, created_at)
   VALUES (?, ?, ?, ?, ?)`
).bind(sessionId, user.id, user.tenant_id, now + 3600, now).run();

// On response: set httpOnly cookie
headers.set('Set-Cookie',
  `mc_sid=${sessionId}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=3600`);

// On request: look up session by ID
const sess = await env.DB.prepare(
  `SELECT user_id, tenant_id, expires_at, revoked_at FROM sessions
   WHERE id = ? AND expires_at > ? AND revoked_at IS NULL LIMIT 1`
).bind(sessionId, now).first();
```

Revocation = `UPDATE sessions SET revoked_at = ? WHERE id = ?`. One
SQL statement, immediately effective. The cookie in the user's
browser becomes useless on next request.

## Verification
- **Test:** `test/session.test.ts > revocation is immediate` — log in
  → revoke session → next request returns 401 (not 200)
- **Live:** Sentry / log shows 0 "stale session" 401s after a
  revocation event
- **Audit:** Revocations write to the audit log with `actor_id` +
  `target_user_id` for forensic traceability

## Gotchas
- **Cookies require CSRF protection.** State-changing POSTs need a
  CSRF token in addition to the session cookie. See
  `csrf-protection-double-submit.md`.
- **SameSite=Lax is the right default for a social app.** Strict
  breaks OAuth callbacks from third parties. None breaks CSRF.
- **`Secure` flag is mandatory in production.** Browsers reject
  `Secure` cookies on `http://` (only on `https://`).
- **Session ID in URL is NEVER acceptable.** The URL is logged in
  proxies, browser history, and Referer headers. Cookie only.
- **The session row needs cleanup.** A cron that purges expired
  sessions every 24h keeps the table small.

## Related
- `csrf-protection-double-submit.md` (companion entry)
- `audit-chain-durable-object.md` (every session event is audit-logged)
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
