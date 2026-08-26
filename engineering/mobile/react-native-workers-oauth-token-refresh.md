# React Native Workers OAuth Token Refresh Flow

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Access tokens expire (typically 15–60 min). Without a coordinated refresh flow, multiple in-flight requests each independently detect the 401, race to POST `/token`, and only one succeeds while the others invalidate the refresh token, locking the user out. Workers acts as the OAuth proxy — it holds client secrets, calls the upstream IdP, and issues short-lived JWTs to the mobile client.

## Context

The canonical pattern is a **refresh lock**: a single promise that all callers await. The Workers endpoint accepts the refresh token, exchanges it with the upstream IdP (Auth0, Cognito, custom), and returns new tokens. The mobile client stores the refresh token in the secure enclave (Keychain/Keystore), never in AsyncStorage.

Architecture:
```
RN app → Workers /auth/refresh → IdP token endpoint
                    ↓
              KV: session state (optional rate-limit)
```

---

## Workers Token Refresh Endpoint

```typescript
// workers/src/auth/refresh.ts
import { Env } from '../types';

interface TokenRequest {
  refresh_token: string;
  client_id: string;
}

interface IdPTokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

export async function handleTokenRefresh(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<TokenRequest>();

  if (!body.refresh_token || !body.client_id) {
    return Response.json({ error: 'invalid_request' }, { status: 400 });
  }

  // Rate-limit: one refresh per client per 30s using KV
  const rateLimitKey = `rl:refresh:${body.client_id}`;
  const existing = await env.KV_AUTH.get(rateLimitKey);
  if (existing) {
    return Response.json(
      { error: 'too_many_requests', retry_after: 30 },
      { status: 429 }
    );
  }

  const idpResponse = await fetch(`${env.IDP_TOKEN_URL}/oauth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: body.refresh_token,
      client_id: env.OAUTH_CLIENT_ID,
      client_secret: env.OAUTH_CLIENT_SECRET,
    }),
  });

  if (!idpResponse.ok) {
    const err = await idpResponse.json<{ error: string }>();
    return Response.json({ error: err.error }, { status: 401 });
  }

  const tokens = await idpResponse.json<IdPTokenResponse>();

  // Set rate-limit window
  await env.KV_AUTH.put(rateLimitKey, '1', { expirationTtl: 30 });

  return Response.json({
    access_token: <redacted-secret>
    refresh_token: tokens.refresh_token,
    expires_in: tokens.expires_in,
  });
}
```

## React Native Refresh Lock (Race Prevention)

```typescript
// src/auth/tokenRefresh.ts
import * as Keychain from 'react-native-keychain';

const WORKERS_BASE = 'https://api.example.com';

let refreshPromise: Promise<string> | null = null;

async function performRefresh(): Promise<string> {
  const creds = await Keychain.getGenericPassword({ service: 'refresh_token' });
  if (!creds) throw new Error('NO_REFRESH_TOKEN');

  const res = await fetch(`${WORKERS_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      refresh_token: creds.password,
      client_id: creds.username,
    }),
  });

  if (res.status === 429) {
    const { retry_after } = await res.json<{ retry_after: number }>();
    await new Promise(r => setTimeout(r, retry_after * 1000));
    return performRefresh();
  }

  if (!res.ok) {
    throw new Error('REFRESH_FAILED');
  }

  const { access_token, refresh_token, expires_in } = await res.json<{
    access_token: string;
    refresh_token: string;
    expires_in: number;
  }>();

  // Persist new tokens
  await Keychain.setGenericPassword(creds.username, refresh_token, {
    service: 'refresh_token',
  });

  tokenStore.setToken(access_token, Date.now() + expires_in * 1000);
  return access_token;
}

/**
 * getValidToken: returns a valid access token, refreshing if needed.
 * Multiple simultaneous callers share one refresh attempt.
 */
export async function getValidToken(): Promise<string> {
  if (tokenStore.isValid()) {
    return tokenStore.getToken()!;
  }

  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }

  return refreshPromise;
}
```

## In-Memory Token Store with Clock Skew Buffer

```typescript
// src/auth/tokenStore.ts
const SKEW_BUFFER_MS = 30_000; // refresh 30s before actual expiry

let _token: string | null = null;
let _expiresAt: number = 0;

export const tokenStore = {
  setToken(token: string, expiresAt: number) {
    _token = token;
    _expiresAt = expiresAt;
  },
  isValid(): boolean {
    return !!_token && Date.now() < _expiresAt - SKEW_BUFFER_MS;
  },
  getToken(): string | null {
    return _token;
  },
  clear() {
    _token = null;
    _expiresAt = 0;
  },
};
```

## Axios Interceptor Pattern

```typescript
// src/api/axiosInstance.ts
import axios, { AxiosInstance, AxiosError } from 'axios';
import { getValidToken } from '../auth/tokenRefresh';
import { tokenStore } from '../auth/tokenStore';

export function createApiClient(baseURL: string): AxiosInstance {
  const client = axios.create({ baseURL });

  // Attach token to every request
  client.interceptors.request.use(async config => {
    const token = await getValidToken();
    config.headers['Authorization'] = `Bearer ${token}`;
    return config;
  });

  // On 401: refresh once and retry
  client.interceptors.response.use(
    res => res,
    async (error: AxiosError) => {
      const original = error.config as typeof error.config & {
        _retried?: boolean;
      };

      if (error.response?.status === 401 && !original._retried) {
        original._retried = true;
        tokenStore.clear(); // force refresh on next getValidToken call

        try {
          const token = await getValidToken();
          original!.headers!['Authorization'] = `Bearer ${token}`;
          return client(original!);
        } catch {
          // Refresh failed — sign out
          tokenStore.clear();
          throw error;
        }
      }

      throw error;
    }
  );

  return client;
}
```

## Workers KV — Session Invalidation on Logout

```typescript
// workers/src/auth/logout.ts
export async function handleLogout(
  request: Request,
  env: Env
): Promise<Response> {
  const auth = request.headers.get('Authorization');
  if (!auth?.startsWith('Bearer ')) {
    return Response.json({ error: 'unauthorized' }, { status: 401 });
  }

  const { sub } = decodeJWTPayload(auth.slice(7));

  // Blocklist the sub until token expiry
  await env.KV_AUTH.put(`blocklist:${sub}`, '1', { expirationTtl: 3600 });

  return Response.json({ success: true });
}

function decodeJWTPayload(token: string): { sub: string } {
  const [, payload] = token.split('.');
  return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
}
```

---

## Anti-patterns

- **Storing refresh tokens in AsyncStorage** — unencrypted, readable by any JS code in the bundle. Always use Keychain (iOS) or EncryptedSharedPreferences (Android).
- **No refresh lock** — parallel requests each try to refresh, burning the single-use refresh token. The promise-singleton pattern above prevents this.
- **Refreshing inside every component** — refresh logic belongs in a single auth module, not scattered across screens.
- **Not clearing the token on 401 before retrying** — causes an infinite retry loop if the Workers endpoint itself returns a 401 on stale tokens.
- **Trusting `expires_in` without a skew buffer** — Workers may have slight clock differences from the IdP; buffer 30 s.

---

## Gotchas

- **KV eventual consistency** — the rate-limit key may not be immediately visible across all Workers instances; brief double-refresh is possible within the eventual-consistency window (~60 ms). This is acceptable for token operations.
- **Keychain access on locked device (iOS)** — if the app is in background and the device is locked, `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` will fail. Use `kSecAttrAccessibleAfterFirstUnlock` for background-capable refresh.
- **React Native New Architecture (Fabric)** — `react-native-keychain` ≥ 9.x is required for JSI support; older versions may freeze the JS thread on the bridge.
- **Workers `fetch()` timeout** — default is 30 s; IdP token endpoints occasionally slow down. Wrap with `Promise.race` and a `AbortController` if sub-5 s latency is required.

---

## Verification

```bash
# Confirm 429 on rapid double-refresh
curl -X POST https://api.example.com/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<rt>","client_id":"<id>"}' && \
curl -X POST https://api.example.com/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<rt>","client_id":"<id>"}'
# Second call should return 429

# Simulate 401 and check retry fires once
# Set a breakpoint on _retried flag in interceptor
```

---

## Related

- `react-native-anonymous-session-refresh-workers-jwt.md`
- `react-native-workers-hmac-signed-requests.md`
- `mobile-jwt-storage-pitfalls.md`
- `react-native-keychain.md`
- `mobile-auth-oauth-pkce.md`

---

## Sources

- Cloudflare Workers KV docs — https://developers.cloudflare.com/kv/
- RFC 6749 §6 Refreshing an Access Token — https://datatracker.ietf.org/doc/html/rfc6749#section-6
- react-native-keychain — https://github.com/oblador/react-native-keychain
- Axios interceptors — https://axios-http.com/docs/interceptors
