# mobile-network-resilience

**Issue:** Building mobile apps that gracefully handle intermittent connectivity, slow networks, and server errors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mobile networks drop mid-request; apps that don't retry with backoff produce bad UX and data inconsistencies.

## Pattern / Solution
```ts
// Exponential backoff with jitter (TypeScript)
async function fetchWithRetry<T>(
  url: string,
  options?: RequestInit,
  maxAttempts = 4
): Promise<T> {
  let lastError: Error;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      lastError = err as Error;
      if (attempt < maxAttempts - 1) {
        const delay = Math.min(1000 * 2 ** attempt + Math.random() * 500, 30_000);
        await new Promise((r) => setTimeout(r, delay));
      }
    }
  }
  throw lastError!;
}

// Offline queue (React Native)
import NetInfo from '@react-native-community/netinfo';
import { storage } from './mmkvStorage';

async function queueOrExecute(action: () => Promise<void>, key: string) {
  const { isConnected } = await NetInfo.fetch();
  if (isConnected) {
    return action();
  }
  // Persist for later
  const queue: string[] = JSON.parse(storage.getString('offlineQueue') ?? '[]');
  queue.push(key);
  storage.set('offlineQueue', JSON.stringify(queue));
}
```

## Gotchas
- Retry should not re-send non-idempotent operations (POST payments) without deduplication tokens
- Jitter (random delay component) is critical — without it, all clients retry simultaneously after an outage (thundering herd)
- `fetch` timeout must be set via `AbortController` — there is no native timeout parameter
- 429 (rate limit) responses should use the `Retry-After` header value, not exponential backoff

## Related
- `react-native-netinfo.md`
- `react-native-offline-first.md`
- `mobile-battery-optimization.md`
