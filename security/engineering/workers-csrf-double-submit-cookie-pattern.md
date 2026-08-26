# CSRF Protection in Workers with the Double-Submit Cookie Pattern

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker serves a browser-facing API or server-rendered HTML application and you need to protect state-mutating endpoints (POST, PUT, PATCH, DELETE) against Cross-Site Request Forgery without relying on a session store. The double-submit cookie pattern is stateless: the server sets a random token in a readable cookie and requires the same value in a custom request header, exploiting the same-origin policy to block forged requests from other origins.

---

## Context

Traditional CSRF protection stores a token server-side in a session and checks it on each request. Workers are often stateless or avoid session storage for latency reasons; the double-submit pattern sidesteps the session requirement. A `__csrf` cookie is set with `SameSite=Strict` and `HttpOnly=false` (so JavaScript can read it) on the first GET. On every mutating request the client reads that cookie and echoes it in the `X-CSRF-Token` header. The Worker verifies that the header value matches the cookie value. Because a cross-site attacker cannot read cookies set on the target origin (same-origin policy), they cannot reproduce the header. Hono's middleware system makes it straightforward to apply this check globally.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name            = "csrf-demo"
main            = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
CSRF_COOKIE_NAME   = "__csrf"
CSRF_HEADER_NAME   = "X-CSRF-Token"
CSRF_COOKIE_DOMAIN = ".example.com"
```

---

## Section 2 — Worker Implementation

```typescript
// src/csrf.ts
export const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export function generateCsrfToken(): string {
  // crypto.randomUUID() is available in all Workers runtimes >= 2021-11-15
  return crypto.randomUUID();
}

export function getCookieValue(cookieHeader: string | null, name: string): string | null {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return rest.join('=');
  }
  return null;
}

export interface CsrfOptions {
  cookieName: string;
  headerName: string;
  cookieDomain: string;
  secureCookie: boolean;
}

/**
 * Returns a Response with the CSRF cookie set if the request has no existing
 * token, or null if no cookie action is needed.
 */
export function buildCsrfSetCookieHeader(
  token: string,
  options: CsrfOptions,
): string {
  const secure = options.secureCookie ? '; Secure' : '';
  return (
    `${options.cookieName}=${token}` +
    `; Path=/` +
    `; Domain=${options.cookieDomain}` +
    `; SameSite=Strict` +
    secure
    // HttpOnly intentionally omitted so the JS client can read it
  );
}

export function validateCsrfToken(
  request: Request,
  options: Pick<CsrfOptions, 'cookieName' | 'headerName'>,
): { valid: boolean; reason?: string } {
  if (SAFE_METHODS.has(request.method)) {
    return { valid: true };
  }

  const cookieHeader = request.headers.get('Cookie');
  const cookieToken = getCookieValue(cookieHeader, options.cookieName);
  const headerToken = request.headers.get(options.headerName);

  if (!cookieToken) return { valid: false, reason: 'Missing CSRF cookie' };
  if (!headerToken) return { valid: false, reason: 'Missing CSRF header' };
  if (cookieToken !== headerToken) return { valid: false, reason: 'CSRF token mismatch' };

  return { valid: true };
}
```

```typescript
// src/index.ts  — Hono integration
import { Hono } from 'hono';
import {
  generateCsrfToken,
  getCookieValue,
  buildCsrfSetCookieHeader,
  validateCsrfToken,
  SAFE_METHODS,
} from './csrf';

export interface Env {
  CSRF_COOKIE_NAME: string;
  CSRF_HEADER_NAME: string;
  CSRF_COOKIE_DOMAIN: string;
}

const app = new Hono<{ Bindings: Env }>();

// ── CSRF middleware ──────────────────────────────────────────────────────────
app.use('*', async (c, next) => {
  const opts = {
    cookieName: c.env.CSRF_COOKIE_NAME,
    headerName: c.env.CSRF_HEADER_NAME,
    cookieDomain: c.env.CSRF_COOKIE_DOMAIN,
    secureCookie: true,
  };

  // For safe methods: ensure the cookie exists; issue one if not.
  if (SAFE_METHODS.has(c.req.method)) {
    await next();
    const existingToken = getCookieValue(
      c.req.header('Cookie') ?? null,
      opts.cookieName,
    );
    if (!existingToken) {
      const token = generateCsrfToken();
      c.res.headers.append('Set-Cookie', buildCsrfSetCookieHeader(token, opts));
    }
    return;
  }

  // For mutating methods: validate.
  const result = validateCsrfToken(c.req.raw, opts);
  if (!result.valid) {
    return c.text(result.reason ?? 'Forbidden', 403);
  }

  await next();
});

// ── Routes ───────────────────────────────────────────────────────────────────
app.get('/', (c) => c.html('<html><body><h1>CSRF Demo</h1></body></html>'));

app.post('/api/data', async (c) => {
  const body = await c.req.json();
  return c.json({ received: body });
});

export default app;
```

---

## Section 3 — Testing / Verification

```typescript
// test/csrf.test.ts
import { describe, it, expect } from 'vitest';
import { SELF } from 'cloudflare:test';

async function getTokenFromCookie(res: Response, cookieName: string): Promise<string | null> {
  for (const [name, value] of res.headers.entries()) {
    if (name.toLowerCase() === 'set-cookie' && value.startsWith(cookieName)) {
      const token = value.split(';')[0].split('=')[1];
      return token ?? null;
    }
  }
  return null;
}

describe('CSRF double-submit', () => {
  it('issues a __csrf cookie on GET', async () => {
    const res = await SELF.fetch('https://example.com/');
    const token = await getTokenFromCookie(res, '__csrf');
    expect(token).toBeTruthy();
  });

  it('rejects POST without header', async () => {
    const res = await SELF.fetch('https://example.com/api/data', {
      method: 'POST',
      headers: {
        'Cookie': '__csrf=abc123',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ test: true }),
    });
    expect(res.status).toBe(403);
  });

  it('accepts POST with matching header and cookie', async () => {
    const token = crypto.randomUUID();
    const res = await SELF.fetch('https://example.com/api/data', {
      method: 'POST',
      headers: {
        'Cookie': `__csrf=${token}`,
        'X-CSRF-Token': token,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ test: true }),
    });
    expect(res.status).toBe(200);
  });

  it('rejects POST when header does not match cookie', async () => {
    const res = await SELF.fetch('https://example.com/api/data', {
      method: 'POST',
      headers: {
        'Cookie': '__csrf=token-a',
        'X-CSRF-Token': 'token-b',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ test: true }),
    });
    expect(res.status).toBe(403);
  });
});
```

---

## Anti-patterns

- **Setting `HttpOnly=true` on the CSRF cookie** — the whole pattern relies on JavaScript being able to read the cookie to copy it into the header; `HttpOnly` breaks this.
- **Using a predictable token** — always use `crypto.randomUUID()` or `crypto.getRandomValues()`; sequential IDs or timestamps are guessable.
- **Checking CSRF on GET requests** — GET should be idempotent and reading the cookie on GET causes problems for prefetch/CDN caching.
- **Storing the CSRF token in `localStorage`** — XSS can read `localStorage`; a cookie with `SameSite=Strict` scopes the token to same-site requests, giving an extra layer of protection.
- **Skipping the header check and relying solely on `SameSite=Strict`** — browser support and edge cases (top-level navigations, some OAuth redirect flows) make `SameSite` alone insufficient as the sole CSRF defense.

---

## Gotchas

- `SameSite=Strict` blocks the cookie from being sent on cross-site top-level navigations (e.g. clicking a link from another domain), which may break OAuth redirect flows — use `SameSite=Lax` for the session cookie, but keep `Strict` for the CSRF cookie.
- When behind Cloudflare's CDN, `Set-Cookie` headers on `GET` responses are stripped for cached responses; ensure the CSRF endpoint is exempt from caching (`Cache-Control: no-store`).
- The double-submit pattern does NOT protect against DNS rebinding or subdomain takeover attacks; pair it with `Origin` / `Referer` header validation for defence in depth.
- Hono's `c.req.header()` lowercases header names; use the lowercased form when reading (`x-csrf-token`).

---

## Verification

```bash
# Deploy
npx wrangler deploy

# 1. GET the root — observe Set-Cookie with __csrf
curl -i https://csrf-demo.<subdomain>.workers.dev/

# 2. POST without CSRF header — expect 403
curl -i -X POST https://csrf-demo.<subdomain>.workers.dev/api/data \
  -H 'Cookie: __csrf=test-token' \
  -H 'Content-Type: application/json' \
  -d '{"foo":"bar"}'

# 3. POST with matching header and cookie — expect 200
TOKEN=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -i -X POST https://csrf-demo.<subdomain>.workers.dev/api/data \
  -H "Cookie: __csrf=$TOKEN" \
  -H "X-CSRF-Token: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"foo":"bar"}'

# 4. Unit tests
npx vitest run
```

---

## Related

- `workers-content-security-policy-nonce.md`
- `workers-jwt-rs256-verification-webcrypto.md`

---

## Sources

- OWASP CSRF Prevention Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- Cloudflare Workers Hono Integration — https://developers.cloudflare.com/workers/frameworks/framework-guides/hono/
- MDN SameSite Cookies — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite
