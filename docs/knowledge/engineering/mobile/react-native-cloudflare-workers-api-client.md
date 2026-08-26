# React Native Typed API Client for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Mobile teams need a robust, typed HTTP client to communicate with Cloudflare Workers APIs from React Native. Raw `fetch` calls scatter throughout the codebase, retry logic is ad-hoc, and token refresh races cause sporadic 401 errors that are hard to reproduce.

---

## Context
Cloudflare Workers return a `CF-Ray` header on every response — a globally unique request ID invaluable for correlating mobile crash reports with Workers logs. Zod schemas enforce contract alignment between the Worker response and the React Native consumer at runtime, catching drift before it surfaces as a crash. A centralised client singleton handles JWT expiry transparently via an interceptor, queues requests that arrive while a token refresh is in flight, and drains offline mutations through `@react-native-async-storage/async-storage` once connectivity is restored. The pattern works with both Expo and bare React Native projects.

---

## Section 1 — Dependencies & Config

```bash
npx expo install zod
npx expo install @react-native-async-storage/async-storage
npx expo install @react-native-community/netinfo
```

```toml
# app.config.ts / environment
CF_WORKERS_BASE_URL = "https://api.example.workers.dev"
CF_JWT_REFRESH_PATH = "/auth/refresh"
CF_REQUEST_TIMEOUT_MS = 10000
```

---

## Section 2 — Implementation

```typescript
// src/api/client.ts
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import { z, ZodTypeAny } from 'zod';

const BASE_URL = process.env.CF_WORKERS_BASE_URL ?? '';
const REFRESH_PATH = process.env.CF_JWT_REFRESH_PATH ?? '/auth/refresh';
const TIMEOUT_MS = Number(process.env.CF_REQUEST_TIMEOUT_MS ?? 10_000);
const TOKEN_KEY = '@cf_access_token';
const REFRESH_TOKEN_KEY = '@cf_refresh_token';
const OFFLINE_QUEUE_KEY = '@cf_offline_queue';

type QueuedRequest = {
  id: string;
  method: string;
  path: string;
  body?: unknown;
  timestamp: number;
};

let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

function subscribeTokenRefresh(cb: (token: string) => void) {
  refreshSubscribers.push(cb);
}

function notifySubscribers(token: string) {
  refreshSubscribers.forEach(cb => cb(token));
  refreshSubscribers = [];
}

async function getAccessToken(): Promise<string | null> {
  return AsyncStorage.getItem(TOKEN_KEY);
}

async function refreshAccessToken(): Promise<string> {
  const refreshToken = await AsyncStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) throw new Error('No refresh token stored');

  const res = await fetch(`${BASE_URL}${REFRESH_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refreshToken }),
  });

  if (!res.ok) throw new Error(`Token refresh failed: ${res.status}`);

  const { accessToken, refreshToken: newRefresh } = await res.json();
  await AsyncStorage.multiSet([
    [TOKEN_KEY, accessToken],
    [REFRESH_TOKEN_KEY, newRefresh],
  ]);
  return accessToken;
}

async function enqueueOffline(req: Omit<QueuedRequest, 'id' | 'timestamp'>) {
  const raw = await AsyncStorage.getItem(OFFLINE_QUEUE_KEY);
  const queue: QueuedRequest[] = raw ? JSON.parse(raw) : [];
  queue.push({ ...req, id: Math.random().toString(36).slice(2), timestamp: Date.now() });
  await AsyncStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue));
}

export async function drainOfflineQueue() {
  const { isConnected } = await NetInfo.fetch();
  if (!isConnected) return;

  const raw = await AsyncStorage.getItem(OFFLINE_QUEUE_KEY);
  if (!raw) return;

  const queue: QueuedRequest[] = JSON.parse(raw);
  await AsyncStorage.removeItem(OFFLINE_QUEUE_KEY);

  for (const req of queue) {
    try {
      await cfFetch(req.path, { method: req.method, body: req.body });
    } catch {
      // Re-enqueue on failure — simple strategy; production code would cap retries
      await enqueueOffline({ method: req.method, path: req.path, body: req.body });
    }
  }
}

type FetchOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
};

async function cfFetch<T extends ZodTypeAny>(
  path: string,
  options: FetchOptions = {},
  schema?: T,
): Promise<z.infer<T>> {
  const { isConnected } = await NetInfo.fetch();

  if (!isConnected && options.method && options.method !== 'GET') {
    await enqueueOffline({ method: options.method, path, body: options.body });
    throw new Error('OFFLINE_QUEUED');
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const token = await getAccessToken();

  const makeRequest = async (accessToken: string | null) =>
    fetch(`${BASE_URL}${path}`, {
      method: options.method ?? 'GET',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Client-Platform': 'react-native',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...options.headers,
      },
      body: options.body != null ? JSON.stringify(options.body) : undefined,
    });

  let res = await makeRequest(token);
  clearTimeout(timer);

  const cfRay = res.headers.get('CF-Ray');
  if (cfRay) console.debug('[CF-Ray]', cfRay);

  // --- 401: transparent JWT refresh ---
  if (res.status === 401) {
    if (isRefreshing) {
      const newToken = await new Promise<string>(resolve => subscribeTokenRefresh(resolve));
      res = await makeRequest(newToken);
    } else {
      isRefreshing = true;
      try {
        const newToken = await refreshAccessToken();
        notifySubscribers(newToken);
        res = await makeRequest(newToken);
      } finally {
        isRefreshing = false;
      }
    }
  }

  // --- 429: honour Retry-After ---
  if (res.status === 429) {
    const retryAfter = Number(res.headers.get('Retry-After') ?? '1');
    await new Promise(r => setTimeout(r, retryAfter * 1_000));
    res = await makeRequest(await getAccessToken());
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`CF Workers error ${res.status}: ${text}`);
  }

  const json = await res.json();
  return schema ? schema.parse(json) : json;
}

// --- Typed helpers ---
export const UserSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  displayName: z.string(),
});
export type User = z.infer<typeof UserSchema>;

export const api = {
  getUser: (id: string) => cfFetch(`/users/${id}`, {}, UserSchema),
  updateUser: (id: string, patch: Partial<User>) =>
    cfFetch(`/users/${id}`, { method: 'PATCH', body: patch }, UserSchema),
};
```

---

## Section 3 — Integration / Testing

```typescript
// __tests__/api-client.test.ts
import { api, drainOfflineQueue } from '../src/api/client';

global.fetch = jest.fn();

const mockFetch = (status: number, body: unknown, headers: Record<string, string> = {}) => {
  (fetch as jest.Mock).mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (k: string) => headers[k] ?? null },
    json: async () => body,
    text: async () => JSON.stringify(body),
  });
};

test('getUser parses valid response', async () => {
  mockFetch(200, { id: '1', email: 'a@b.com', displayName: 'Alice' });
  const user = await api.getUser('1');
  expect(user.email).toBe('a@b.com');
});

test('retries once after 429 with Retry-After 0', async () => {
  mockFetch(429, {}, { 'Retry-After': '0' });
  mockFetch(200, { id: '1', email: 'a@b.com', displayName: 'Alice' });
  const user = await api.getUser('1');
  expect(user.id).toBe('1');
  expect(fetch).toHaveBeenCalledTimes(2);
});
```

---

## Anti-patterns
- **Storing JWTs in plain AsyncStorage without encryption** — use `expo-secure-store` for access tokens on production builds.
- **Ignoring `CF-Ray` in error reports** — always surface it in Sentry breadcrumbs so Workers logs can be correlated.
- **Unlimited offline queue growth** — cap the queue at a fixed size and surface a user-visible warning when the cap is hit.

---

## Gotchas
- `AbortController` in React Native requires RN 0.60+ and Hermes; older JSC builds may need a polyfill.
- Zod `.parse()` throws synchronously — wrap API calls in a try/catch in every screen component.
- The 429 retry loop does not count against the original `TIMEOUT_MS` budget; set a separate ceiling for total wait time in latency-sensitive flows.

---

## Verification

```bash
# Confirm CF-Ray header reaches the client
curl -s -I https://api.example.workers.dev/users/1 | grep -i cf-ray

# Run unit tests
npx jest --testPathPattern=api-client

# Check AsyncStorage offline queue after killing network
# (React Native Debugger → AsyncStorage explorer → @cf_offline_queue)
```

---

## Related
- `expo-workers-push-notifications-queues.md`
- `workers-mobile-offline-sync-d1.md`

---

## Sources
- Cloudflare Workers Fetch API — https://developers.cloudflare.com/workers/runtime-apis/fetch/
- Zod Documentation — https://zod.dev
- React Native AsyncStorage — https://react-native-async-storage.github.io/async-storage/
