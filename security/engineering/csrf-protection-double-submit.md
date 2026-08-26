# csrf-protection-double-submit

**Issue:** `SameSite=Strict` alone is not enough CSRF protection
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a session cookie with `SameSite=Lax` (to allow OAuth
callbacks). A malicious site includes a hidden form that POSTs to
your `/api/account/delete` endpoint. The browser sends your session
cookie (because it's a top-level POST, which Lax allows). The
account is deleted.

## Root cause
`SameSite=Lax` allows cookies on top-level navigations (GET) and
on top-level form POSTs (with a 2-minute window). It does NOT
block cross-site `fetch()` POSTs, but it does block `<form>` POSTs
in many cases. The behavior is browser-dependent and version-dependent.

For a state-changing endpoint, you cannot rely on `SameSite` alone.
You need an additional CSRF defense.

**Source:** OWASP CSRF Prevention Cheat Sheet:
https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

## Fix
Use the **double-submit cookie** pattern:

```ts
// On session creation: also create a CSRF token
const csrfToken = crypto.randomUUID();
await env.DB.prepare(
  `UPDATE sessions SET csrf_token = ? WHERE id = ?`
).bind(csrfToken, sessionId).run();

headers.append('Set-Cookie',
  `mc_csrf=${csrfToken}; Secure; SameSite=Strict; Path=/; Max-Age=3600`);

// On state-changing request: verify CSRF token
async function verifyCsrf(request: Request, env: Env): Promise<boolean> {
  if (request.method === 'GET' || request.method === 'HEAD') return true;
  const cookieToken = (request.headers.get('cookie') ?? '')
    .match(/(?:^|;\s*)mc_csrf=([^;]+)/)?.[1];
  const headerToken = request.headers.get('x-csrf-token');
  if (!cookieToken || !headerToken) return false;
  if (cookieToken !== headerToken) return false;
  // Optional: verify the token is in the sessions table
  const sess = await env.DB.prepare(
    `SELECT 1 FROM sessions WHERE csrf_token = ? LIMIT 1`
  ).bind(cookieToken).first();
  return !!sess;
}
```

The client reads the CSRF cookie via `document.cookie` (the JS
context) and sends the same value in `X-CSRF-Token` header. A
cross-site attacker cannot read the cookie (the browser blocks
cross-origin `document.cookie`), so they cannot forge the header.

## Verification
- **Test:** `test/csrf.test.ts > cross-origin POST without X-CSRF-Token returns 403`
  — passes
- **Live:** Burp Suite / OWASP ZAP scan shows no CSRF findings
- **Pen test:** Annual third-party pentest includes CSRF coverage

## Gotchas
- **The CSRF cookie must be `SameSite=Strict`** (not Lax) so the
  attacker can't trigger any cross-site send.
- **The CSRF cookie must NOT be `HttpOnly`** — JavaScript needs to
  read it. The session cookie stays `HttpOnly`; only the CSRF
  cookie is readable.
- **For double-submit, the header AND cookie must match.** Constant
  time comparison is not needed (both are random UUIDs), but the
  comparison should be strict equality.
- **Don't put the CSRF token in a URL parameter.** URLs are logged.
  Use a header.
- **For SPAs, the client must add `X-CSRF-Token` to every state-
  changing request.** Document this in the API client SDK.
- **The pattern is per-tab, not per-session.** Different tabs can
  use different CSRF tokens if you want finer isolation. Most
  apps just use one per session.

## Related
- `session-cookies-vs-jwt.md` (companion entry)
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
