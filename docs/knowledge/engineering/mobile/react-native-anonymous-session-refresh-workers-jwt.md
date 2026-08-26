# React Native Anonymous Session Refresh with Cloudflare Workers JWT

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project users are anonymous by design. The app issues short-lived JWTs (15 min TTL) that encode a stable anonymous identity — a deterministic `anonId` derived from device attestation. When a token expires mid-feed, the UX hard-stops with a 401. You need silent background refresh that keeps the user in-flow, with no username or password involved.

Symptoms that bring you here:
- `401 Unauthorized` bursts in prod logs every 15 minutes
- Concurrent requests all try to refresh simultaneously, causing a token stampede
- Refresh tokens stored in `AsyncStorage` are readable by Hermes debugger or other apps on non-SELinux devices
- On iOS the app backgrounded just before token expiry; on foreground the refresh is stale

---

## Context

The example project auth model:
- Device fingerprint → Cloudflare Worker `/auth/anon` → signed JWT (`RS256`) + refresh token (opaque, stored in D1)
- JWT payload: `{ sub: anonId, iat, exp, tier: "anon" }`
- Refresh token TTL: 30 days, rotated on every use (refresh-token rotation)
- Cloudflare Worker `/auth/refresh` validates the opaque token against D1, issues new JWT + new refresh token, invalidates old refresh token
- React Native client must use `react-native-keychain` for refresh token storage, never `AsyncStorage`

Stack: React Native 0.76+ (New Architecture), TypeScript, `react-native-keychain`, `axios` with interceptors, Zustand for auth state.

---

## Token Storage with react-native-keychain

Never store refresh tokens in `AsyncStorage`. Use the Keychain (iOS Keychain / Android Keystore-backed Keychain).

```typescript
// src/auth/tokenStorage.ts
import * as Keychain from 'react-native-keychain';

const SERVICE_NAME = 'com.example project.app.refreshToken';

export async function saveRefreshToken(token: string): Promise<void> {
  await Keychain.setGenericPassword('example project_anon', token, {
    service: SERVICE_NAME,
    accessible: Keychain.ACCESSIBLE.AFTER_FIRST_UNLOCK, // survives device restart
    securityLevel: Keychain.SECURITY_LEVEL.SECURE_HARDWARE, // Android Strongbox / iOS Secure Enclave
  });
}

export async function loadRefreshToken(): Promise<string | null> {
  const creds = await Keychain.getGenericPassword({ service: SERVICE_NAME });
  if (!creds) return null;
  return creds.password;
}

export async function deleteRefreshToken(): Promise<void> {
  await Keychain.resetGenericPassword({ service: SERVICE_NAME });
}
```

---

## Cloudflare Worker: /auth/refresh Endpoint

```typescript
// workers/src/auth/refresh.ts
import { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  JWT_PRIVATE_KEY: string; // RS256 private key in PEM, stored as Worker secret
}

export async function handleRefresh(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{ refreshToken: string }>();
  const { refreshToken } = body;

  if (!refreshToken) {
    return new Response(JSON.stringify({ error: 'missing_token' }), { status: 400 });
  }

  // Lookup and rotate in a single transaction
  const result = await env.DB.prepare(
    `UPDATE anon_refresh_tokens
     SET token = ?1, rotated_at = unixepoch()
     WHERE token = ?2
       AND expires_at > unixepoch()
       AND revoked = 0
     RETURNING anon_id, token AS new_token`
  )
    .bind(generateOpaqueToken(), refreshToken)
    .first<{ anon_id: string; new_token: string }>();

  if (!result) {
    // Token not found, expired, or already rotated (possible replay attack)
    return new Response(JSON.stringify({ error: 'invalid_token' }), { status: 401 });
  }

  const jwt = await signJwt({ sub: result.anon_id, tier: 'anon' }, env.JWT_PRIVATE_KEY);

  return new Response(
    JSON.stringify({ accessToken: jwt, refreshToken: result.new_token }),
    { status: 200, headers: { 'Content-Type': 'application/json' } }
  );
}

function generateOpaqueToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

async function signJwt(payload: Record<string, unknown>, privateKeyPem: string): Promise<string> {
  const header = { alg: 'RS256', typ: 'JWT' };
  const now = Math.floor(Date.now() / 1000);
  const claims = { ...payload, iat: now, exp: now + 900 }; // 15 min

  const encode = (obj: unknown) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');

  const signingInput = `${encode(header)}.${encode(claims)}`;

  const key = await crypto.subtle.importKey(
    'pkcs8',
    pemToDer(privateKeyPem),
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const sig = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key, new TextEncoder().encode(signingInput));
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');

  return `${signingInput}.${sigB64}`;
}

function pemToDer(pem: string): ArrayBuffer {
  const b64 = pem.replace(/-----[^-]+-----/g, '').replace(/\s+/g, '');
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}
```

---

## React Native: Single-Flight Refresh Interceptor

The critical pattern is a **single-flight lock**: only one refresh in-flight at a time. All concurrent 401s wait for that single promise.

```typescript
// src/auth/apiClient.ts
import axios, { AxiosInstance, AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios';
import { loadRefreshToken, saveRefreshToken, deleteRefreshToken } from './tokenStorage';
import { useAuthStore } from '../store/authStore';

let refreshPromise: Promise<string | null> | null = null;

function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: 'https://api.example project.workers.dev',
    timeout: 10_000,
  });

  // Attach current access token to every request
  client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().accessToken;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // On 401, attempt silent refresh
  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      const originalRequest: AxiosRequestConfig & { _retry?: boolean } = error.config;

      if (error.response?.status !== 401 || originalRequest._retry) {
        return Promise.reject(error);
      }

      originalRequest._retry = true;

      // Single-flight: reuse an in-flight refresh
      if (!refreshPromise) {
        refreshPromise = performRefresh().finally(() => {
          refreshPromise = null;
        });
      }

      const newToken = await refreshPromise;

      if (!newToken) {
        // Refresh failed — clear all auth state, send user back to "ghost mode"
        useAuthStore.getState().clearSession();
        return Promise.reject(new Error('SESSION_EXPIRED'));
      }

      // Retry the original request with the new token
      if (originalRequest.headers) {
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
      }
      return client(originalRequest);
    }
  );

  return client;
}

async function performRefresh(): Promise<string | null> {
  try {
    const refreshToken = await loadRefreshToken();
    if (!refreshToken) return null;

    const response = await axios.post<{ accessToken: string; refreshToken: string }>(
      'https://api.example project.workers.dev/auth/refresh',
      { refreshToken },
      { timeout: 8_000 }
    );

    const { accessToken, refreshToken: newRefreshToken } = response.data;

    // Persist new tokens
    await saveRefreshToken(newRefreshToken);
    useAuthStore.getState().setAccessToken(accessToken);

    return accessToken;
  } catch {
    // Refresh token invalid or revoked
    await deleteRefreshToken();
    return null;
  }
}

export const apiClient = createApiClient();
```

---

## Zustand Auth Store

```typescript
// src/store/authStore.ts
import { create } from 'zustand';

interface AuthState {
  accessToken: string | null;
  anonId: string | null;
  setAccessToken: (token: string) => void;
  setSession: (token: string, anonId: string) => void;
  clearSession: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  anonId: null,
  setAccessToken: (token) => set({ accessToken: token }),
  setSession: (token, anonId) => set({ accessToken: token, anonId }),
  clearSession: () => set({ accessToken: null, anonId: null }),
}));
```

---

## Proactive Refresh Before Expiry

Instead of waiting for a 401, decode the JWT exp claim and refresh 60 seconds early. Use a React hook that fires on app foreground.

```typescript
// src/auth/useProactiveRefresh.ts
import { useEffect, useRef } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { useAuthStore } from '../store/authStore';
import { performRefresh } from './apiClient'; // re-export the function

function jwtExpiry(token: string): number {
  const payload = token.split('.')[1];
  const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
  return decoded.exp as number;
}

export function useProactiveRefresh() {
  const accessToken = <redacted-secret> => s.accessToken);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleRefresh = (token: string) => {
    if (timerRef.current) clearTimeout(timerRef.current);

    const exp = jwtExpiry(token);
    const now = Math.floor(Date.now() / 1000);
    const delay = Math.max(0, (exp - now - 60) * 1000); // 60s buffer

    timerRef.current = setTimeout(() => {
      performRefresh();
    }, delay);
  };

  useEffect(() => {
    if (accessToken) scheduleRefresh(accessToken);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [accessToken]);

  // Re-check on foreground resume
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state: AppStateStatus) => {
      if (state === 'active' && accessToken) {
        const exp = jwtExpiry(accessToken);
        const now = Math.floor(Date.now() / 1000);
        if (exp - now < 120) { // less than 2 min left
          performRefresh();
        }
      }
    });
    return () => sub.remove();
  }, [accessToken]);
}
```

---

## Anti-patterns

- **Storing refresh tokens in `AsyncStorage`**: readable without root on some Android OEMs, and accessible to Hermes debugger sessions. Always use `react-native-keychain`.
- **No single-flight lock**: without the `refreshPromise` guard, five simultaneous 401s fire five refresh requests. The Worker's D1 row gets rotated by the first success; the remaining four see an invalid token and log out the user.
- **Refreshing inside the Worker secret scope without rate-limiting**: callers can brute-force rotate tokens; add a Cloudflare Rate Limiting rule on `/auth/refresh` tied to `anonId` (extracted from the request body after basic validation).
- **Not rotating the refresh token on use**: static refresh tokens are equivalent to passwords; always rotate.
- **Using `exp` from an untrusted decoded JWT without signature verification**: the client-side decode for scheduling is fine, but the Worker must always verify the signature and `exp` server-side before trusting any claim.

---

## Gotchas

- **iOS App Backgrounding**: When iOS suspends the app, `setTimeout` is frozen. On foreground resume the 60s-before check in `AppState` listener is the safety net.
- **D1 write latency**: The `UPDATE ... RETURNING` token rotation is a single D1 write. D1 has ~10 ms P99 in the same region. Add `?_journal_mode=WAL` pragma if you see lock contention under load.
- **Clock skew**: Worker servers use UTC; device clocks may drift. The 60-second proactive buffer absorbs up to 60 seconds of drift. If users run devices with clocks more than 5 minutes off, `iat` validation will also reject the JWT — document this in support.
- **Hermes `atob`**: Hermes on RN 0.73+ ships a native `atob`; on older versions you need a polyfill (`base-64` npm package) for the client-side JWT decode.
- **Network errors vs. 401**: The interceptor only retries on HTTP 401. A network timeout re-throws immediately. Ensure your retry logic in calling code handles `ECONNABORTED` separately.

---

## Verification

```bash
# 1. Obtain an anonymous session
curl -X POST https://api.example project.workers.dev/auth/anon \
  -H 'Content-Type: application/json' \
  -d '{"deviceFingerprint":"test-device-001"}'

# 2. Wait for the JWT to expire (or manually create one with exp = now-1)
# 3. Hit a protected endpoint — expect 401 in interceptor logs, then automatic retry success

# 4. Replay attack test: use the SAME refresh token twice
REFRESH="<first_refresh_token>"
curl -X POST https://api.example project.workers.dev/auth/refresh -d "{\"refreshToken\":\"$REFRESH\"}"
# second call with same token should return 401 invalid_token

# 5. Confirm single-flight: instrument performRefresh with a counter
# Fire 5 requests simultaneously: only 1 network call to /auth/refresh should appear in logs
```

---

## Related

- `mobile-jwt-storage-pitfalls.md`
- `react-native-workers-biometric-auth-secure-enclave.md`
- `react-native-workers-hmac-signed-requests.md`
- `android-credential-manager-passkey-migration.md`
- `ios-keychain-storage.md`
- `capacitor-workers-biometric-webauthn.md`

---

## Sources

- Cloudflare Workers Secrets docs: https://developers.cloudflare.com/workers/configuration/secrets/
- react-native-keychain README: https://github.com/oblador/react-native-keychain
- RFC 6749 §10.4 Refresh Token rotation: https://datatracker.ietf.org/doc/html/rfc6749#section-10.4
- Axios interceptors docs: https://axios-http.com/docs/interceptors
- Hermes `atob` support matrix: https://github.com/facebook/hermes/issues
