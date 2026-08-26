# Pages Functions Authentication Middleware Session

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are deploying a Cloudflare Pages site with server-side logic via Pages Functions
(`functions/` directory). You need every protected route — `/dashboard/*`, `/api/*`,
`/admin/*` — to verify a session before the function handler runs, without copy-pasting
auth logic into every function file.

Pages Functions support middleware via `_middleware.ts` files that run before any sibling
or nested function in the same directory. This article shows how to build a robust
session-checking middleware that gates entire subtrees, attaches the authenticated user to
the context, and short-circuits unauthenticated requests cleanly.

---

## Context

Pages Functions middleware files sit at `functions/_middleware.ts` (applies globally) or
`functions/dashboard/_middleware.ts` (applies only under `/dashboard/`). A middleware
exports a named export `onRequest` (or `onRequestGet`, etc.) and receives a `context`
object with `context.next()` to continue the chain.

Sessions are typically stored as:
- **Signed JWT in an HttpOnly cookie** — verified in middleware, user claims attached to
  `context.data`.
- **Opaque session ID in a cookie** — looked up in KV or D1 to retrieve session data.

This article covers the signed-JWT pattern (lowest latency; no KV lookup per request).

---

## Middleware File Structure

```
functions/
  _middleware.ts           ← runs on every function route (e.g. verify CSRF / log)
  api/
    _middleware.ts         ← runs before all /api/* routes
    users.ts
    profile.ts
  dashboard/
    _middleware.ts         ← runs before all /dashboard/* routes
    index.ts
```

---

## Session JWT Cookie Setup (Login Handler)

```typescript
// functions/api/login.ts
import { SignJWT } from 'jose';   // bundled via Pages Functions npm support

interface Env {
  JWT_SECRET: string;
}

export const onRequestPost: PagesFunction<Env> = async (context) => {
  const { request, env } = context;
  const { username, password } = await request.json<{ username: string; password: string }>();

  // ... validate credentials against D1 ...
  const userId = 'usr_123'; // replace with real lookup

  const secret = new TextEncoder().encode(env.JWT_SECRET);
  const token = await new SignJWT({ sub: userId, role: 'user' })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('8h')
    .setJti(crypto.randomUUID())
    .sign(secret);

  const isSecure = new URL(request.url).protocol === 'https:';
  const cookie = [
    `session=${token}`,
    'HttpOnly',
    'SameSite=Lax',
    isSecure ? 'Secure' : '',
    'Path=/',
    'Max-Age=28800',
  ].filter(Boolean).join('; ');

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': cookie,
    },
  });
};
```

---

## Protected Route Middleware

```typescript
// functions/dashboard/_middleware.ts
import { jwtVerify, type JWTPayload } from 'jose';

interface Env {
  JWT_SECRET: string;
}

export interface SessionUser {
  sub: string;
  role: string;
  jti: string;
}

// Extend the PagesFunction context data type
declare module '@cloudflare/workers-types' {
  interface EventContext<Env, P extends string, Data> {
    data: Data & { user?: SessionUser };
  }
}

function parseCookie(header: string | null, name: string): string | undefined {
  if (!header) return undefined;
  const match = header.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : undefined;
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env, next, data } = context;
  const cookieHeader = request.headers.get('Cookie');
  const token = parseCookie(cookieHeader, 'session');

  if (!token) {
    return Response.redirect(new URL('/login', request.url).toString(), 302);
  }

  const secret = new TextEncoder().encode(env.JWT_SECRET);

  let payload: JWTPayload;
  try {
    ({ payload } = await jwtVerify(token, secret, {
      algorithms: ['HS256'],
      clockTolerance: 15, // seconds — handles minor clock drift
    }));
  } catch {
    // Token invalid or expired — clear the stale cookie and redirect
    const expired = new Response(null, {
      status: 302,
      headers: {
        Location: '/login?reason=expired',
        'Set-Cookie': 'session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0',
      },
    });
    return expired;
  }

  if (!payload.sub || !payload.role || !payload.jti) {
    return new Response('Forbidden', { status: 403 });
  }

  // Attach the verified user to context.data for downstream handlers
  data.user = {
    sub: payload.sub as string,
    role: payload.role as string,
    jti: payload.jti as string,
  };

  return next();
};
```

---

## Using the Authenticated User in a Downstream Handler

```typescript
// functions/dashboard/index.ts
import type { SessionUser } from './_middleware';

interface Env {
  DB: D1Database;
}

export const onRequestGet: PagesFunction<Env, string, { user: SessionUser }> = async (context) => {
  const { env, data } = context;
  const { sub: userId } = data.user;

  const result = await env.DB.prepare(
    'SELECT * FROM profiles WHERE user_id = ?',
  ).bind(userId).first();

  if (!result) {
    return new Response('Not found', { status: 404 });
  }

  return Response.json(result);
};
```

---

## Role-Based Access Control in Middleware

```typescript
// functions/admin/_middleware.ts — extends the dashboard middleware pattern
import { jwtVerify } from 'jose';

interface Env {
  JWT_SECRET: string;
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env, next, data } = context;

  // Re-use cookie parsing; in a real app import a shared utility
  const cookieHeader = request.headers.get('Cookie');
  const token = cookieHeader?.match(/session=([^;]+)/)?.[1];
  if (!token) return Response.redirect('/login', 302);

  try {
    const { payload } = await jwtVerify(token, new TextEncoder().encode(env.JWT_SECRET), {
      algorithms: ['HS256'],
    });

    if (payload.role !== 'admin') {
      return new Response('Forbidden', { status: 403 });
    }

    (data as any).user = payload;
  } catch {
    return Response.redirect('/login?reason=expired', 302);
  }

  return next();
};
```

---

## Logout Handler

```typescript
// functions/api/logout.ts
export const onRequestPost: PagesFunction = async () => {
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': 'session=; HttpOnly; SameSite=Lax; Secure; Path=/; Max-Age=0',
    },
  });
};
```

---

## Anti-patterns

- **Single global `_middleware.ts` for auth.** A global middleware running on every route
  (including public pages and assets) adds latency. Place auth middleware only in the
  directories that need it (`api/`, `dashboard/`, `admin/`).
- **Storing the session payload in a client-readable cookie.** Always use `HttpOnly`. A
  readable cookie exposes the JWT to XSS.
- **Not setting `SameSite`.** Without `SameSite=Lax` or `Strict`, the session cookie is
  sent on cross-site form POSTs, enabling CSRF.
- **Trusting `context.data.user` without a prior middleware.** If a handler file is
  reached without the middleware running (e.g., the file is outside the middleware's
  directory), `data.user` is undefined. Always null-check or use TypeScript's strict
  optional properties.
- **Using `alg: 'none'` or omitting algorithm restriction in `jwtVerify`.** Always pass
  `{ algorithms: ['HS256'] }` to prevent algorithm confusion attacks.

---

## Gotchas

- Pages Functions middleware does **not** run on static asset requests. A request for
  `/dashboard/logo.png` that Cloudflare serves from the static site will bypass your
  middleware entirely — ensure sensitive assets are served by a function, not as static
  files.
- The `context.next()` call passes control to the next middleware or the final handler.
  Returning early (without calling `next()`) short-circuits the chain.
- `jose` (and other npm packages) must be declared in `package.json` and built with
  Wrangler's Pages Functions bundler — they are not available as globals.
- `JWT_SECRET` must be set as a Pages secret via the dashboard or `wrangler pages secret
  put JWT_SECRET`, not hard-coded in `wrangler.toml`.
- Clock drift between the JWT issuer and the verifier can cause spurious expiry errors.
  The `clockTolerance` option in `jwtVerify` mitigates this.

---

## Verification

```typescript
// tests/middleware.test.ts — using Wrangler's unstable_dev or Miniflare
import { SELF } from 'cloudflare:test';

describe('dashboard middleware', () => {
  it('redirects unauthenticated requests to /login', async () => {
    const res = await SELF.fetch('https://example.com/dashboard/');
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toContain('/login');
  });

  it('allows a valid session through', async () => {
    // mint a valid test token and attach as Cookie header
    const res = await SELF.fetch('https://example.com/dashboard/', {
      headers: { Cookie: `session=${await mintTestToken()}` },
    });
    expect(res.status).toBe(200);
  });
});
```

---

## Related

- `session-fixation-workers-d1-rotation.md`
- `csrf-protection-double-submit.md`
- `jwt-best-practices.md`
- `oauth-pkce-flow.md`
- `cloudflare-access-jwt-assertion-validation.md`

---

## Sources

- Cloudflare Pages Functions middleware — https://developers.cloudflare.com/pages/functions/middleware/
- Cloudflare Pages Functions routing — https://developers.cloudflare.com/pages/functions/routing/
- `jose` library — https://github.com/panva/jose
- RFC 6265 HTTP State Management — https://datatracker.ietf.org/doc/html/rfc6265
