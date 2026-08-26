# Cloudflare Pages Middleware for Auth-Gated Routes

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You want to protect all routes under `/app` with a session cookie check that runs before any Page Function executes. On a valid session the middleware forwards the request with the decoded user identity in a request header; on an invalid or missing cookie it issues a 302 redirect to `/login`. The check must run entirely at the edge with no origin round-trip.

---

## Context
Cloudflare Pages Functions support middleware via files named `_middleware.ts` placed in a directory under `functions/`. A `_middleware.ts` at `functions/app/_middleware.ts` intercepts every request whose path begins with `/app`. The middleware reads a `session` cookie, verifies its HMAC signature with `crypto.subtle.verify` using a secret stored in a Worker secret binding, and either passes the request through with an `X-User` header or redirects to `/login`. Downstream Page Functions (e.g. `functions/app/dashboard.ts`) read `X-User` from the incoming request without re-verifying, trusting the middleware chain. Signed cookies avoid the need for a KV round-trip on every request.

---

## Section 1 — Project Structure and Wrangler Config

Directory layout
```
functions/
  app/
    _middleware.ts      ← auth guard for all /app/* routes
    dashboard.ts        ← example downstream function
    profile.ts
  login.ts
wrangler.toml
```

`wrangler.toml`
```toml
name = "my-pages-app"
compatibility_date = "2024-09-23"
pages_build_output_dir = "dist"

# Store the signing secret as a secret, not a plain var:
# wrangler pages secret put SESSION_SECRET --project-name my-pages-app
[vars]
SESSION_COOKIE_NAME = "__session"
```

Set the signing secret (run once)
```bash
wrangler pages secret put SESSION_SECRET --project-name my-pages-app
# Paste a 32-byte random hex string when prompted
# e.g.: openssl rand -hex 32
```

---

## Section 2 — Cookie Signing Utilities

`functions/_shared/cookie-crypto.ts`
```typescript
// HMAC-SHA256 signing and verification for session cookies.
// Cookie format: <base64url(payload)>.<base64url(signature)>

const ALGO = { name: 'HMAC', hash: 'SHA-256' } as const;

function base64url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function base64urlDecode(str: string): Uint8Array {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/').padEnd(
    str.length + ((4 - (str.length % 4)) % 4),
    '='
  );
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

async function importKey(secret: string): Promise<CryptoKey> {
  const raw = new TextEncoder().encode(secret);
  return crypto.subtle.importKey('raw', raw, ALGO, false, ['sign', 'verify']);
}

export async function signPayload(
  payload: Record<string, unknown>,
  secret: string
): Promise<string> {
  const key = await importKey(secret);
  const encoded = base64url(new TextEncoder().encode(JSON.stringify(payload)));
  const sig = await crypto.subtle.sign(ALGO, key, new TextEncoder().encode(encoded));
  return `${encoded}.${base64url(sig)}`;
}

export async function verifyAndDecode(
  cookie: string,
  secret: string
): Promise<Record<string, unknown> | null> {
  const dot = cookie.lastIndexOf('.');
  if (dot === -1) return null;

  const encoded = cookie.slice(0, dot);
  const sigBytes = base64urlDecode(cookie.slice(dot + 1));

  const key = await importKey(secret);
  const valid = await crypto.subtle.verify(
    ALGO,
    key,
    sigBytes,
    new TextEncoder().encode(encoded)
  );
  if (!valid) return null;

  try {
    return JSON.parse(new TextDecoder().decode(base64urlDecode(encoded))) as Record<
      string,
      unknown
    >;
  } catch {
    return null;
  }
}
```

---

## Section 3 — Middleware and Downstream Function

`functions/app/_middleware.ts`
```typescript
import { verifyAndDecode } from '../_shared/cookie-crypto';

interface Env {
  SESSION_SECRET: string;
  SESSION_COOKIE_NAME: string;
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env, next } = context;
  const cookieName = env.SESSION_COOKIE_NAME ?? '__session';

  // Parse the Cookie header
  const cookieHeader = request.headers.get('Cookie') ?? '';
  const cookies = Object.fromEntries(
    cookieHeader.split(';').map((c) => {
      const [k, ...v] = c.trim().split('=');
      return [k, v.join('=')];
    })
  );

  const rawSession = cookies[cookieName];
  if (!rawSession) {
    return redirectToLogin(request.url);
  }

  const payload = await verifyAndDecode(rawSession, env.SESSION_SECRET);
  if (!payload) {
    return redirectToLogin(request.url);
  }

  // Optionally enforce session expiry stored in payload
  if (typeof payload.exp === 'number' && Date.now() / 1000 > payload.exp) {
    return redirectToLogin(request.url);
  }

  // Forward user identity to downstream Page Functions via a request header.
  // Clone the request and inject X-User so downstream code can trust it.
  const userId = String(payload.sub ?? payload.userId ?? '');
  const mutatedRequest = new Request(request, {
    headers: new Headers({
      ...Object.fromEntries(request.headers.entries()),
      'X-User': userId,
      'X-User-Email': String(payload.email ?? ''),
    }),
  });

  return next(mutatedRequest);
};

function redirectToLogin(originalUrl: string): Response {
  const loginUrl = new URL('/login', originalUrl);
  loginUrl.searchParams.set(
    'next',
    new URL(originalUrl).pathname + new URL(originalUrl).search
  );
  return Response.redirect(loginUrl.toString(), 302);
}
```

`functions/app/dashboard.ts`
```typescript
// The _middleware.ts above guarantees this function only runs
// for authenticated requests. Read identity from headers.

export const onRequestGet: PagesFunction = async ({ request }) => {
  const userId = request.headers.get('X-User');
  const email = request.headers.get('X-User-Email');

  return new Response(
    JSON.stringify({ message: `Hello ${email ?? userId}`, userId }),
    { headers: { 'Content-Type': 'application/json' } }
  );
};
```

`functions/login.ts` — issue a signed session cookie on successful credential check
```typescript
import { signPayload } from './_shared/cookie-crypto';

interface Env {
  SESSION_SECRET: string;
  SESSION_COOKIE_NAME: string;
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  const body = await request.json<{ username: string; password: string }>();

  // Replace with real credential validation (e.g. D1 lookup + bcrypt)
  if (body.username !== 'demo' || body.password !== 'secret') {
    return new Response(JSON.stringify({ error: 'Invalid credentials' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const expiresInSeconds = 60 * 60 * 24; // 24 h
  const payload = {
    sub: 'user_123',
    email: body.username + '@example.com',
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + expiresInSeconds,
  };

  const signed = await signPayload(payload, env.SESSION_SECRET);
  const cookieName = env.SESSION_COOKIE_NAME ?? '__session';

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': [
        `${cookieName}=${signed}`,
        'Path=/',
        'HttpOnly',
        'Secure',
        'SameSite=Lax',
        `Max-Age=${expiresInSeconds}`,
      ].join('; '),
    },
  });
};
```

---

## Anti-patterns
- **Storing the session payload unencrypted in the cookie** — Even a signed cookie exposes payload contents to the client; if the payload includes sensitive fields, encrypt with `crypto.subtle.encrypt` (AES-GCM) before base64-encoding.
- **Using a plain `var` for `SESSION_SECRET`** — Secrets must be set via `wrangler pages secret put` so they do not appear in `wrangler.toml` or version control.
- **Trusting `X-User` in client-facing endpoints** — The `X-User` header is an internal convention between middleware and downstream functions; strip it from any external response to prevent header leakage.
- **Not including `next` in the request parameter** — Forgetting to call `next(mutatedRequest)` causes the middleware to drop the request silently; always return `next()`.

---

## Gotchas
- `new Request(existing, { headers: newHeaders })` replaces the entire headers object; use `new Headers({ ...Object.fromEntries(existing.headers.entries()), ...additions })` to merge rather than overwrite.
- Cloudflare Pages Functions execute in the Workers runtime, not Node.js; do not use `jsonwebtoken` or other Node-only JWT libraries — use `crypto.subtle` directly as shown.
- A `_middleware.ts` at `functions/app/` does **not** intercept requests to `/app` itself (no trailing slash); add a redirect rule in `_redirects` if the root `/app` path needs protecting.
- `crypto.subtle.verify` returns `false` (not throws) for invalid signatures; always check the boolean return value explicitly.

---

## Verification
```bash
# Set secret for local dev (written to .dev.vars)
echo 'SESSION_SECRET=your-32-byte-hex-secret' >> .dev.vars
echo 'SESSION_COOKIE_NAME=__session' >> .dev.vars

# Run Pages Functions locally
wrangler pages dev dist --compatibility-date 2024-09-23

# Attempt unauthenticated access — expect redirect to /login
curl -I http://localhost:8788/app/dashboard
# HTTP/1.1 302 Found
# Location: /login?next=%2Fapp%2Fdashboard

# Log in and capture the cookie
curl -c cookies.txt -X POST http://localhost:8788/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"secret"}'

# Access protected route with the session cookie
curl -b cookies.txt http://localhost:8788/app/dashboard
# {"message":"Hello demo@example.com","userId":"user_123"}

# Deploy
wrangler pages deploy dist --project-name my-pages-app
```

---

## Related
- `svelte-sveltekit-cloudflare-pages-adapter.md`
- `react-server-components-cloudflare-pages.md`
- `workers-html-streaming-rewriter-esi.md`

---

## Sources
- Cloudflare Pages Functions middleware — https://developers.cloudflare.com/pages/functions/middleware/
- Web Crypto API (HMAC) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/verify
- Cloudflare Pages secrets — https://developers.cloudflare.com/pages/functions/bindings/#secrets
