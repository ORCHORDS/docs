# Chaos Testing Workers KV Latency Injection

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project caches anonymous session tokens and rate-limit counters in Cloudflare KV. When KV read
latency degrades — due to a regional disruption or cold cache after a deployment — Workers that
depend on synchronous KV lookups can exceed the 30-second CPU time budget or return 503s to users.
The team needed chaos tests that inject artificial KV latency to verify that the Worker falls back
gracefully (short-circuit to allow or deny) rather than hanging indefinitely.

## Context

The tests run inside `vitest` using `@cloudflare/vitest-pool-workers`. KV latency injection is
achieved by wrapping the `KVNamespace` binding in a proxy that adds a configurable `delay` before
forwarding calls to the underlying Miniflare KV store. There is no need to intercept network traffic
because the KV binding is an in-process object in the Miniflare runtime. The proxy is injected via
a vitest `beforeEach` block that replaces `env.SESSION_KV`.

## KV Latency Proxy

```typescript
// tests/helpers/kv-latency-proxy.ts
export interface LatencyConfig {
  getDelayMs: number;
  putDelayMs?: number;
  listDelayMs?: number;
  deleteDelayMs?: number;
}

export function createKvLatencyProxy(
  kv: KVNamespace,
  config: LatencyConfig
): KVNamespace {
  const delay = (ms: number) =>
    new Promise<void>((resolve) => setTimeout(resolve, ms));

  return new Proxy(kv, {
    get(target, prop) {
      if (prop === "get" || prop === "getWithMetadata") {
        return async (...args: Parameters<KVNamespace["get"]>) => {
          await delay(config.getDelayMs);
          return (target as any)prop;
        };
      }
      if (prop === "put") {
        return async (...args: Parameters<KVNamespace["put"]>) => {
          await delay(config.putDelayMs ?? 0);
          return target.put(...args);
        };
      }
      if (prop === "list") {
        return async (...args: Parameters<KVNamespace["list"]>) => {
          await delay(config.listDelayMs ?? 0);
          return target.list(...args);
        };
      }
      if (prop === "delete") {
        return async (...args: Parameters<KVNamespace["delete"]>) => {
          await delay(config.deleteDelayMs ?? 0);
          return target.delete(...args);
        };
      }
      return (target as any)[prop];
    },
  });
}
```

## Worker Session Middleware with Timeout Guard

```typescript
// src/middleware/session.ts
import { Env } from "../types";

const SESSION_TIMEOUT_MS = 150; // fail-fast budget for KV reads

export interface SessionResult {
  valid: boolean;
  anonId?: string;
  failedOpen: boolean; // true when KV timed out and we defaulted to allow
}

export async function resolveSession(
  token: string,
  env: Env
): Promise<SessionResult> {
  const kvGet = env.SESSION_KV.get(token, { type: "json" });

  const timeoutP = new Promise<null>((resolve) =>
    setTimeout(() => resolve(null), SESSION_TIMEOUT_MS)
  );

  const raw = await Promise.race([kvGet, timeoutP]);

  if (raw === null) {
    // KV was too slow — fail open to avoid blocking the user
    console.warn("KV session lookup timed out; failing open");
    return { valid: true, failedOpen: true };
  }

  const session = raw as { anonId: string; expiresAt: number } | null;
  if (!session || session.expiresAt < Date.now()) {
    return { valid: false, failedOpen: false };
  }

  return { valid: true, anonId: session.anonId, failedOpen: false };
}
```

## Vitest Chaos Tests

```typescript
// tests/chaos/kv-latency.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { env } from "cloudflare:test";
import { createKvLatencyProxy } from "../helpers/kv-latency-proxy";
import { resolveSession } from "../../src/middleware/session";

describe("KV latency chaos — session middleware", () => {
  const TOKEN = "chaos-test-token";
  const SESSION = {
    anonId: "anon-chaos-001",
    expiresAt: Date.now() + 60_000,
  };

  beforeEach(async () => {
    // Seed a valid session in the real Miniflare KV store
    await env.SESSION_KV.put(TOKEN, JSON.stringify(SESSION));
  });

  it("resolves correctly when KV is fast", async () => {
    const result = await resolveSession(TOKEN, env);
    expect(result.valid).toBe(true);
    expect(result.anonId).toBe("anon-chaos-001");
    expect(result.failedOpen).toBe(false);
  });

  it("fails open when KV latency exceeds the timeout budget", async () => {
    const slowKv = createKvLatencyProxy(env.SESSION_KV, { getDelayMs: 300 });
    const chaosEnv = { ...env, SESSION_KV: slowKv };

    const start = Date.now();
    const result = await resolveSession(TOKEN, chaosEnv);
    const elapsed = Date.now() - start;

    expect(result.valid).toBe(true);
    expect(result.failedOpen).toBe(true);
    // Should have returned in ~150 ms (the timeout), not 300 ms
    expect(elapsed).toBeLessThan(250);
  });

  it("returns invalid for a missing token even under normal latency", async () => {
    const result = await resolveSession("nonexistent-token", env);
    expect(result.valid).toBe(false);
    expect(result.failedOpen).toBe(false);
  });

  it("returns invalid for an expired session", async () => {
    const expiredToken = "expired-token";
    await env.SESSION_KV.put(
      expiredToken,
      JSON.stringify({ anonId: "anon-x", expiresAt: Date.now() - 1000 })
    );
    const result = await resolveSession(expiredToken, env);
    expect(result.valid).toBe(false);
  });

  it("does not hang for more than 200 ms even with 1s KV delay", async () => {
    const verySlowKv = createKvLatencyProxy(env.SESSION_KV, {
      getDelayMs: 1000,
    });
    const chaosEnv = { ...env, SESSION_KV: verySlowKv };

    const t0 = performance.now();
    await resolveSession(TOKEN, chaosEnv);
    const elapsed = performance.now() - t0;

    expect(elapsed).toBeLessThan(200);
  });
});
```

## Rate Limiter Chaos: KV Write Latency

```typescript
// tests/chaos/kv-write-latency.test.ts
import { describe, it, expect } from "vitest";
import { env } from "cloudflare:test";
import { createKvLatencyProxy } from "../helpers/kv-latency-proxy";
import { incrementRateLimit } from "../../src/middleware/rate-limit";

describe("KV write latency chaos — rate limiter", () => {
  it("completes the rate-limit increment within 200 ms under 500 ms KV write delay", async () => {
    const slowKv = createKvLatencyProxy(env.RATE_KV, {
      getDelayMs: 0,
      putDelayMs: 500,
    });
    const chaosEnv = { ...env, RATE_KV: slowKv };

    const t0 = performance.now();
    // The rate limiter should not await the write — fire-and-forget the KV put
    const result = await incrementRateLimit("ip-127-0-0-1", chaosEnv);
    const elapsed = performance.now() - t0;

    // The counter increment result should be returned quickly
    expect(result).toBeDefined();
    expect(elapsed).toBeLessThan(200);
  });
});
```

## Anti-patterns

- Injecting latency via `globalThis.setTimeout` patching — this affects all timers in the test process, making other async code behave incorrectly.
- Using `vi.useFakeTimers` for latency simulation — fake timers advance instantly, defeating the purpose of a real latency budget test; use real `setTimeout`.
- Testing only the happy path and assuming KV is always fast — in Cloudflare's global network, KV consistency windows mean reads can take 100–300 ms for keys not yet propagated.
- Setting `SESSION_TIMEOUT_MS` equal to the test delay — the race condition becomes non-deterministic; keep at least a 2× margin between the inject delay and the budget.
- Forgetting to seed KV before the latency test — without seeded data, `KVNamespace.get` returns `null` regardless of delay, masking whether the timeout actually fired.

## Gotchas

- `@cloudflare/vitest-pool-workers` runs each test file in a fresh Worker isolate; the Miniflare KV store is reset between files unless `kv_persist` is configured in `wrangler.toml`.
- `performance.now()` in the Workers runtime uses the request timestamp as `t=0`; in vitest pool mode it behaves like Node's `performance.now()` — consistent within a test but not across isolate boundaries.
- `Promise.race` does not cancel the losing promise; the underlying KV get still runs to completion in the background. Ensure the Worker does not rely on its side effects in the timeout branch.
- The Proxy approach wraps the JS binding object, not the actual KV TCP connection; this is appropriate for unit/integration chaos tests but does not replicate true network-level degradation.
- Under the Workers runtime, KV `get` calls count against CPU time even if the response is discarded via `Promise.race`.

## Verification

```bash
npx vitest run tests/chaos/kv-latency.test.ts tests/chaos/kv-write-latency.test.ts \
  --reporter=verbose
```

Expected output: all tests green, elapsed-time assertions passing. In CI, add these tests to a
`chaos` test suite that runs nightly rather than on every PR to avoid flakiness from timer
imprecision in loaded CI runners.

## Related

- documentation/docs/policies/testing/chaos-kv-eviction-simulation-workers.md
- documentation/docs/policies/testing/chaos-engineering-cloudflare-workers.md
- documentation/docs/policies/testing/kv-testing-miniflare.md
- documentation/docs/policies/testing/miniflare-kv-ttl-expiry-testing.md
- documentation/docs/policies/testing/vitest-workers-kv-namespace-isolation.md

## Sources

- https://developers.cloudflare.com/kv/reference/how-kv-works/
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- https://developers.cloudflare.com/workers/runtime-apis/performance/
- https://vitest.dev/guide/workspace
- https://developers.cloudflare.com/workers/testing/vitest-integration/
