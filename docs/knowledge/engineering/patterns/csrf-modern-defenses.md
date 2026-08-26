# csrf-modern-defenses

**Issue:** Modern CSRF defenses — origin check, Sec-Fetch-Site
**Date:** 2026-08-09
**Status:** documented

## Symptom
You use double-submit cookies for CSRF. A security audit says
"you should also check the Origin header." You add an Origin
check. Now some legitimate requests are blocked (mobile apps
with no Origin header).

## Root cause
**CSRF defense has multiple layers.** The Origin/Referer check
is one layer; the double-submit cookie is another. Each has
tradeoffs.

**Source:** OWASP CSRF Defense Cheat Sheet:
https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

> "Verifying the Origin and/or Referer header ... is a powerful
> CSRF defense. ... It is recommended to combine with other
> defenses for defense in depth."

## The layers of CSRF defense

### Layer 1: SameSite cookies
- **What:** The browser doesn't send the cookie on cross-site
  requests
- **Browser support:** All modern browsers
- **Limitation:** SameSite=Lax has a 2-minute window for
  top-level navigations; not 100% effective for all attack
  vectors

### Layer 2: Origin / Referer check
- **What:** Server checks the Origin (or Referer) header
- **Browser support:** Universal (every browser sends these)
- **Limitation:** Some legitimate clients (mobile apps, older
  browsers) don't send these

### Layer 3: Sec-Fetch-Site header (modern)
- **What:** Browser tells the server the relationship
  (same-origin, same-site, cross-site, none)
- **Browser support:** All modern browsers (2020+)
- **Limitation:** Same as Origin — some clients don't send

### Layer 4: CSRF token (double-submit)
- **What:** Server requires a token that's tied to the user
  session
- **Browser support:** Universal
- **Limitation:** Requires session cookie auth

### Layer 5: Custom request header
- **What:** Client adds a custom header (e.g. `X-Requested-With`)
- **Browser support:** Universal
- **Limitation:** Simple custom headers trigger CORS
  preflight; the attack vector is "the attacker's site can't
  add a custom header" (only the user's browser can)

## Implementation

### Origin / Referer check
```ts
const ALLOWED_ORIGINS = new Set([
  'https://example.com',
  'https://www.example.com',
  'https://staging.example.com',
  'http://localhost:3000',  // dev
]);

function checkOrigin(request: Request): boolean {
  if (request.method === 'GET' || request.method === 'HEAD') return true;

  const origin = request.headers.get('Origin');
  if (origin && ALLOWED_ORIGINS.has(origin)) return true;

  // Fall back to Referer (older browsers)
  const referer = request.headers.get('Referer');
  if (referer) {
    try {
      const url = new URL(referer);
      if (ALLOWED_ORIGINS.has(url.origin)) return true;
    } catch {}
  }

  return false;
}
```

### Sec-Fetch-Site check
```ts
function checkSecFetchSite(request: Request): boolean {
  if (request.method === 'GET' || request.method === 'HEAD') return true;

  const secFetchSite = request.headers.get('Sec-Fetch-Site');
  // 'same-origin' = same scheme + host + port
  // 'same-site' = same registrable domain
  // 'cross-site' = different domain
  // 'none' = user typed the URL, opened a bookmark, etc.

  if (secFetchSite === 'cross-site') return false;  // block
  return true;  // 'same-origin', 'same-site', 'none' = OK
}
```

### Custom header
```ts
function checkCustomHeader(request: Request): boolean {
  if (request.method === 'GET' || request.method === 'HEAD') return true;

  const xRequestedWith = request.headers.get('X-Requested-With');
  if (xRequestedWith !== 'XMLHttpRequest') return false;  // require

  return true;
}

// On the client (browser, mobile app, etc.):
fetch('/api/users', {
  method: 'POST',
  headers: { 'X-Requested-With': 'XMLHttpRequest' },
  body: JSON.stringify(data),
});
```

## Defense in depth

Use multiple layers:
```ts
async function csrfCheck(request: Request, env: Env): Promise<boolean> {
  if (request.method === 'GET' || request.method === 'HEAD') return true;

  // Layer 1: SameSite cookie (browser-enforced)
  // (Can't check from the server; the browser does this)

  // Layer 2: Origin/Referer check
  if (!checkOrigin(request)) return false;

  // Layer 3: Sec-Fetch-Site check
  if (!checkSecFetchSite(request)) return false;

  // Layer 4: CSRF token (double-submit)
  if (!verifyCsrfToken(request)) return false;

  // Layer 5: Custom header (for browser requests)
  if (request.headers.get('Sec-Fetch-Mode') === 'cors') {
    if (request.headers.get('X-Requested-With') !== 'XMLHttpRequest') {
      return false;
    }
  }

  return true;
}
```

## When to use which

| Client | Defense |
|---|---|
| Modern browser SPA | All 5 layers (defense in depth) |
| Mobile app | Origin check + custom header |
| Server-to-server | mTLS or signed request (not CSRF, different concern) |
| API for 3rd parties | API key + OAuth (not CSRF) |

## Verification
- **Test:** `test/csrf-modern.test.ts > cross-origin request
  blocked by Origin check, Sec-Fetch-Site check, AND token
  check` — passes
- **Test:** `test/csrf-modern.test.ts > same-origin request
  passes all 3 checks` — passes
- **Live:** Burp Suite / OWASP ZAP shows no CSRF findings
- **Pen test:** Annual third-party review

## Gotchas
- **The Origin header is `null` in some cases** (e.g. same-
  origin POST, sandboxed iframe). The check must handle
  `null` gracefully.
- **The Referer can be stripped** by the user (browser
  setting) or by a proxy. Don't rely on it as the only check.
- **Sec-Fetch-Site is not sent by all clients** (curl,
  Postman, older browsers). For non-browser clients, the
  check should be skipped or the client should explicitly
  send a header.
- **A custom header triggers CORS preflight** in browsers. The
  first request is OPTIONS; the second is the real request.
  The performance cost is small.
- **The Origin check is for the value** of the Origin header,
  not its presence. A missing Origin is suspicious but not
  always malicious.

## Related
- `csrf-protection-double-submit.md`
- `csrf-vs-cors-vs-samesite.md` (the relationship)
- `session-cookies-vs-jwt.md`
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- Sec-Fetch-Site spec: https://w3c.github.io/webappsec-fetch-metadata/
