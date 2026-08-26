# csrf-vs-cors-vs-samesite

**Issue:** The relationship between CSRF, CORS, SameSite — common confusion
**Date:** 2026-08-09
**Status:** documented

## Symptom
You add `SameSite=Strict` to your session cookie. You think
you're CSRF-protected. A security audit finds you still have
CSRF vulnerabilities. The reviewer says "SameSite is not
sufficient."

## Root cause
**CORS, CSRF, and SameSite are different things that work
together.** They are not substitutes for each other.

| Concept | Purpose | Enforced by |
|---|---|---|
| **SameSite cookie** | Tells the browser to NOT send the cookie on cross-site requests | Browser |
| **CORS** | Tells the browser to allow the JS to READ the response | Browser |
| **CSRF token** | Tells the server "this request originated from our site" | Server (you) |

**Source:** OWASP — CSRF Prevention Cheat Sheet:
https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

## How they work together

### Scenario: Cross-site form POST to your API

1. **Browser blocks the cookie send (SameSite=Strict)**
   - The user's `<form>` on evil.com tries to POST to your API
   - The browser sees `SameSite=Strict` → does NOT send the
     `mc_sid` cookie
   - The server gets the POST but no session → 401
   - ✅ CSRF blocked

2. **Browser allows the cookie but server rejects (no CSRF token)**
   - The user is on `evil.com` which uses `fetch()` to POST to
     your API
   - The browser sees `SameSite=Lax` → DOES send the cookie
     (for top-level navigations, but not for fetch from a
     cross-site origin)
   - The server gets the POST + session → executes the action
   - ❌ CSRF succeeded

3. **The double-submit defense**
   - The server requires a CSRF token in addition to the
     session cookie
   - The browser does not let `evil.com` read the CSRF cookie
     (cross-origin `document.cookie` is blocked)
   - `evil.com` cannot send the CSRF token in the header
   - Server rejects → 403
   - ✅ CSRF blocked

## The full defense

```ts
// 1. Set the session cookie with SameSite=Lax
headers.set('Set-Cookie',
  `mc_sid=${sessionId}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=3600`);

// 2. Set the CSRF cookie with SameSite=Strict
headers.append('Set-Cookie',
  `mc_csrf=${csrfToken}; Secure; SameSite=Strict; Path=/; Max-Age=3600`);

// 3. Verify CSRF token on state-changing requests
if (request.method !== 'GET' && request.method !== 'HEAD') {
  if (!verifyCsrf(request)) {
    return new Response('Forbidden', { status: 403 });
  }
}

// 4. Set CORS headers on the response (for cross-origin SPA)
const origin = request.headers.get('Origin') ?? '';
if (ALLOWED_ORIGINS.has(origin)) {
  headers.set('Access-Control-Allow-Origin', origin);
  headers.set('Access-Control-Allow-Credentials', 'true');
}
```

## What each defense protects against

### SameSite=Lax
- **Protects against:** `<form>` POST from cross-site
- **Does NOT protect against:** cross-site `fetch()` POST (in
  some browsers), top-level navigation GET (the 2-minute window)
- **Use when:** you want OAuth callbacks to work, but want
  basic CSRF protection

### SameSite=Strict
- **Protects against:** all cross-site sends
- **Does NOT protect against:** same-site CSRF (e.g. an XSS
  on your own site)
- **Use when:** the cookie is for sensitive actions (banking,
  password reset)

### CSRF token (double-submit)
- **Protects against:** all CSRF, including same-site XSS-
  initiated CSRF (if combined with CSP)
- **Use when:** you need defense in depth

### CORS
- **Protects against:** unauthorized JS from reading the
  response
- **Does NOT protect against:** the request being sent or
  executed
- **Use when:** you have a cross-origin SPA + API

## Verification
- **Test:** `test/csrf.test.ts` + `test/cors.test.ts` + manual
  test of cross-origin `fetch()` from dev tools
- **Live:** Pen test confirms no CSRF / CORS misconfiguration
- **Audit:** Annual review of cookie + CORS config

## Gotchas
- **`SameSite=None` requires `Secure`.** Modern browsers reject
  `SameSite=None` cookies that don't have `Secure`.
- **The 2-minute window for `SameSite=Lax`** is intentional —
  it allows a user clicking an external link to your site to
  land on a logged-in page without a redirect.
- **CORS doesn't prevent CSRF.** It prevents the RESPONSE from
  being read by a cross-origin script. The request is still
  sent (and processed, if not blocked by other defenses).
- **Subdomain attacks:** A bug on `*.example.com` can set
  cookies for `example.com`. Use `Domain=.example.com` only if
  you control all subdomains.
- **CORS preflight failures look like CSRF failures** to a
  developer who's not paying attention. Both are "the request
  was rejected by the browser." Check the Network tab.

## Related
- `csrf-protection-double-submit.md`
- `cors-pages-functions.md`
- `session-cookies-vs-jwt.md`
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
