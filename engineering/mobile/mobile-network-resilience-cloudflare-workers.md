# Mobile Network Resilience with Cloudflare Workers

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

API calls from the example project mobile app succeed on Wi-Fi but
fail silently on cellular. Users on 2G/3G see blank feeds,
failed post submissions, or stale vote counts with no error
message. The app re-submits on reconnect and creates
duplicate records (double votes, duplicate posts). Workers
respond with 524 (timeout) on degraded connections and the
app treats this as a permanent error instead of retrying.

## Context

Cloudflare Workers sit between the mobile client and
downstream services (D1, KV, R2). The Worker itself has a
30-second CPU limit and a 30-second wall-clock limit per
request. Mobile networks — especially 2G EDGE (~200 kbps,
500 ms RTT) and 3G HSPA (~2 Mbps, 100 ms RTT) — can push
a request past these limits or drop the TCP connection
mid-flight. The mobile client must own the retry strategy;
the Worker must own idempotency so retries are safe.

---

## 1. Exponential Backoff with Jitter

Use full-jitter backoff. Cap at 30 s to avoid indefinite
blocking on degraded 2G links where the UX cost of waiting
exceeds the benefit of eventual success.

```ts
// src/network/fetchWithBackoff.ts

interface BackoffOptions {
  maxAttempts?: number;   // default 4
  baseDelayMs?: number;   // default 500
  maxDelayMs?:  number;   // default 30_000
  shouldRetry?: (status: number) => boolean;
}

const RETRYABLE = new Set([408, 429, 500, 502, 503, 504, 524]);

export async function fetchWithBackoff<T>(
  url: string,
  init: RequestInit = {},
  opts: BackoffOptions = {}
): Promise<T> {
  const {
    maxAttempts = 4,
    baseDelayMs = 500,
    maxDelayMs  = 30_000,
    shouldRetry = (s) => RETRYABLE.has(s),
  } = opts;

  let lastErr: Error = new Error('unreachable');

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const controller = new AbortController();
    const timeout = setTimeout(
      () => controller.abort(), 15_000  // 15 s per attempt
    );

    try {
      const res = await fetch(url, {
        ...init,
        signal: controller.signal,
      });

      if (res.ok) return res.json() as Promise<T>;

      // Use Retry-After for 429; fall through to backoff
      if (res.status === 429) {
        const ra = res.headers.get('retry-after');
        const ms = ra ? Number(ra) * 1000 : baseDelayMs;
        await delay(ms);
        continue;
      }

      if (!shouldRetry(res.status)) {
        throw new Error(`HTTP ${res.status}`);
      }
      lastErr = new Error(`HTTP ${res.status}`);
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') {
        lastErr = new Error('Request timeout');
      } else {
        lastErr = err as Error;
      }
    } finally {
      clearTimeout(timeout);
    }

    if (attempt < maxAttempts - 1) {
      // Full-jitter: random value in [0, cap]
      const cap = Math.min(
        baseDelayMs * 2 ** attempt, maxDelayMs
      );
      await delay(Math.random() * cap);
    }
  }

  throw lastErr;
}

const delay = (ms: number) =>
  new Promise<void>((r) => setTimeout(r, ms));
```

---

## 2. Request Idempotency via D1

Mutations (post, vote, report) must be safe to replay.
Store a client-generated idempotency key in D1 and return
the original response on duplicate submissions.

```sql
-- D1 migration: 0005_idempotency.sql
CREATE TABLE IF NOT EXISTS idempotency_keys (
  key         TEXT PRIMARY KEY,
  status_code INTEGER NOT NULL,
  response    TEXT    NOT NULL,   -- JSON blob
  created_at  INTEGER NOT NULL,   -- Unix ms
  expires_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS
  idx_idem_expires ON idempotency_keys (expires_at);
```

```ts
// workers/src/middleware/idempotency.ts
import { Env } from '../types';

export async function withIdempotency(
  req: Request,
  env: Env,
  handler: () => Promise<Response>
): Promise<Response> {
  const key = req.headers.get('idempotency-key');
  if (!key) return handler();          // GET or opted-out

  const existing = await env.DB
    .prepare(
      'SELECT status_code, response FROM idempotency_keys' +
      ' WHERE key = ? AND expires_at > ?'
    )
    .bind(key, Date.now())
    .first<{ status_code: number; response: string }>();

  if (existing) {
    return new Response(existing.response, {
      status: existing.status_code,
      headers: { 'content-type': 'application/json',
                 'idempotent-replayed': 'true' },
    });
  }

  const res = await handler();
  const body = await res.text();

  // Store for 24 hours; don't store errors
  if (res.ok) {
    await env.DB
      .prepare(
        'INSERT OR IGNORE INTO idempotency_keys' +
        ' (key, status_code, response, created_at, expires_at)' +
        ' VALUES (?, ?, ?, ?, ?)'
      )
      .bind(
        key, res.status, body,
        Date.now(), Date.now() + 86_400_000
      )
      .run();
  }

  return new Response(body, {
    status: res.status,
    headers: res.headers,
  });
}
```

On the client, generate the key once per user action and
persist it until the server confirms success:

```ts
import 'react-native-get-random-values';
import { v4 as uuidv4 } from 'uuid';
import { storage } from './mmkvStorage';

export function getOrCreateIdemKey(actionId: string): string {
  const stored = storage.getString(`idem:${actionId}`);
  if (stored) return stored;
  const key = uuidv4();
  storage.set(`idem:${actionId}`, key);
  return key;
}

export function clearIdemKey(actionId: string) {
  storage.delete(`idem:${actionId}`);
}
```

---

## 3. Offline Queue with Background Sync

Persist mutations when offline; drain on reconnect. Use
MMKV for the queue because AsyncStorage flushes have caused
data loss on abrupt process termination in React Native.

```ts
// src/network/offlineQueue.ts
import NetInfo from '@react-native-community/netinfo';
import { storage } from './mmkvStorage';
import { fetchWithBackoff } from './fetchWithBackoff';

interface QueuedRequest {
  id:        string;
  url:       string;
  method:    string;
  body:      string;
  idemKey:   string;
  queuedAt:  number;
}

const QUEUE_KEY = 'offline_queue_v2';

export function enqueue(req: Omit<QueuedRequest, 'id' | 'queuedAt'>) {
  const queue = getQueue();
  queue.push({ ...req, id: req.idemKey,
               queuedAt: Date.now() });
  storage.set(QUEUE_KEY, JSON.stringify(queue));
}

function getQueue(): QueuedRequest[] {
  return JSON.parse(storage.getString(QUEUE_KEY) ?? '[]');
}

export function startBackgroundSync() {
  NetInfo.addEventListener(async (state) => {
    if (!state.isConnected) return;
    const queue = getQueue();
    if (!queue.length) return;

    const remaining: QueuedRequest[] = [];
    for (const item of queue) {
      try {
        await fetchWithBackoff(item.url, {
          method: item.method,
          body:   item.body,
          headers: {
            'content-type':    'application/json',
            'idempotency-key': item.idemKey,
          },
        });
        clearIdemKey(item.idemKey);
      } catch {
        // Keep failed items; drop items older than 7 days
        if (Date.now() - item.queuedAt < 7 * 86_400_000) {
          remaining.push(item);
        }
      }
    }
    storage.set(QUEUE_KEY, JSON.stringify(remaining));
  });
}
```

---

## 4. Handling 2G / 3G Degraded Responses

Detect slow connections before making large requests and
downgrade to compressed/minimal payloads.

```ts
import NetInfo, { NetInfoStateType }
  from '@react-native-community/netinfo';

type Quality = 'fast' | 'slow' | 'offline';

export async function networkQuality(): Promise<Quality> {
  const state = await NetInfo.fetch();
  if (!state.isConnected) return 'offline';
  if (
    state.type === NetInfoStateType.cellular &&
    state.details?.cellularGeneration &&
    ['2g', '3g'].includes(state.details.cellularGeneration)
  ) return 'slow';
  return 'fast';
}
```

Pass quality as a query param; the Worker returns a slimmer
payload on `?quality=slow`:

```
| Quality | Feed items | Image size | Comment preview |
|---------|-----------|------------|-----------------|
| fast    | 20        | 720 px     | 3 lines         |
| slow    | 10        | 240 px     | 1 line          |
| offline | 0 (cache) | cached     | cached          |
```

In the Worker:

```ts
// workers/src/routes/feed.ts
export async function handleFeed(req: Request, env: Env) {
  const url  = new URL(req.url);
  const slow = url.searchParams.get('quality') === 'slow';
  const limit = slow ? 10 : 20;
  const imgW  = slow ? 240 : 720;
  // ... query D1, return slim projection
}
```

---

## 5. Retry Budget Table

Avoid burning through retries on unrecoverable errors.

```
| HTTP Status | Retry? | Strategy                        |
|-------------|--------|---------------------------------|
| 400         | No     | Client bug; show error          |
| 401         | No     | Re-authenticate                 |
| 403         | No     | Permanent denial                |
| 404         | No     | Resource gone                   |
| 408         | Yes    | Timeout; full jitter backoff    |
| 409         | No     | Conflict; re-fetch & reconcile  |
| 429         | Yes    | Use Retry-After header          |
| 500         | Yes    | Server error; backoff           |
| 502/503     | Yes    | Cloudflare upstream; backoff    |
| 504/524     | Yes    | Worker timeout; backoff         |
| Network err | Yes    | Offline or DNS; backoff         |
```

---

## Anti-patterns

- Retrying POST without an idempotency key. Every retry
  risks a duplicate record in D1.
- Using `setTimeout` for backoff inside a React Native
  background task. The task may be killed before the timer
  fires; use the offline queue pattern instead.
- Treating Cloudflare 524 (connection timeout) as a 5xx
  error and showing "server error" to the user. 524 means
  the Worker itself timed out, not that the origin is down.
- Ignoring `Retry-After` on 429. Sending requests faster
  than the header allows escalates the ban window.
- Storing the offline queue in AsyncStorage. Data loss
  occurs on abrupt process termination.

## Gotchas

- `AbortController` timeout on React Native requires the
  `abort-controller` polyfill on RN < 0.71; newer versions
  include it natively.
- Cloudflare's 30-second Worker timeout clock starts when
  the Worker begins executing, not when the client connects.
  A slow 3G upload can consume most of the budget before
  the Worker even reads the body.
- MMKV writes are synchronous but extremely fast (~µs); do
  not move them off the JS thread.
- The `NetInfo` `isConnected` value can be `true` on a
  captive portal (hotel Wi-Fi login screen) while actual
  HTTPS requests fail. Always handle fetch rejections even
  when `isConnected` is truthy.

## Verification

```bash
# Simulate 2G from the terminal (macOS network link conditioner
# or Android emulator extended controls → Cellular)

# Confirm idempotency: send same request twice,
# second should return 'idempotent-replayed: true' header
curl -X POST https://api.example.com/v1/posts \
  -H "idempotency-key: test-idem-001" \
  -H "content-type: application/json" \
  -d '{"body":"hello world"}' -i

# Send again — expect HTTP 200 with idempotent-replayed: true
curl -X POST https://api.example.com/v1/posts \
  -H "idempotency-key: test-idem-001" \
  -H "content-type: application/json" \
  -d '{"body":"hello world"}' -i
```

## Related

- `mobile-network-resilience.md`
- `mobile-offline-sync-conflict-resolution.md`
- `mobile-slow-network-testing.md`
- `offline-first-worker-api-resilience.md`
- `react-native-netinfo.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/d1/
- https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Retry-After
- https://github.com/react-native-netinfo/react-native-netinfo
