# React Native / Expo App Authenticating Against a Cloudflare Worker API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You are building a React Native (Expo) mobile app and need a secure backend API hosted on Cloudflare Workers. You want JWT-based authentication with server-side sessions stored in KV, token persistence on the device using `expo-secure-store`, and a `fetch` interceptor that automatically attaches the Bearer token and refreshes it transparently on 401 responses.

---

## Context
Cloudflare Workers are an ideal backend for mobile apps: globally distributed, sub-millisecond cold-start, and free-tier generous. Session state sits in Workers KV (low-latency reads), while the JWT is signed with a secret stored in a Worker secret. On the mobile side, `expo-secure-store` persists tokens in the iOS Keychain / Android Keystore, the most secure storage available on each platform. A thin `fetch` wrapper intercepts every request, injects the `Authorization` header, and retries once with a fresh token if the server returns `401`. This removes all auth boilerplate from individual API calls and keeps credential handling in a single place.

---

## Section 1 — wrangler.toml

```toml
name = "mobile-api"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "SESSIONS"
id = "<YOUR_KV_NAMESPACE_ID>"

[vars]
JWT_ISSUER = "https://api.example.com"
ACCESS_TOKEN_TTL_SEC = "900"
REFRESH_TOKEN_TTL_SEC = "2592000"

# Store JWT_SECRET via: wrangler secret put JWT_SECRET
```

---

## Section 2 — Worker implementation

```typescript
// src/index.ts
import { Hono } from 'hono';
import { sign, verify } from 'hono/jwt';

type Bindings = {
  SESSIONS: KVNamespace;
  JWT_SECRET: string;
  JWT_ISSUER: string;
  ACCESS_TOKEN_TTL_SEC: string;
  REFRESH_TOKEN_TTL_SEC: string;
};

const app = new Hono<{ Bindings: Bindings }>();

// ── helpers ────────────────────────────────────────────────────────────────
async function issueTokens(
  userId: string,
  env: Bindings
): Promise<{ accessToken: string; refreshToken: string }> {
  const now = Math.floor(Date.now() / 1000);
  const atTtl = Number(env.ACCESS_TOKEN_TTL_SEC);
  const rtTtl = Number(env.REFRESH_TOKEN_TTL_SEC);

  const accessToken = await sign(
    { sub: userId, iss: env.JWT_ISSUER, iat: now, exp: now + atTtl, type: 'access' },
    env.JWT_SECRET
  );
  const refreshToken = await sign(
    { sub: userId, iss: env.JWT_ISSUER, iat: now, exp: now + rtTtl, type: 'refresh' },
    env.JWT_SECRET
  );

  // persist refresh token in KV so we can invalidate it server-side
  await env.SESSIONS.put(`refresh:${userId}`, refreshToken, {
    expirationTtl: rtTtl,
  });

  return { accessToken, refreshToken };
}

async function requireAuth(
  c: any,
  next: () => Promise<void>
): Promise<Response | void> {
  const auth = c.req.header('Authorization') ?? '';
  if (!auth.startsWith('Bearer ')) {
    return c.json({ error: 'missing_token' }, 401);
  }
  try {
    const payload = await verify(auth.slice(7), c.env.JWT_SECRET);
    if ((payload as any).type !== 'access') throw new Error('wrong token type');
    c.set('userId', (payload as any).sub as string);
  } catch {
    return c.json({ error: 'invalid_token' }, 401);
  }
  await next();
}

// ── routes ─────────────────────────────────────────────────────────────────
app.post('/auth/login', async (c) => {
  const { email, password } = await c.req.json<{ email: string; password: string }>();
  // TODO: validate credentials against your user store (D1, etc.)
  if (!email || !password) return c.json({ error: 'bad_request' }, 400);

  // Stub: replace with real password check
  const userId = `user:${email}`;
  const tokens = await issueTokens(userId, c.env);
  return c.json(tokens);
});

app.post('/auth/refresh', async (c) => {
  const { refreshToken } = await c.req.json<{ refreshToken: string }>();
  let payload: any;
  try {
    payload = await verify(refreshToken, c.env.JWT_SECRET);
    if (payload.type !== 'refresh') throw new Error();
  } catch {
    return c.json({ error: 'invalid_refresh_token' }, 401);
  }

  const stored = await c.env.SESSIONS.get(`refresh:${payload.sub}`);
  if (stored !== refreshToken) {
    return c.json({ error: 'refresh_token_reuse' }, 401); // rotation violation
  }

  const tokens = await issueTokens(payload.sub, c.env);
  return c.json(tokens);
});

app.post('/auth/logout', requireAuth, async (c) => {
  const userId = c.get('userId') as string;
  await c.env.SESSIONS.delete(`refresh:${userId}`);
  return c.json({ ok: true });
});

app.get('/me', requireAuth, (c) => {
  return c.json({ userId: c.get('userId') });
});

export default app;
```

---

## Section 3 — Client-side (React Native / Expo)

```typescript
// lib/apiClient.ts
import * as SecureStore from 'expo-secure-store';

const BASE_URL = 'https://mobile-api.orchords.workers.dev';
const ACCESS_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';

// ── token helpers ──────────────────────────────────────────────────────────
export async function saveTokens(access: string, refresh: string) {
  await SecureStore.setItemAsync(ACCESS_KEY, access);
  await SecureStore.setItemAsync(REFRESH_KEY, refresh);
}

export async function clearTokens() {
  await SecureStore.deleteItemAsync(ACCESS_KEY);
  await SecureStore.deleteItemAsync(REFRESH_KEY);
}

async function getAccessToken() {
  return SecureStore.getItemAsync(ACCESS_KEY);
}

async function getRefreshToken() {
  return SecureStore.getItemAsync(REFRESH_KEY);
}

// ── token refresh ──────────────────────────────────────────────────────────
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) return null;

  const res = await fetch(`${BASE_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refreshToken }),
  });

  if (!res.ok) {
    await clearTokens();
    return null;
  }

  const { accessToken, refreshToken: newRefresh } = await res.json();
  await saveTokens(accessToken, newRefresh);
  return accessToken;
}

// ── intercepted fetch ──────────────────────────────────────────────────────
export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const token = await getAccessToken();

  const headers = new Headers(init.headers);
  headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let res = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  if (res.status === 401) {
    // Deduplicate concurrent refresh calls
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }
    const newToken = await refreshPromise;
    if (!newToken) throw new Error('session_expired');

    headers.set('Authorization', `Bearer ${newToken}`);
    res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  }

  return res;
}

// ── auth helpers ───────────────────────────────────────────────────────────
export async function login(email: string, password: string) {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error('login_failed');
  const { accessToken, refreshToken } = await res.json();
  await saveTokens(accessToken, refreshToken);
}

export async function logout() {
  try {
    await apiFetch('/auth/logout', { method: 'POST' });
  } finally {
    await clearTokens();
  }
}
```

---

## Anti-patterns
- **Storing tokens in AsyncStorage** — AsyncStorage is unencrypted. Always use `expo-secure-store` for credentials.
- **Not deduplicating refresh calls** — concurrent 401s without a shared `refreshPromise` cause a token-rotation race where the second refresh call invalidates the first new token.
- **Signing JWTs client-side** — the secret must never leave the Worker; the client only receives and presents tokens.
- **Infinite refresh loop** — always check `payload.type === 'access'` on protected routes, or a mistakenly forwarded refresh token loops forever.

---

## Gotchas
- `hono/jwt` uses the Web Crypto API under the hood; it is available in the Workers runtime but not in Node.js unit tests without a polyfill.
- `expo-secure-store` values are scoped to the app bundle ID — clearing app data on Android also wipes the keystore entry.
- Refresh token rotation (issuing a new refresh token on each use) means a replay of a used refresh token correctly returns `401`; log this server-side as a possible theft indicator.
- `wrangler secret put JWT_SECRET` stores the value encrypted at rest; never put secrets in `wrangler.toml` `[vars]`.

---

## Verification
```bash
# Deploy the Worker
npx wrangler deploy

# Login
curl -s -X POST https://mobile-api.orchords.workers.dev/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@example.com","password":"secret"}' | jq .

# Call protected route with access token
curl -s https://mobile-api.orchords.workers.dev/me \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq .

# Refresh
curl -s -X POST https://mobile-api.orchords.workers.dev/auth/refresh \
  -H 'Content-Type: application/json' \
  -d "{\"refreshToken\":\"$REFRESH_TOKEN\"}" | jq .
```

---

## Related
- `mobile-push-notifications-workers-queues-fcm.md`
- `offline-first-sync-workers-d1-mobile.md`

---

## Sources
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Hono JWT middleware — https://hono.dev/docs/middleware/builtin/jwt
- Expo SecureStore — https://docs.expo.dev/versions/latest/sdk/securestore/
