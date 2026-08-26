# FedCM — Federated Credential Management with Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to offer "Sign in with Google / GitHub / Apple" without third-party cookies or
pop-ups, using the browser's native identity picker (FedCM). The challenge is validating
the resulting ID token server-side in a Cloudflare Worker, exchanging it for a session
cookie, and storing the user record in D1 — all without running Node.js.

---

## Context

Federated Credential Management (FedCM) is a browser API that replaces the old pop-up and
redirect OAuth flows with a first-party browser-mediated prompt. The browser contacts the
Identity Provider (IdP) directly, returns a signed ID token to the Relying Party (RP), and
the RP's backend validates that token. This removes the need for third-party cookies in
federated login flows. Cloudflare Workers act as the RP backend: validating tokens using
the Web Crypto API, creating sessions in KV, and recording users in D1.

---

## Feature Detection

```typescript
// src/lib/fedcm.ts
export function isFedCMSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'IdentityCredential' in window &&
    navigator.credentials !== undefined
  );
}

export type FedCMProvider = {
  configURL: string;
  clientId: string;
  nonce?: string;
};
```

---

## Browser — Requesting a Federated Credential

```typescript
// src/auth/fedcmLogin.ts
import { isFedCMSupported } from '../lib/fedcm';

const GOOGLE_CONFIG_URL = 'https://accounts.google.com/gsi/fedcm.json';

export async function signInWithFedCM(
  clientId: string,
  nonce: string
): Promise<string | null> {
  if (!isFedCMSupported()) return null;

  try {
    const credential = (await navigator.credentials.get({
      identity: {
        providers: [
          {
            configURL: GOOGLE_CONFIG_URL,
            clientId,
            nonce,
          },
        ],
        context: 'signin', // or 'signup', 'use', 'continue'
      },
    } as CredentialRequestOptions)) as IdentityCredential | null;

    return credential?.token ?? null;
  } catch (err) {
    if ((err as DOMException).name === 'NotAllowedError') {
      // User dismissed the prompt
      return null;
    }
    throw err;
  }
}

export async function signInAndExchange(clientId: string): Promise<boolean> {
  // Get a nonce from server to prevent replay attacks
  const nonceRes = await fetch('/api/auth/nonce');
  const { nonce } = (await nonceRes.json()) as { nonce: string };

  const token = await signInWithFedCM(clientId, nonce);
  if (!token) return false;

  // Exchange ID token for session cookie at Worker endpoint
  const res = await fetch('/api/auth/fedcm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, nonce }),
  });

  return res.ok;
}
```

---

## Cloudflare Worker — Nonce Endpoint

```typescript
// workers/auth/nonce.ts  (GET /api/auth/nonce)
import { Hono } from 'hono';

type Env = { KV: KVNamespace };
const app = new Hono<{ Bindings: Env }>();

app.get('/api/auth/nonce', async (c) => {
  // Generate a cryptographically random nonce
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const nonce = btoa(String.fromCharCode(...bytes))
    .replace(/[+/=]/g, (m) => ({ '+': '-', '/': '_', '=': '' }[m] ?? m));

  // Store nonce with 5-minute TTL to prevent replay
  await c.env.KV.put(`nonce:${nonce}`, '1', { expirationTtl: 300 });

  return c.json({ nonce });
});

export default app;
```

---

## Cloudflare Worker — Token Validation + Session Creation

```typescript
// workers/auth/fedcm.ts  (POST /api/auth/fedcm)
import { Hono } from 'hono';
import { jwtVerify, createRemoteJWKSet } from 'jose'; // bundled, no Node deps

type Env = {
  KV: KVNamespace;
  DB: D1Database;
  GOOGLE_CLIENT_ID: string;
  SESSION_SECRET: string;
};

const GOOGLE_JWKS = createRemoteJWKSet(
  new URL('https://www.googleapis.com/oauth2/v3/certs')
);

const app = new Hono<{ Bindings: Env }>();

app.post('/api/auth/fedcm', async (c) => {
  const { token, nonce } = await c.req.json<{ token: string; nonce: string }>();

  // 1. Verify nonce exists and consume it (one-time use)
  const storedNonce = await c.env.KV.get(`nonce:${nonce}`);
  if (!storedNonce) {
    return c.json({ error: 'Invalid or expired nonce' }, 401);
  }
  await c.env.KV.delete(`nonce:${nonce}`);

  // 2. Verify the Google ID token
  let payload: Record<string, unknown>;
  try {
    const { payload: p } = await jwtVerify(token, GOOGLE_JWKS, {
      audience: c.env.GOOGLE_CLIENT_ID,
      issuer: ['https://accounts.google.com', 'accounts.google.com'],
    });
    payload = p as Record<string, unknown>;
  } catch {
    return c.json({ error: 'Invalid token' }, 401);
  }

  // Validate nonce inside the JWT matches what we issued
  if ((payload['nonce'] as string) !== nonce) {
    return c.json({ error: 'Nonce mismatch' }, 401);
  }

  const sub = payload['sub'] as string;
  const email = payload['email'] as string;
  const name = payload['name'] as string | undefined;

  // 3. Upsert user in D1
  await c.env.DB.prepare(`
    INSERT INTO users (google_sub, email, name, last_login)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT (google_sub) DO UPDATE
    SET email = excluded.email, name = excluded.name, last_login = CURRENT_TIMESTAMP
  `).bind(sub, email, name ?? null).run();

  // 4. Create session in KV
  const sessionId = crypto.randomUUID();
  await c.env.KV.put(
    `session:${sessionId}`,
    JSON.stringify({ sub, email }),
    { expirationTtl: 60 * 60 * 24 * 7 } // 7 days
  );

  // 5. Set HttpOnly session cookie
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': [
        `sid=${sessionId}`,
        'Path=/',
        'HttpOnly',
        'Secure',
        'SameSite=Lax',
        'Max-Age=604800',
      ].join('; '),
    },
  });
});

export default app;
```

---

## Session Middleware

```typescript
// workers/middleware/session.ts
import { Context, Next } from 'hono';

export async function sessionMiddleware(
  c: Context<{ Bindings: { KV: KVNamespace } }>,
  next: Next
) {
  const cookieHeader = c.req.header('cookie') ?? '';
  const sidMatch = cookieHeader.match(/(?:^|;\s*)sid=([^;]+)/);
  const sessionId = sidMatch?.[1];

  if (sessionId) {
    const raw = await c.env.KV.get(`session:${sessionId}`);
    if (raw) {
      c.set('user', JSON.parse(raw) as { sub: string; email: string });
    }
  }

  await next();
}
```

---

## Progressive Enhancement — Fallback to Redirect OAuth

```typescript
// src/auth/login.ts
import { signInAndExchange } from './fedcmLogin';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export async function login(): Promise<void> {
  const success = await signInAndExchange(GOOGLE_CLIENT_ID);

  if (!success) {
    // FedCM unavailable or dismissed — fall back to redirect flow
    const params = new URLSearchParams({
      client_id: GOOGLE_CLIENT_ID,
      redirect_uri: `${location.origin}/api/auth/google/callback`,
      response_type: 'code',
      scope: 'openid email profile',
    });
    location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
  }
}
```

---

## Anti-patterns

- **Skipping nonce validation** — without a server-issued, one-time nonce inside the JWT, replay attacks are trivial.
- **Accepting tokens without audience check** — always verify `aud === YOUR_CLIENT_ID`; tokens for other clients must be rejected.
- **Storing session data client-side** — always use an opaque session ID in the cookie backed by KV; never put sub/email in the cookie value.
- **Calling `navigator.credentials.get()` on page load** — FedCM prompts must be initiated by a user gesture (click) in most browser implementations.
- **Not handling `NotAllowedError`** — the user can dismiss the prompt; treat that as a non-error and show a fallback.

---

## Gotchas

- FedCM requires `https` even on `localhost`; use `wrangler pages dev --local-protocol https` for local development.
- Google's FedCM config URL (`accounts.google.com/gsi/fedcm.json`) must be reachable from the browser, not the Worker.
- `jose` must be bundled without Node.js crypto polyfills — use `jose`'s browser/edge build and verify it works under `wrangler dev`.
- The `context` field in the identity request affects the button label shown in the browser sheet; use `'signup'` for registration flows.
- Safari's FedCM support (added in Safari 17.4) does not yet support the `context` field — feature-detect before passing it.

---

## Verification

```bash
# Confirm nonce endpoint
curl -s https://staging.example.workers.dev/api/auth/nonce
# → {"nonce":"<base64url>"}

# Check KV contains nonce (expires in 5 min)
wrangler kv key get --binding=KV "nonce:<value>"

# After browser FedCM flow, verify session cookie is HttpOnly
curl -I https://staging.example.workers.dev/api/me
# → Set-Cookie: sid=...; HttpOnly; Secure; SameSite=Lax

# D1 user upsert check
wrangler d1 execute DB --command "SELECT * FROM users ORDER BY last_login DESC LIMIT 5;"
```

---

## Related

- `credential-management-api-cloudflare-workers.md`
- `webauthn-conditional-mediation-autofill.md`
- `cloudflare-pages-middleware-auth-gating.md`
- `cloudflare-pages-functions-session-validation-middleware.md`
- `feature-flags-cloudflare-workers-kv-edge-config.md`

---

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/FedCM_API
- https://developers.google.com/privacy-sandbox/cookies/fedcm
- https://w3c-fedid.github.io/FedCM/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
