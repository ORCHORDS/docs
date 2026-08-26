# Durable Objects Unit Testing with Miniflare and Fake Timers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You have a Durable Object (DO) that manages stateful sessions, rate limiters, or scheduled alarms. Your CI pipeline needs deterministic, sub-second tests that exercise alarm callbacks, `setTimeout`-style logic, and storage reads/writes without deploying to Cloudflare or waiting real wall-clock time.

Typical pain points:

- Alarms fire asynchronously; tests that `await stub.fetch(...)` miss the alarm side-effects.
- `Date.now()` calls in alarm handlers produce non-deterministic timestamps.
- Running against the real `wrangler dev` adds seconds of startup latency per test file.
- Concurrent tests share DO instances when namespace isolation is not enforced.

---

## Context

Miniflare 3 ships as `@cloudflare/vitest-pool-workers`, which integrates directly with Vitest's worker pool and provides:

- An in-process `DurableObjectNamespace` mock backed by SQLite.
- A fake clock implementation that advances on demand (`runMicrotasks`, `advanceFakeTime`).
- Per-test isolation via `isolatedStorage: true`.

Fake timers let you call `env.MY_DO.get(id).fetch(...)`, then advance the clock by 1 hour to trigger an alarm, then assert the resulting storage state—all within a single synchronous-looking test.

Stack: **Cloudflare Workers + Durable Objects, Vitest 2, `@cloudflare/vitest-pool-workers` ≥ 0.5**.

---

## 1. Project Setup

### `vitest.config.ts`

```typescript
import { defineConfig } from "vitest/config";
import { defineWorkersProject } from "@cloudflare/vitest-pool-workers/config";

export default defineConfig({
  test: {
    projects: [
      defineWorkersProject({
        test: {
          poolOptions: {
            workers: {
              wranglerConfigPath: "./wrangler.toml",
              isolatedStorage: true, // Each test gets its own DO storage
              miniflare: {
                compatibilityDate: "2025-09-01",
                compatibilityFlags: ["nodejs_compat"],
              },
            },
          },
        },
      }),
    ],
  },
});
```

### `wrangler.toml` (excerpt)

```toml
name = "my-worker"
compatibility_date = "2025-09-01"

[[durable_objects.bindings]]
name = "RATE_LIMITER"
class_name = "RateLimiter"

[[migrations]]
tag = "v1"
new_classes = ["RateLimiter"]
```

### Install

```bash
npm install --save-dev vitest @cloudflare/vitest-pool-workers
```

---

## 2. The Durable Object Under Test

```typescript
// src/rate-limiter.ts
export class RateLimiter implements DurableObject {
  private storage: DurableObjectStorage;

  constructor(state: DurableObjectState, _env: Env) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();
    const windowStart = (await this.storage.get<number>("windowStart")) ?? now;
    const count = (await this.storage.get<number>("count")) ?? 0;

    const WINDOW_MS = 60_000; // 1 minute
    const LIMIT = 10;

    if (now - windowStart > WINDOW_MS) {
      // Reset window
      await this.storage.put("windowStart", now);
      await this.storage.put("count", 1);
      await this.storage.setAlarm(now + WINDOW_MS);
      return new Response("ok", { status: 200 });
    }

    if (count >= LIMIT) {
      return new Response("rate limited", { status: 429 });
    }

    await this.storage.put("count", count + 1);
    return new Response("ok", { status: 200 });
  }

  async alarm(): Promise<void> {
    // Alarm fires at end of window; clear state for next window
    await this.storage.deleteAll();
  }
}
```

---

## 3. Basic DO Fetch Tests

```typescript
// tests/rate-limiter.test.ts
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";

// Helper: get a stable DO stub for the same logical key
function getLimiterStub(key: string) {
  const id = env.RATE_LIMITER.idFromName(key);
  return env.RATE_LIMITER.get(id);
}

describe("RateLimiter Durable Object", () => {
  it("allows requests under the limit", async () => {
    const stub = getLimiterStub("user-1");
    const responses: Response[] = [];

    for (let i = 0; i < 5; i++) {
      responses.push(await stub.fetch("http://do/check"));
    }

    expect(responses.every((r) => r.status === 200)).toBe(true);
  });

  it("rejects the 11th request with 429", async () => {
    const stub = getLimiterStub("user-2");

    for (let i = 0; i < 10; i++) {
      await stub.fetch("http://do/check");
    }

    const response = await stub.fetch("http://do/check");
    expect(response.status).toBe(429);
  });

  it("isolates state between different key names", async () => {
    const stubA = getLimiterStub("isolation-a");
    const stubB = getLimiterStub("isolation-b");

    // Exhaust A
    for (let i = 0; i < 10; i++) {
      await stubA.fetch("http://do/check");
    }

    // B should still be fresh
    const response = await stubB.fetch("http://do/check");
    expect(response.status).toBe(200);
  });
});
```

---

## 4. Fake Timer Integration for Alarm Testing

```typescript
// tests/rate-limiter-alarms.test.ts
import { env, runInDurableObject } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import { RateLimiter } from "../src/rate-limiter";

describe("RateLimiter alarm resets state", () => {
  it("clears count after alarm fires", async () => {
    const id = env.RATE_LIMITER.idFromName("alarm-test");
    const stub = env.RATE_LIMITER.get(id);

    // Exhaust the limit
    for (let i = 0; i < 10; i++) {
      await stub.fetch("http://do/check");
    }

    // Confirm we're rate limited
    expect((await stub.fetch("http://do/check")).status).toBe(429);

    // Fire the alarm directly inside the DO's context
    await runInDurableObject(stub, async (instance: RateLimiter) => {
      await instance.alarm();
    });

    // State cleared — next request succeeds
    const afterAlarm = await stub.fetch("http://do/check");
    expect(afterAlarm.status).toBe(200);
  });

  it("sets next alarm on first request of new window", async () => {
    const id = env.RATE_LIMITER.idFromName("alarm-schedule-test");
    const stub = env.RATE_LIMITER.get(id);

    await stub.fetch("http://do/check");

    await runInDurableObject(stub, async (_instance: RateLimiter, state) => {
      const alarm = await state.storage.getAlarm();
      expect(alarm).not.toBeNull();
      // Alarm should be ~60 seconds in the future (within 1 second tolerance)
      expect(alarm! - Date.now()).toBeGreaterThan(59_000);
      expect(alarm! - Date.now()).toBeLessThan(61_000);
    });
  });
});
```

---

## 5. Advancing Fake Time Across Window Boundaries

```typescript
// tests/rate-limiter-time-travel.test.ts
import {
  env,
  runInDurableObject,
  advanceFakeTime,
  runMicrotasks,
} from "cloudflare:test";
import { describe, it, expect } from "vitest";
import { RateLimiter } from "../src/rate-limiter";

describe("RateLimiter time-travel scenarios", () => {
  it("resets window automatically when 60 seconds elapse", async () => {
    const id = env.RATE_LIMITER.idFromName("time-travel");
    const stub = env.RATE_LIMITER.get(id);

    // Fill up the limit within the first window
    for (let i = 0; i < 10; i++) {
      await stub.fetch("http://do/check");
    }
    expect((await stub.fetch("http://do/check")).status).toBe(429);

    // Advance fake clock past the 60-second window
    await advanceFakeTime(61_000);
    await runMicrotasks(); // Let pending microtasks (alarm callbacks) settle

    // The alarm fires automatically; DO resets its state
    // First request of next window should succeed
    const response = await stub.fetch("http://do/check");
    expect(response.status).toBe(200);
  });

  it("does not reset before window expires", async () => {
    const id = env.RATE_LIMITER.idFromName("no-early-reset");
    const stub = env.RATE_LIMITER.get(id);

    for (let i = 0; i < 10; i++) {
      await stub.fetch("http://do/check");
    }

    // Advance only 30 seconds — window still open
    await advanceFakeTime(30_000);
    await runMicrotasks();

    const response = await stub.fetch("http://do/check");
    expect(response.status).toBe(429);
  });

  it("handles sequential windows correctly", async () => {
    const id = env.RATE_LIMITER.idFromName("sequential-windows");
    const stub = env.RATE_LIMITER.get(id);

    for (const _window of [1, 2, 3]) {
      // Use limit
      for (let i = 0; i < 10; i++) {
        await stub.fetch("http://do/check");
      }
      expect((await stub.fetch("http://do/check")).status).toBe(429);

      // Advance to next window
      await advanceFakeTime(61_000);
      await runMicrotasks();
    }

    // After 3 windows, still works
    expect((await stub.fetch("http://do/check")).status).toBe(200);
  });
});
```

---

## 6. Storage Inspection via `runInDurableObject`

```typescript
// tests/rate-limiter-storage.test.ts
import { env, runInDurableObject } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import { RateLimiter } from "../src/rate-limiter";

describe("RateLimiter storage state", () => {
  it("stores count and windowStart after first request", async () => {
    const id = env.RATE_LIMITER.idFromName("storage-inspect");
    const stub = env.RATE_LIMITER.get(id);

    const before = Date.now();
    await stub.fetch("http://do/check");

    await runInDurableObject(stub, async (_instance: RateLimiter, state) => {
      const count = await state.storage.get<number>("count");
      const windowStart = await state.storage.get<number>("windowStart");

      expect(count).toBe(1);
      expect(windowStart).toBeGreaterThanOrEqual(before);
      expect(windowStart).toBeLessThanOrEqual(Date.now());
    });
  });

  it("increments count monotonically", async () => {
    const id = env.RATE_LIMITER.idFromName("monotonic-count");
    const stub = env.RATE_LIMITER.get(id);

    for (let expected = 1; expected <= 5; expected++) {
      await stub.fetch("http://do/check");

      await runInDurableObject(stub, async (_: RateLimiter, state) => {
        const count = await state.storage.get<number>("count");
        expect(count).toBe(expected);
      });
    }
  });

  it("leaves storage empty after alarm", async () => {
    const id = env.RATE_LIMITER.idFromName("post-alarm-empty");
    const stub = env.RATE_LIMITER.get(id);

    await stub.fetch("http://do/check");

    await runInDurableObject(stub, async (instance: RateLimiter) => {
      await instance.alarm();
    });

    await runInDurableObject(stub, async (_: RateLimiter, state) => {
      const all = await state.storage.list();
      expect(all.size).toBe(0);
    });
  });
});
```

---

## Anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Sharing one DO key across tests | State leaks between tests causing order-dependence | Use unique keys per test (`idFromName(test.name)`) or rely on `isolatedStorage: true` |
| `await new Promise(resolve => setTimeout(resolve, 60000))` | Waits real wall-clock time; slow and brittle | Use `advanceFakeTime` + `runMicrotasks` |
| Asserting alarm side-effects without `runMicrotasks` | Alarm callbacks still pending; assertions race | Always call `await runMicrotasks()` after `advanceFakeTime` |
| Testing alarm logic through fetch only | Cannot reach alarm handler without time travel or direct invocation | Use `runInDurableObject` to call `instance.alarm()` directly |
| `new RateLimiter(state, env)` in unit tests | Requires manual stub construction for `DurableObjectState` | Use `runInDurableObject` which injects the real state handle |
| Forgetting `isolatedStorage: true` | Tests pollute each other's DO storage | Set it in `vitest.config.ts` pool options |

---

## Gotchas

- **`advanceFakeTime` is async** — it must be `await`-ed; forgetting `await` means the clock hasn't moved before assertions run.
- **`runInDurableObject` runs inside the worker process** — you cannot import Node.js modules or use `jest.fn()` inside its callback; use `vi.fn()` or plain TypeScript.
- **Alarm scheduling is per-storage** — if `isolatedStorage: true` is set, each test's alarm list is isolated; if you reuse a key across tests without isolation, alarms from test A can fire during test B.
- **`wrangler.toml` must list all DO classes** under `[[durable_objects.bindings]]` even for tests; missing entries cause `TypeError: env.MY_DO is undefined`.
- **`idFromName` vs `newUniqueId`** — `idFromName` is deterministic (good for stable test fixtures); `newUniqueId` generates a random ID each call (good for ensuring zero cross-test sharing).
- **`Date.now()` inside DOs uses the fake clock** when Miniflare's fake timers are active; ensure your DO code does not cache `Date.now()` at module load time.

---

## Verification

```bash
# Run only DO tests
npx vitest run tests/rate-limiter*.test.ts

# Run with verbose output to see alarm timing
npx vitest run --reporter=verbose tests/rate-limiter-time-travel.test.ts

# Expected output (all green):
# ✓ allows requests under the limit
# ✓ rejects the 11th request with 429
# ✓ clears count after alarm fires
# ✓ sets next alarm on first request of new window
# ✓ resets window automatically when 60 seconds elapse
# ✓ handles sequential windows correctly
```

CI integration:

```yaml
# .github/workflows/test.yml
- name: Run DO unit tests
  run: npx vitest run --project workers
  env:
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

---

## Related

- [`miniflare-d1-integration-testing.md`](miniflare-d1-integration-testing.md) — D1 integration testing patterns with Miniflare
- [`kv-testing-miniflare.md`](kv-testing-miniflare.md) — KV namespace reads/writes with Miniflare
- [`vitest-cloudflare-pool-workers.md`](vitest-cloudflare-pool-workers.md) — `@cloudflare/vitest-pool-workers` configuration reference
- [`jest-timer-fakes.md`](jest-timer-fakes.md) — Fake timer patterns (Jest/Vitest equivalent concepts)
- [`test-doubles-cloudflare-workers.md`](test-doubles-cloudflare-workers.md) — General Workers test double patterns

---

## Sources

- [Cloudflare Docs — Durable Objects](https://developers.cloudflare.com/durable-objects/)
- [Cloudflare Docs — Testing Durable Objects with Miniflare](https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/#durable-objects)
- [`@cloudflare/vitest-pool-workers` README](https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers)
- [Vitest Fake Timers](https://vitest.dev/guide/mocking.html#timers)
- [Miniflare Source — Durable Objects](https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare)
