# Miniflare KV TTL Expiry Testing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

KV values written with `expirationTtl` or `expiration` silently disappear after their TTL elapses. Testing time-sensitive eviction paths—cache invalidation logic, session timeouts, token refresh windows—requires advancing the clock without sleeping for minutes in a test. Without controlled time, TTL behaviour is untestable in fast CI runs.

## Context

Miniflare (via `@cloudflare/vitest-pool-workers`) implements KV TTL using the process clock. Vitest's `vi.useFakeTimers()` replaces `Date` and timer globals in the test thread, but Miniflare's KV engine runs in a separate workerd instance and reads the system clock independently. The correct approach is to use `runWithMiniflareClock` (or the equivalent `setTime` utility provided by the pool) to advance Miniflare's internal clock, not the JavaScript `Date` object.

KV TTL semantics in production:
- Values are guaranteed to be readable until their expiration time.
- Values may persist up to 60 seconds beyond expiration (eventual consistency).
- Miniflare enforces expiry exactly at the target time (no grace window) which makes tests deterministic.

Minimum TTL on production KV is 60 seconds. Miniflare accepts any value ≥ 1 second.

## Setup

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "SESSION_KV"
id = "test-namespace"
```

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    pool: '@cloudflare/vitest-pool-workers',
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

```typescript
// env.d.ts
interface Env {
  SESSION_KV: KVNamespace;
}
```

## Advancing Miniflare's Clock

The pool exposes `getMiniflareDurableObjectStorage` and a `setTime` helper via `cloudflare:test`:

```typescript
// tests/kv-ttl.test.ts
import { env, runWithMiniflareClock } from 'cloudflare:test';
// Note: runWithMiniflareClock may be exported as `advanceMiniflareTime`
// in some pool-workers versions — check your installed version.
import { describe, it, expect, beforeEach } from 'vitest';

async function advanceSeconds(seconds: number): Promise<void> {
  // The pool exposes a clock control via the __clock symbol on the env proxy,
  // or through the runWithMiniflareClock wrapper. Adjust for your SDK version:
  await runWithMiniflareClock(seconds * 1000);
}

describe('KV TTL expiry', () => {
  beforeEach(async () => {
    // Clear namespace between tests
    const list = await env.SESSION_KV.list();
    await Promise.all(list.keys.map((k) => env.SESSION_KV.delete(k.name)));
  });
```

## Testing Expiry on Read

```typescript
  it('returns null after TTL elapses', async () => {
    await env.SESSION_KV.put('session:abc', JSON.stringify({ userId: 1 }), {
      expirationTtl: 30, // 30 seconds
    });

    // Confirm value is readable before expiry
    const before = await env.SESSION_KV.get('session:abc');
    expect(before).not.toBeNull();

    // Advance past TTL
    await advanceSeconds(31);

    const after = await env.SESSION_KV.get('session:abc');
    expect(after).toBeNull();
  });

  it('returns value when TTL has not yet elapsed', async () => {
    await env.SESSION_KV.put('token:xyz', 'refresh-token-value', {
      expirationTtl: 60,
    });

    await advanceSeconds(59);

    const value = await env.SESSION_KV.get('token:xyz');
    expect(value).toBe('refresh-token-value');
  });
});
```

## Testing Absolute Expiration Timestamps

```typescript
describe('KV absolute expiration', () => {
  it('expires at the specified Unix timestamp', async () => {
    const nowSeconds = Math.floor(Date.now() / 1000);
    const expiresAt = nowSeconds + 120; // 2 minutes from now

    await env.SESSION_KV.put('rate-limit:user:42', '5', {
      expiration: expiresAt,
    });

    await advanceSeconds(119);
    expect(await env.SESSION_KV.get('rate-limit:user:42')).toBe('5');

    await advanceSeconds(2); // total 121s elapsed
    expect(await env.SESSION_KV.get('rate-limit:user:42')).toBeNull();
  });
});
```

## Testing Sliding Window Refresh

A common pattern refreshes the TTL on each access to extend a session:

```typescript
async function touchSession(kv: KVNamespace, key: string, ttlSeconds: number): Promise<string | null> {
  const value = await kv.get(key);
  if (value !== null) {
    await kv.put(key, value, { expirationTtl: ttlSeconds });
  }
  return value;
}

describe('sliding window session', () => {
  it('extends TTL on each touch', async () => {
    await env.SESSION_KV.put('session:sliding', '{"user":99}', { expirationTtl: 30 });

    // Touch at 25s to reset TTL to 30s from now (total 55s from start)
    await advanceSeconds(25);
    const mid = await touchSession(env.SESSION_KV, 'session:sliding', 30);
    expect(mid).not.toBeNull();

    // Without touch: would have expired at 30s; with touch: expires at 55s
    await advanceSeconds(29); // now at 54s from original put
    const late = await env.SESSION_KV.get('session:sliding');
    expect(late).not.toBeNull();

    // Finally expires after the refreshed window
    await advanceSeconds(2); // now at 56s
    const expired = await env.SESSION_KV.get('session:sliding');
    expect(expired).toBeNull();
  });
});
```

## Testing List with Expiry Metadata

```typescript
describe('KV list expiration metadata', () => {
  it('list returns expiration timestamp on keys', async () => {
    const nowSeconds = Math.floor(Date.now() / 1000);
    await env.SESSION_KV.put('meta:key', 'value', { expirationTtl: 60 });

    const { keys } = await env.SESSION_KV.list({ prefix: 'meta:' });
    expect(keys).toHaveLength(1);
    expect(keys[0].expiration).toBeGreaterThanOrEqual(nowSeconds + 60);
  });

  it('expired keys do not appear in list results', async () => {
    await env.SESSION_KV.put('expired:key', 'value', { expirationTtl: 10 });
    await env.SESSION_KV.put('live:key', 'value', { expirationTtl: 300 });

    await advanceSeconds(11);

    const { keys } = await env.SESSION_KV.list();
    const names = keys.map((k) => k.name);
    expect(names).not.toContain('expired:key');
    expect(names).toContain('live:key');
  });
});
```

## Anti-patterns

- **Using `vi.useFakeTimers()` to control KV expiry** – Vitest fake timers affect only the JS runtime clock; Miniflare's KV engine runs in a separate workerd process and ignores `Date` overrides.
- **Sleeping with `setTimeout` in tests** – Sleeping 30+ seconds in CI for TTL tests is impractical. Always use the clock control API.
- **Asserting exact expiration timestamps** – Expiration values may round to the nearest second. Use `toBeGreaterThanOrEqual` with a floor value rather than strict equality.
- **Skipping cleanup between tests** – KV state persists across tests within a file. Always delete keys in `beforeEach` or `afterEach`.

## Gotchas

- Production KV has a minimum TTL of 60 seconds; Miniflare does not enforce this. Write a separate guard in application code to reject TTLs below 60 seconds.
- `runWithMiniflareClock` / clock control export names differ between pool-workers versions. Consult the installed version's type declarations.
- The `expiration` option takes a Unix timestamp in seconds, not milliseconds. A common mistake is passing `Date.now()` (milliseconds) directly.
- After `advanceSeconds`, await any pending microtasks (`await new Promise(r => setTimeout(r, 0))`) before asserting expiry if the KV write was deferred.

## Verification

```bash
npx vitest run tests/kv-ttl.test.ts --reporter=verbose
```

All tests should complete in under 2 seconds regardless of the TTL durations under test.

## Related

- `kv-testing-miniflare.md` — basic KV put/get/delete/list patterns
- `durable-objects-miniflare-fake-timers.md` — fake timers for Durable Object alarms
- `test-doubles-cloudflare-workers.md` — manual KV mock strategies

## Sources

- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
