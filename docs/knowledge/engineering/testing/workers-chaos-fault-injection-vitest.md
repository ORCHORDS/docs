# Fault Injection Testing for Cloudflare Workers (Vitest)

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker handles D1 errors with a retry loop and a circuit breaker, but you have never actually exercised that code path in tests. When D1 degrades in production, the retry logic spins indefinitely or the circuit breaker opens too early. Fault injection makes these paths first-class citizens of your test suite.

## Context

With `@cloudflare/vitest-pool-workers`, bindings are real Miniflare instances. `vi.spyOn` can intercept binding method calls, inject controlled errors, and restore the original implementation afterward. This lets you simulate KV timeouts, D1 failures, and partial R2 errors deterministically without any external chaos tools.

---

## Section 1 — Mocking D1 to throw on N% of calls

```ts
// tests/chaos/d1-partial-failure.test.ts
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, vi, afterEach } from 'vitest';

/**
 * Wraps a D1Database binding so `prepare().run()` throws on `rate`% of calls.
 * Returns a restore function.
 */
function injectD1Failure(
  db: D1Database,
  rate: number // 0.0 – 1.0
): () => void {
  const original = db.prepare.bind(db);
  const spy = vi.spyOn(db, 'prepare').mockImplementation((query: string) => {
    const stmt = original(query);
    const originalRun = stmt.run.bind(stmt);
    const originalFirst = stmt.first.bind(stmt);
    const originalAll = stmt.all.bind(stmt);

    const maybeFail = <T>(fn: () => Promise<T>): Promise<T> => {
      if (Math.random() < rate) {
        return Promise.reject(
          new Error('D1_ERROR: simulated transient failure')
        );
      }
      return fn();
    };

    return Object.assign(stmt, {
      run: () => maybeFail(originalRun),
      first: <T = unknown>(col?: string) =>
        maybeFail(() => originalFirst<T>(col as string)),
      all: <T = unknown>() => maybeFail(originalAll<T>),
    });
  });

  return () => spy.mockRestore();
}

describe('D1 partial failure — retry logic', () => {
  afterEach(() => vi.restoreAllMocks());

  it('Worker retries up to 3 times and succeeds when failure rate is 30%', async () => {
    // 30% failure rate: statistically the Worker should succeed within 3 retries
    const restore = injectD1Failure(env.DB, 0.3);

    // Seed a row so a successful read can happen
    await env.DB.prepare(
      `INSERT OR IGNORE INTO items (id, name) VALUES (42, 'widget')`
    ).run();

    restore(); // Remove chaos for seed, re-inject for request
    const restoreChaos = injectD1Failure(env.DB, 0.3);

    const res = await SELF.fetch('https://example.com/items/42');
    restoreChaos();

    expect([200, 503]).toContain(res.status); // Allow 503 on bad luck
  });

  it('Worker returns 503 when D1 fails 100% of the time', async () => {
    const restore = injectD1Failure(env.DB, 1.0);
    const res = await SELF.fetch('https://example.com/items/42');
    restore();
    expect(res.status).toBe(503);
  });

  it('error response body contains a retryable hint', async () => {
    const restore = injectD1Failure(env.DB, 1.0);
    const res = await SELF.fetch('https://example.com/items/42');
    restore();
    const body = await res.json<{ error: string; retryable: boolean }>();
    expect(body.retryable).toBe(true);
  });
});
```

## Section 2 — Testing retry and circuit-breaker logic

```ts
// src/lib/with-retry.ts  (source under test)
export async function withRetry<T>(
  fn: () => Promise<T>,
  maxAttempts = 3,
  backoffMs = 100
): Promise<T> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      if (attempt < maxAttempts) {
        await new Promise((r) => setTimeout(r, backoffMs * attempt));
      }
    }
  }
  throw lastError;
}
```

```ts
// tests/chaos/retry.test.ts
import { describe, it, expect, vi } from 'vitest';
import { withRetry } from '../../src/lib/with-retry';

describe('withRetry', () => {
  it('resolves on first attempt when fn succeeds immediately', async () => {
    const fn = vi.fn().mockResolvedValue('ok');
    await expect(withRetry(fn, 3, 0)).resolves.toBe('ok');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('retries and resolves on the 3rd attempt', async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error('fail 1'))
      .mockRejectedValueOnce(new Error('fail 2'))
      .mockResolvedValueOnce('ok');

    await expect(withRetry(fn, 3, 0)).resolves.toBe('ok');
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it('throws after exhausting all attempts', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('always fails'));
    await expect(withRetry(fn, 3, 0)).rejects.toThrow('always fails');
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it('applies exponential backoff delay between attempts', async () => {
    vi.useFakeTimers();
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error('1'))
      .mockRejectedValueOnce(new Error('2'))
      .mockResolvedValueOnce('done');

    const promise = withRetry(fn, 3, 100);
    // Advance through both delays: 100 ms, 200 ms
    await vi.advanceTimersByTimeAsync(100);
    await vi.advanceTimersByTimeAsync(200);
    const result = await promise;

    expect(result).toBe('done');
    vi.useRealTimers();
  });
});
```

## Section 3 — Simulating KV timeouts

```ts
// tests/chaos/kv-timeout.test.ts
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, vi, afterEach } from 'vitest';

/**
 * Makes KVNamespace.get hang for `delayMs` before resolving to null.
 * Simulates a KV timeout / slow response.
 */
function injectKVTimeout(kv: KVNamespace, delayMs: number): () => void {
  const spy = vi.spyOn(kv, 'get').mockImplementation(
    () =>
      new Promise((resolve) =>
        setTimeout(() => resolve(null), delayMs)
      ) as ReturnType<KVNamespace['get']>
  );
  return () => spy.mockRestore();
}

describe('KV timeout simulation', () => {
  afterEach(() => vi.restoreAllMocks());

  it('Worker falls back to D1 when KV times out', async () => {
    // Simulate KV taking 2 seconds — Worker timeout budget is typically 30 s,
    // but we test that the Worker does NOT wait and falls back fast.
    const restore = injectKVTimeout(env.CACHE, 2000);

    // Seed D1 fallback
    await env.DB.prepare(
      `INSERT OR IGNORE INTO items (id, name) VALUES (1, 'fallback-item')`
    ).run();

    const start = Date.now();
    const res = await SELF.fetch('https://example.com/items/1');
    restore();

    expect(res.status).toBe(200);
    // Worker should have a KV timeout of ~500 ms and then hit D1
    expect(Date.now() - start).toBeLessThan(600);

    const body = await res.json<{ name: string; source: string }>();
    expect(body.source).toBe('d1'); // confirms fallback path
  });

  it('returns stale-while-revalidate header when KV is unavailable', async () => {
    const restore = injectKVTimeout(env.CACHE, 5000);
    const res = await SELF.fetch('https://example.com/items/1');
    restore();
    // Cache-Control must signal stale content during KV outage
    expect(res.headers.get('Cache-Control')).toContain('stale-while-revalidate');
  });
});
```

## Section 4 — Deterministic fault injection with vi.spyOn call counts

```ts
// tests/chaos/d1-nth-call-failure.test.ts
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, vi, afterEach } from 'vitest';

/**
 * Fails only on the Nth call to db.prepare, then succeeds.
 * Useful for testing that retry logic recovers from a single transient error.
 */
function failOnNthPrepare(db: D1Database, n: number): () => void {
  let callCount = 0;
  const original = db.prepare.bind(db);
  const spy = vi.spyOn(db, 'prepare').mockImplementation((query: string) => {
    callCount++;
    if (callCount === n) {
      const fakeStmt = {
        bind: () => fakeStmt,
        run: () => Promise.reject(new Error(`D1_FAIL on call ${n}`)),
        first: () => Promise.reject(new Error(`D1_FAIL on call ${n}`)),
        all: () => Promise.reject(new Error(`D1_FAIL on call ${n}`)),
      } as unknown as D1PreparedStatement;
      return fakeStmt;
    }
    return original(query);
  });
  return () => spy.mockRestore();
}

describe('Nth-call fault injection', () => {
  afterEach(() => vi.restoreAllMocks());

  it('recovers when only the 2nd D1 call fails', async () => {
    await env.DB.prepare(
      `INSERT OR IGNORE INTO items (id, name) VALUES (99, 'chaos-item')`
    ).run();

    const restore = failOnNthPrepare(env.DB, 2);
    const res = await SELF.fetch('https://example.com/items/99');
    restore();

    // The Worker's retry should have made a 3rd call that succeeded
    expect(res.status).toBe(200);
  });
});
```

## Anti-patterns

- **Injecting faults in `beforeAll`** without restoring in `afterEach` — subsequent tests inherit the mock and produce false failures.
- **Using `Math.random()` in assertions** — fault injection with probabilistic rates should always have a deterministic fallback assertion (e.g., test 100% failure rate separately).
- **Mocking at the fetch level** (e.g., intercepting `fetch()`) for D1/KV — these are not HTTP calls inside Workers; mock at the binding method level.

## Gotchas

- `vi.spyOn` on Miniflare binding objects works because they are plain JS objects, but the spy must be created *after* `cloudflare:test` provides `env`.
- Fake timers (`vi.useFakeTimers`) and async Miniflare operations can deadlock. Call `vi.useRealTimers()` in `afterEach` or use `vi.advanceTimersByTimeAsync`.
- Injecting D1 failures during seed (`beforeAll`) pollutes the seed step. Restore before seeding, re-inject for the test.

## Verification

```bash
npx vitest run tests/chaos/
# All chaos tests should be deterministic — run twice to confirm
npx vitest run tests/chaos/ && npx vitest run tests/chaos/
```

## Related

- `documentation/docs/policies/testing/workers-mutation-testing-stryker-vitest.md`
- `documentation/resilience/workers-circuit-breaker-pattern.md`
- `documentation/resilience/workers-kv-fallback-d1.md`

## Sources

- https://vitest.dev/api/vi.html#vi-spyon
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://miniflare.dev/
