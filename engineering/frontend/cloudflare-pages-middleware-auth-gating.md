# Cloudflare Pages Middleware Auth Gating

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You have a Cloudflare Pages site with sections that require authentication (dashboard, admin, account pages). Unauthenticated requests must redirect to `/login` before the browser downloads any protected HTML. You want the gate to run at the edge — not inside React or as a client-side redirect — so protected content never reaches the wire for anonymous users.

## Context

Cloudflare Pages Functions support a `_middleware.ts` file placed in the `functions/` directory. Middleware wraps every request matching its path and runs before any other function or asset. This is the right layer for auth gating: it is executed on Cloudflare's global network before the CDN serves the static asset, costs no round-trip to an origin, and can inspect cookies or JWT headers with the full Workers runtime.

Common auth patterns: session cookie validated against KV or D1, JWT verified with the WebCrypto API, or delegating to a third-party auth provider (Clerk, Auth.js, Stytch) whose SDK runs inside the Worker.

---

## Directory-Scoped Middleware

Place `_middleware.ts` inside the directory to protect. Files in `functions/dashboard/` only run for `/dashboard/*` requests.

```
functions/
  _middleware.ts          ← global middleware (runs for every request)
  dashboard/
    _middleware.ts        ← only /dashboard/*
    index.ts
  api/
    _middleware.ts        ← only /api/*
    user.ts
```

---

## Session Cookie Middleware with KV

```typescript
// functions/dashboard/_middleware.ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  SESSIONS: KVNamespace;
}

interface Session {
  userId: string;
  expiresAt: number;
}

function getSessionId(cookieHeader: string | null): string | null {
  if (!cookieHeader) return null;
  const match = cookieHeader.match(/(?:^|;\s*)sid=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const sessionId = getSessionId(ctx.request.headers.get('cookie'));

  if (!sessionId) {
    return redirectToLogin(ctx.request.url);
  }

  const session = await ctx.env.SESSIONS.get<Session>(
    `session:${sessionId}`,
    'json',
  );

  if (!session || session.expiresAt < Date.now()) {
    return redirectToLogin(ctx.request.url);
  }

  // Propagate userId to downstream functions via headers
  const request = new Request(ctx.request, {
    headers: new Headers({
      ...Object.fromEntries(ctx.request.headers),
      'x-user-id': session.userId,
    }),
  });

  return ctx.next(request);
};

function redirectToLogin(originalUrl: string): Response {
  const loginUrl = new URL('/login', originalUrl);
  loginUrl.searchParams.set('next', new URL(originalUrl).pathname);
  return Response.redirect(loginUrl.toString(), 302);
}
```

---

## JWT Verification with WebCrypto

Avoid shipping a JWT library; use the native `crypto.subtle` API available in all Workers.

```typescript
// functions/api/_middleware.ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  JWT_SECRET: string;      // set in Pages dashboard → Settings → Variables
}

interface JWTPayload {
  sub: string;
  exp: number;
  role: string;
}

async function importJwtKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify'],
  );
}

async function verifyJwt(
  token: string,
  key: CryptoKey,
): Promise<JWTPayload | null> {
  const parts = token.split('.');
  if (parts.length !== 3) return null;

  const [headerB64, payloadB64, sigB64] = parts;
  const signingInput = `${headerB64}.${payloadB64}`;

  const signature = Uint8Array.from(
    atob(sigB64.replace(/-/g, '+').replace(/_/g, '/')),
    (c) => c.charCodeAt(0),
  );

  const valid = await crypto.subtle.verify(
    'HMAC',
    key,
    signature,
    new TextEncoder().encode(signingInput),
  );

  if (!valid) return null;

  const payload = JSON.parse(atob(payloadB64)) as JWTPayload;
  if (payload.exp * 1000 < Date.now()) return null;

  return payload;
}

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const authorization = ctx.request.headers.get('authorization') ?? '';
  const token = authorization.startsWith('Bearer ')
    ? authorization.slice(7)
    : null;

  if (!token) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const key = await importJwtKey(ctx.env.JWT_SECRET);
  const payload = await verifyJwt(token, key);

  if (!payload) {
    return Response.json({ error: 'Invalid or expired token' }, { status: 401 });
  }

  // Attach user context for downstream route handlers
  ctx.data.userId = payload.sub;
  ctx.data.role = payload.role;

  return ctx.next();
};
```

---

## Role-Based Route Protection

Extend the middleware to enforce roles for specific sub-paths.

```typescript
// functions/admin/_middleware.ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  SESSIONS: KVNamespace;
}

const ADMIN_ROLES = new Set(['admin', 'superuser']);

export const onRequest: PagesFunction<Env> = async (ctx) => {
  // Assume a parent _middleware.ts already set x-user-role
  const role = ctx.request.headers.get('x-user-role') ?? '';

  if (!ADMIN_ROLES.has(role)) {
    return new Response(null, {
      status: 403,
      headers: { location: '/403' },
    });
  }

  return ctx.next();
};
```

---

## Caching Auth Decisions at the Edge

KV reads add ~1–5 ms; cache the result in a `waitUntil` write-through pattern to avoid per-request KV hits for high-traffic routes.

```typescript
// functions/dashboard/_middleware.ts (with cache)
export const onRequest: PagesFunction<Env> = async (ctx) => {
  const sessionId = getSessionId(ctx.request.headers.get('cookie'));
  if (!sessionId) return redirectToLogin(ctx.request.url);

  const cacheKey = new Request(`https://cache.internal/session/${sessionId}`);
  const cache = caches.default;

  let session = await cache.match(cacheKey).then(async (cached) => {
    if (cached) return cached.json() as Promise<Session>;
    return null;
  });

  if (!session) {
    session = await ctx.env.SESSIONS.get<Session>(`session:${sessionId}`, 'json');
    if (session) {
      // Cache for remaining session lifetime, max 60 s
      const ttl = Math.min(60, Math.floor((session.expiresAt - Date.now()) / 1000));
      if (ttl > 0) {
        ctx.waitUntil(
          cache.put(
            cacheKey,
            new Response(JSON.stringify(session), {
              headers: { 'cache-control': `private, max-age=${ttl}` },
            }),
          ),
        );
      }
    }
  }

  if (!session || session.expiresAt < Date.now()) {
    return redirectToLogin(ctx.request.url);
  }

  return ctx.next();
};
```

---

## Anti-patterns

- **Client-side auth gating only** – React Router guards that redirect in `useEffect` are too late; the HTML and JS bundle already loaded; always gate at the middleware layer.
- **Storing JWT in `localStorage`** – the middleware cannot read it; use `HttpOnly; Secure; SameSite=Lax` cookies instead.
- **Validating tokens on every request without caching** – WebCrypto verify is fast but KV reads are not; cache valid sessions as shown above.
- **Returning 401 for HTML routes** – browsers do not follow redirects on 401; return 302 to `/login` for HTML routes and 401 JSON for API routes.
- **Using `ctx.data` to pass secrets to untrusted functions** – `ctx.data` is shared with all downstream middleware and route functions; pass only safe identifiers like `userId` and `role`.

---

## Gotchas

- `Response.redirect()` with a 302 loses the original `POST` body; use 303 for form submission redirects to force `GET`.
- `caches.default` in Pages Functions is isolated per Cloudflare datacenter (same as Workers); it is not a shared distributed cache across all DCs.
- The `x-user-id` header injected by middleware is visible in browser DevTools network tab if it appears in the response; strip it from outgoing responses with an `HTMLRewriter` or by only injecting it on the cloned request passed to `ctx.next()`.
- Pages Functions do not support streaming `ctx.next()` responses through middleware when the middleware needs to inspect the body — you must either buffer or avoid body inspection in middleware.
- Environment variables set in the Pages dashboard are available at runtime but NOT at build time; never gate auth on build-time variables.

---

## Verification

```bash
# Test unauth redirect
curl -si https://your-site.pages.dev/dashboard | grep -E 'HTTP|location'
# Expected: HTTP/2 302 + location: /login?next=/dashboard

# Test with valid session cookie
curl -si https://your-site.pages.dev/dashboard \
  -H 'Cookie: sid=YOUR_VALID_SESSION_ID' | grep HTTP
# Expected: HTTP/2 200

# Test expired session
curl -si https://your-site.pages.dev/dashboard \
  -H 'Cookie: sid=EXPIRED_SESSION_ID' | grep -E 'HTTP|location'
# Expected: HTTP/2 302
```

Use Playwright for E2E verification:

```typescript
test('redirects unauthenticated users', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/login\?next=\/dashboard/);
});

test('authenticated users access dashboard', async ({ page, context }) => {
  await context.addCookies([
    { name: 'sid', value: 'valid-session', domain: 'localhost', path: '/' },
  ]);
  await page.goto('/dashboard');
  await expect(page).toHaveURL('/dashboard');
});
```

---

## Related

- `edge-middleware-i18n-routing-cloudflare-pages.md`
- `hono-cloudflare-workers-frontend-api.md`
- `feature-flags-cloudflare-workers-kv-edge-config.md`
- `cloudflare-r2-presigned-upload-frontend.md`
- `next-js-middleware-patterns.md`

---

## Sources

- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/kv/
