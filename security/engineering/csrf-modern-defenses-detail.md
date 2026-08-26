# csrf-modern-defenses-detail

**Issue:** CSRF — modern defenses, patterns
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user is logged in. They visit a malicious site. The
malicious site makes a POST to your bank. The browser
sends the user's session cookie. The bank processes the
transfer. The user is broke.

## Root cause
**The browser sends the session cookie automatically.**
The malicious site can make requests to your server
using the user's session.

**Source:** OWASP — CSRF:
https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

> "Cross-Site Request Forgery (CSRF) is an attack that
> forces an end user to execute unwanted actions on a web
> application in which they're currently authenticated."

## The "SameSite cookie" pattern (best for most apps)

The SameSite attribute prevents the cookie from being sent
on cross-site requests:
```
Set-Cookie: session=...; SameSite=Lax; Secure
```

- **SameSite=Strict:** Cookie is never sent on cross-site
  requests. Most secure, but breaks some flows.
- **SameSite=Lax:** Cookie is sent on top-level navigation
  (clicking a link), not on subresource requests. Default
  for modern browsers.
- **SameSite=None:** Cookie is always sent. Must be Secure.

For most apps, **`SameSite=Lax`** is the right default.

## The "double-submit cookie" pattern

For additional CSRF protection:
```ts
// 1. On login, set a CSRF cookie
function setCsrfCookie(): string {
  const token = crypto.randomUUID();
  return `csrf=${token}; Path=/; Secure; SameSite=Lax`;
}

// 2. On the client, send the token in a header
fetch('/api/transfer', {
  method: 'POST',
  headers: { 'X-CSRF-Token': getCookie('csrf') },
  body: JSON.stringify({ amount: 100 }),
});

// 3. On the server, verify the header matches the cookie
async function verifyCsrf(request: Request): Promise<boolean> {
  const cookie = parseCookie(request.headers.get('Cookie') ?? '');
  const header = request.headers.get('X-CSRF-Token');

  if (!cookie.csrf || !header) return false;
  return timingSafeEqual(Buffer.from(cookie.csrf), Buffer.from(header));
}
```

The cookie is sent automatically; the header must be set
by JavaScript. An attacker can't set the header.

## The "synchronizer token" pattern

For a server-side token:
```ts
// 1. Generate a token (per session, or per request)
const csrfToken = crypto.randomUUID();
await env.SESSIONS.put(`csrf:${sessionId}`, csrfToken, { expirationTtl: 86400 });

// 2. Embed in forms
<form>
  <input type="hidden" name="csrf_token" value="${csrfToken}" />
  <button type="submit">Transfer</button>
</form>

// 3. On submit, verify
async function verifyCsrfToken(request: Request, sessionId: string, env: Env): Promise<boolean> {
  const body = await request.formData();
  const token = body.get('csrf_token') as string;

  const expected = await env.SESSIONS.get(`csrf:${sessionId}`);
  if (!expected || !token) return false;

  return timingSafeEqual(Buffer.from(expected), Buffer.from(token));
}
```

The token is per-session; a new token can be generated per
request for extra security.

## The "Origin + Referer" check

For an additional check, verify the Origin or Referer:
```ts
function isValidOrigin(request: Request, allowedOrigins: string[]): boolean {
  const origin = request.headers.get('Origin');
  if (origin && allowedOrigins.includes(origin)) return true;

  const referer = request.headers.get('Referer');
  if (referer) {
    try {
      const refererOrigin = new URL(referer).origin;
      return allowedOrigins.includes(refererOrigin);
    } catch {
      return false;
    }
  }

  return false;
}
```

The Origin header is sent on POST requests; the Referer is
sent on navigations.

## The "custom header" pattern

For a simpler check, require a custom header:
```ts
// Client
fetch('/api/transfer', {
  method: 'POST',
  headers: { 'X-Requested-With': 'XMLHttpRequest' },
  body: JSON.stringify({ amount: 100 }),
});

// Server
function hasCustomHeader(request: Request): boolean {
  return request.headers.get('X-Requested-With') === 'XMLHttpRequest';
}
```

A cross-site form submission can't set custom headers
(without CORS).

## The "CORS" pattern

For CORS, configure properly:
```ts
function setCorsHeaders(request: Request, env: Env): Headers {
  const origin = request.headers.get('Origin');
  const allowedOrigins = env.ALLOWED_ORIGINS.split(',');

  const headers = new Headers();
  if (origin && allowedOrigins.includes(origin)) {
    headers.set('Access-Control-Allow-Origin', origin);
    headers.set('Vary', 'Origin');
  }
  headers.set('Access-Control-Allow-Credentials', 'true');
  headers.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE');
  headers.set('Access-Control-Allow-Headers', 'Content-Type, X-CSRF-Token');
  headers.set('Access-Control-Max-Age', '86400');

  return headers;
}
```

CORS is configured; the preflight is handled.

## The "content-type check" pattern

For a simpler check, require a specific content-type:
```ts
// ❌ Vulnerable: form submission
fetch('/api/transfer', {
  method: 'POST',
  body: JSON.stringify({ amount: 100 }),
  // No content-type; defaults to text/plain
});

// ❌ Vulnerable: simple form submission
// application/x-www-form-urlencoded

// ✅ Safe: JSON content-type (CORS preflight required)
fetch('/api/transfer', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ amount: 100 }),
});
```

A cross-site form can only submit `text/plain`,
`application/x-www-form-urlencoded`, or `multipart/form-
data`. Requiring `application/json` forces a CORS preflight,
which a malicious site can't trigger.

## The "idempotent endpoint" pattern

For idempotent operations, the CSRF risk is lower:
- **GET, HEAD, OPTIONS:** Safe; should be idempotent
- **POST, PATCH, DELETE:** Should require CSRF

For GET requests, ensure they don't have side effects.

## The "preflight" pattern

For a preflight, the browser sends OPTIONS first:
```
OPTIONS /api/transfer HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: Content-Type

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type
```

A cross-site request triggers a preflight; the preflight
is rejected if the origin is not allowed.

## The "CSRF protection" decision

For most apps, use **both**:
- `SameSite=Lax` cookies (browser-level)
- CSRF token for state-changing requests (defense in
  depth)

For a high-security app, use:
- `SameSite=Strict` cookies
- Per-request CSRF tokens
- Origin + Referer checks

## The "frame" pattern

For clickjacking, use `X-Frame-Options: DENY`:
```
X-Frame-Options: DENY
```

Or CSP `frame-ancestors 'none'`:
```
Content-Security-Policy: frame-ancestors 'none'
```

The page can't be framed; clickjacking is prevented.

## The "CSRF" anti-patterns

### 1. No SameSite cookie
- **Issue:** Cookie is sent on cross-site requests
- **Fix:** SameSite=Lax (or Strict)

### 2. No CSRF token
- **Issue:** The request can be forged
- **Fix:** Use a CSRF token (double-submit or synchronizer)

### 3. GET for state changes
- **Issue:** The GET can be triggered by an `<img>` tag
- **Fix:** Use POST for state changes

### 4. Trusting Origin
- **Issue:** Some browsers don't send Origin
- **Fix:** Use multiple signals (Origin + CSRF + SameSite)

## Verification
- **Test:** CSRF is blocked
- **Test:** SameSite cookie is set
- **Test:** Origin is verified
- **Pen test:** Annual security review

## Gotchas
- **The "SameSite is enough" anti-pattern.** SameSite=Lax
  is good but not perfect. Add CSRF tokens.
- **The "GET is safe" anti-pattern.** A GET can have
  side effects (e.g. `/logout`); use POST.
- **The "form submission is safe" anti-pattern.** A form
  submission can trigger any endpoint with cookies.
- **The "CORS blocks CSRF" anti-pattern.** CORS blocks
  reading the response, not the request.
- **The "no CSRF for API" anti-pattern.** APIs also need
  CSRF protection if they use cookies.

## Related
- `csrf-protection-double-submit.md`
- `csrf-vs-cors-vs-samesite.md`
- `cors-pages-functions.md`
- `csrf-modern-defenses.md`
- `security-headers-comprehensive.md`
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- SameSite cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite
