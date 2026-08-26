# Expo SecureStore Workers Token Encryption

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

An Expo app receives JWT access tokens and refresh tokens from a Cloudflare Workers auth endpoint. Storing tokens in `AsyncStorage` exposes them to filesystem inspection on rooted/jailbroken devices. You need tokens encrypted at rest using the device's secure enclave (iOS Keychain / Android Keystore) via `expo-secure-store`, while the Workers endpoint issues tokens with a short TTL and signs them with a secret never exposed to the client.

## Context

`expo-secure-store` wraps iOS Keychain Services and Android Keystore. Data is encrypted with AES-256 (Android) or protected under the device's Secure Enclave (iOS). Cloudflare Workers issue HS256 JWTs signed with a `JWT_SECRET` stored as a Worker secret. The client stores opaque tokens in SecureStore; the refresh endpoint validates the refresh token against a D1 allowlist and issues a new access token, invalidating the old refresh token (rotation).

Token lifecycle:

```
POST /auth/login  →  { accessToken (15 min TTL), refreshToken (30 day TTL) }
         ↓
expo-secure-store  →  keys: "access_token", "refresh_token"
         ↓
API request → Authorization: Bearer <accessToken>
         ↓
401 Unauthorized  →  POST /auth/refresh  →  new token pair  →  SecureStore update
```

## Workers Auth Endpoint

```typescript
// workers/auth/index.ts
import { SignJWT, jwtVerify } from "jose";

export interface Env {
  DB: D1Database;
  JWT_SECRET: string; // set via `wrangler secret put JWT_SECRET`
}

function secret(env: Env): Uint8Array {
  return new TextEncoder().encode(env.JWT_SECRET);
}

async function issueTokenPair(
  userId: string,
  env: Env
): Promise<{ accessToken: string; refreshToken: string }> {
  const now = Math.floor(Date.now() / 1000);

  const accessToken = await new SignJWT({ sub: userId, type: "access" })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt(now)
    .setExpirationTime(now + 900) // 15 minutes
    .sign(secret(env));

  const refreshToken = await new SignJWT({ sub: userId, type: "refresh" })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt(now)
    .setExpirationTime(now + 60 * 60 * 24 * 30) // 30 days
    .sign(secret(env));

  // Store refresh token hash in D1 (never store plain token)
  const hash = btoa(String.fromCharCode(...new Uint8Array(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(refreshToken))
  )));
  await env.DB.prepare(
    "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)"
  ).bind(userId, hash, now + 60 * 60 * 24 * 30).run();

  return { accessToken, refreshToken };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/auth/login") {
      const { email, password } = await request.json<{ email: string; password: string }>();
      // Validate credentials against DB (implementation omitted)
      const user = await env.DB.prepare(
        "SELECT id FROM users WHERE email = ? AND password_hash = hash(?)"
      ).bind(email, password).first<{ id: string }>();

      if (!user) return new Response("Invalid credentials", { status: 401 });

      const tokens = await issueTokenPair(user.id, env);
      return Response.json(tokens);
    }

    if (request.method === "POST" && url.pathname === "/auth/refresh") {
      const { refreshToken } = await request.json<{ refreshToken: string }>();

      let payload: { sub: string; type: string };
      try {
        const verified = await jwtVerify(refreshToken, secret(env));
        payload = verified.payload as { sub: string; type: string };
      } catch {
        return new Response("Invalid token", { status: 401 });
      }

      if (payload.type !== "refresh") return new Response("Wrong token type", { status: 401 });

      // Verify token hash exists (rotation: delete old, issue new)
      const hash = btoa(String.fromCharCode(...new Uint8Array(
        await crypto.subtle.digest("SHA-256", new TextEncoder().encode(refreshToken))
      )));
      const row = await env.DB.prepare(
        "DELETE FROM refresh_tokens WHERE user_id = ? AND token_hash = ? AND expires_at > ? RETURNING user_id"
      ).bind(payload.sub, hash, Math.floor(Date.now() / 1000)).first<{ user_id: string }>();

      if (!row) return new Response("Token reuse detected", { status: 401 });

      const tokens = await issueTokenPair(payload.sub, env);
      return Response.json(tokens);
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

## D1 Schema

```sql
-- migrations/0001_auth.sql
CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  user_id    TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, token_hash)
);
```

## Expo SecureStore Token Manager

```typescript
// src/auth/tokenStore.ts
import * as SecureStore from "expo-secure-store";

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

// SecureStore options: require device authentication for high-sensitivity apps
const STORE_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export async function saveTokens(access: string, refresh: string): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, access, STORE_OPTIONS),
    SecureStore.setItemAsync(REFRESH_KEY, refresh, STORE_OPTIONS),
  ]);
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_KEY, STORE_OPTIONS);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_KEY, STORE_OPTIONS);
}

export async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY, STORE_OPTIONS),
    SecureStore.deleteItemAsync(REFRESH_KEY, STORE_OPTIONS),
  ]);
}
```

## Authenticated Fetch with Auto-Refresh

```typescript
// src/auth/authFetch.ts
import { getAccessToken, getRefreshToken, saveTokens, clearTokens } from "./tokenStore";

const WORKERS_BASE = "https://api.example.com";

let isRefreshing = false;
let refreshQueue: Array<(token: string | null) => void> = [];

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) return null;

  const res = await fetch(`${WORKERS_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken }),
  });

  if (!res.ok) {
    await clearTokens();
    return null;
  }

  const { accessToken, refreshToken: newRefresh } = await res.json<{
    accessToken: string;
    refreshToken: string;
  }>();
  await saveTokens(accessToken, newRefresh);
  return accessToken;
}

export async function authFetch(
  input: RequestInfo,
  init: RequestInit = {}
): Promise<Response> {
  let token = await getAccessToken();

  const makeRequest = (t: string | null) =>
    fetch(input, {
      ...init,
      headers: {
        ...(init.headers as Record<string, string>),
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
      },
    });

  let res = await makeRequest(token);
  if (res.status !== 401) return res;

  // Token expired — refresh once
  if (!isRefreshing) {
    isRefreshing = true;
    token = await refreshAccessToken();
    isRefreshing = false;
    refreshQueue.forEach((cb) => cb(token));
    refreshQueue = [];
  } else {
    // Queue concurrent requests while refresh is in flight
    token = await new Promise<string | null>((resolve) => {
      refreshQueue.push(resolve);
    });
  }

  if (!token) throw new Error("Session expired");
  return makeRequest(token);
}
```

## Anti-patterns

- **Storing tokens in AsyncStorage**: it writes to plain text on-disk, readable without root on some Android versions. Always use `expo-secure-store`.
- **Long-lived access tokens**: a 15-minute TTL limits the blast radius of a leaked access token. Never issue access tokens valid for 24+ hours.
- **Storing the plain refresh token in D1**: only store a SHA-256 hash. If D1 is compromised, refresh tokens remain non-replayable.
- **Re-using refresh tokens**: without rotation (delete-on-use), a stolen refresh token can be used indefinitely. The Workers endpoint deletes the token hash before issuing a new pair.

## Gotchas

- `expo-secure-store` is not available in Expo Go on physical devices for biometric-protected keys. Build a development client with `expo run:ios` / `expo run:android`.
- `WHEN_UNLOCKED_THIS_DEVICE_ONLY` prevents iCloud Keychain backup (iOS). Use `WHEN_UNLOCKED` if cross-device token sharing is acceptable.
- SecureStore has a 2 KB value size limit. JWTs can exceed this if you embed large claims. Keep the access token payload minimal; put roles/permissions behind a separate `/me` endpoint.
- On Android API 23 and below, the Android Keystore may not be hardware-backed. `expo-secure-store` falls back to EncryptedSharedPreferences in that case — still encrypted, but without a secure enclave.
- The `jose` library (`npm i jose`) is required in the Worker. It supports the Web Crypto API used in the Workers runtime; do not use `jsonwebtoken` (Node-only).

## Verification

```bash
# 1. Deploy Worker with JWT_SECRET set
wrangler secret put JWT_SECRET
wrangler deploy

# 2. Test login
curl -X POST https://api.example.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"secret"}'

# 3. Test refresh
curl -X POST https://api.example.com/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refreshToken":"<refresh_token_from_above>"}'

# 4. Confirm old refresh token is invalidated (token reuse detection)
# Re-sending the same refresh token should return 401 "Token reuse detected"
```

## Related

- `react-native-workers-biometric-auth-secure-enclave.md`
- `react-native-secure-storage.md`
- `mobile-jwt-storage-pitfalls.md`
- `ios-keychain-storage.md`
- `biometric-auth.md`

## Sources

- https://docs.expo.dev/versions/latest/sdk/securestore/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/d1/
- https://github.com/panva/jose
