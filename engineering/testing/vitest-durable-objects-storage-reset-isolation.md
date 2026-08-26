# Vitest Durable Objects Storage Reset Isolation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Vitest tests for Cloudflare Durable Objects leak state between test cases because the in-memory DO storage (via `@cloudflare/vitest-pool-workers`) persists across tests in the same suite. A counter DO incremented in test A shows the wrong value in test B. You need a reliable pattern to reset DO storage—including `storage.put`, `storage.delete`, alarms, and WebSocket tags—between every test without spawning a new Miniflare process.

## Context

`@cloudflare/vitest-pool-workers` runs each test file in an isolated Worker environment but does not automatically reset Durable Object storage between individual `it()` blocks within the same file. The storage layer is backed by an in-process SQLite store that persists for the lifetime of the pool worker. The correct pattern is to expose a `reset()` RPC method on each DO class and call it in `beforeEach`, or to use unique DO names per test to achieve natural isolation without explicit teardown.

---

## 1. Project Setup

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "COUNTER"
class_name = "Counter"

[[migrations]]
tag = "v1"
new_classes = ["Counter"]
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          durableObjects: { COUNTER: 'Counter' },
        },
      },
    },
  },
});
```

---

## 2. DO Class with Reset RPC

```typescript
// src/counter.ts
import { DurableObject } from 'cloudflare:workers';
import type { Env } from './types';

export class Counter extends DurableObject<Env> {
  async increment(by = 1): Promise<number> {
    const current = (await this.ctx.storage.get<number>('count')) ?? 0;
    const next = current + by;
    await this.ctx.storage.put('count', next);
    return next;
  }

  async get(): Promise<number> {
    return (await this.ctx.storage.get<number>('count')) ?? 0;
  }

  async reset(): Promise<void> {
    await this.ctx.storage.deleteAll();
    // Cancel any pending alarm
    await this.ctx.storage.deleteAlarm();
  }
}
```

---

## 3. Per-test Storage Reset via RPC

```typescript
// tests/counter.test.ts
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';

function getCounter(name: string) {
  const id = env.COUNTER.idFromName(name);
  return env.COUNTER.get(id);
}

const COUNTER_NAME = 'test-counter';

describe('Counter DO', () => {
  beforeEach(async () => {
    await getCounter(COUNTER_NAME).reset();
  });

  it('starts at zero after reset', async () => {
    expect(await getCounter(COUNTER_NAME).get()).toBe(0);
  });

  it('increments correctly', async () => {
    await getCounter(COUNTER_NAME).increment();
    await getCounter(COUNTER_NAME).increment();
    expect(await getCounter(COUNTER_NAME).get()).toBe(2);
  });

  it('does not see previous test state', async () => {
    // This would fail without beforeEach reset if previous test ran
    expect(await getCounter(COUNTER_NAME).get()).toBe(0);
  });
});
```

---

## 4. Unique-name Isolation (No Explicit Reset Required)

When the DO class has no side effects outside its own storage, using a unique name per test eliminates the need for teardown:

```typescript
// tests/counter-isolated.test.ts
import { env } from 'cloudflare:test';
import { it, expect } from 'vitest';
import { randomUUID } from 'node:crypto';

function freshCounter() {
  const id = env.COUNTER.idFromName(`counter-${randomUUID()}`);
  return env.COUNTER.get(id);
}

it('increments from a clean slate', async () => {
  const counter = freshCounter();
  await counter.increment(5);
  expect(await counter.get()).toBe(5);
});

it('another test, completely isolated storage', async () => {
  const counter = freshCounter();
  expect(await counter.get()).toBe(0);
});
```

This approach is simpler but creates many DO instances. Prefer it for stateless-per-test operations; prefer explicit reset for stateful scenarios where baseline data matters.

---

## 5. Resetting Alarm State

DO alarms survive storage resets unless explicitly deleted. Include alarm teardown in the reset RPC:

```typescript
// src/scheduled-counter.ts
import { DurableObject } from 'cloudflare:workers';

export class ScheduledCounter extends DurableObject {
  async scheduleReset(delayMs: number): Promise<void> {
    await this.ctx.storage.put('pendingReset', true);
    await this.ctx.storage.setAlarm(Date.now() + delayMs);
  }

  async alarm(): Promise<void> {
    await this.ctx.storage.delete('pendingReset');
    await this.ctx.storage.put('count', 0);
  }

  async reset(): Promise<void> {
    await this.ctx.storage.deleteAll();
    await this.ctx.storage.deleteAlarm(); // critical: remove pending alarm
  }

  async hasPendingReset(): Promise<boolean> {
    return (await this.ctx.storage.get<boolean>('pendingReset')) ?? false;
  }
}
```

```typescript
// tests/scheduled-counter.test.ts
import { env } from 'cloudflare:test';
import { runInDurableObject } from 'cloudflare:test';
import { it, expect, beforeEach } from 'vitest';

const id = env.SCHEDULED_COUNTER.idFromName('test');
const stub = env.SCHEDULED_COUNTER.get(id);

beforeEach(async () => {
  await stub.reset();
});

it('alarm is cleared on reset', async () => {
  await stub.scheduleReset(5000);
  expect(await stub.hasPendingReset()).toBe(true);

  await stub.reset();

  expect(await stub.hasPendingReset()).toBe(false);
});
```

---

## 6. Bulk Reset Across Multiple DO Instances

When a test suite creates many named DOs, batch the resets in `afterAll` to avoid dangling storage:

```typescript
// tests/helpers/reset-all-dos.ts
import { env } from 'cloudflare:test';

const trackedNames: string[] = [];

export function trackCounter(name: string) {
  if (!trackedNames.includes(name)) trackedNames.push(name);
  return env.COUNTER.get(env.COUNTER.idFromName(name));
}

export async function resetAllCounters(): Promise<void> {
  await Promise.all(
    trackedNames.map((name) =>
      env.COUNTER.get(env.COUNTER.idFromName(name)).reset()
    )
  );
  trackedNames.length = 0;
}
```

```typescript
// tests/multi-counter.test.ts
import { describe, it, expect, afterAll } from 'vitest';
import { trackCounter, resetAllCounters } from './helpers/reset-all-dos';

afterAll(resetAllCounters);

describe('multi-counter suite', () => {
  it('counter A and B are independent', async () => {
    const a = trackCounter('counter-a');
    const b = trackCounter('counter-b');
    await a.increment(3);
    await b.increment(7);
    expect(await a.get()).toBe(3);
    expect(await b.get()).toBe(7);
  });
});
```

---

## Anti-patterns

- **Relying on Miniflare process restart for isolation**: This works but is 5-10x slower than calling `deleteAll()` directly. Use RPC reset instead.
- **Calling `deleteAll()` from the test without an RPC**: `storage.deleteAll()` is only accessible from inside the DO. Tests must call a reset method exposed on the DO stub.
- **Not deleting alarms on reset**: Pending alarms run after `deleteAll()` and can re-seed storage, corrupting the next test's baseline.
- **Sharing one DO name across parallel test files**: `@cloudflare/vitest-pool-workers` may run files in parallel in the same storage backend. Use unique names per file or per test.
- **Using `ctx.id.toString()` as the reset discriminator**: Name-based IDs (`idFromName`) are stable; hash IDs from `newUniqueId()` cannot be reconstructed after test setup.

---

## Gotchas

- `ctx.storage.deleteAll()` does not commit immediately in the Workers runtime; it is queued and runs before the next `await`. Inside tests it is effectively synchronous.
- `runInDurableObject` from `cloudflare:test` allows running arbitrary code inside a DO context for inspection without going through the fetch/RPC surface—useful for verifying internal storage state directly.
- Vitest's `--reporter=verbose` will show DO RPC calls as part of the test, which can be noisy. Use `--reporter=dot` for large DO test suites.
- The `@cloudflare/vitest-pool-workers` pool does not support `isolate: true` per-test isolation for DO storage; that flag affects module isolation, not storage.
- Storage operations inside `reset()` count against the DO's in-flight request budget. For DOs with many storage keys, `deleteAll()` is faster than iterating with `delete()`.

---

## Verification

```bash
# Run DO tests with verbose output to see reset calls
npx vitest run tests/counter.test.ts --reporter=verbose

# Confirm no state leakage by running twice
npx vitest run tests/counter.test.ts --repeat=3

# Check that unique-name tests create isolated instances
npx vitest run tests/counter-isolated.test.ts
```

---

## Related

- `durable-objects-storage-snapshot-testing.md`
- `durable-objects-miniflare-fake-timers.md`
- `durable-objects-alarm-testing-miniflare.md`
- `vitest-cloudflare-pool-workers.md`
- `test-database-isolation.md`

---

## Sources

- `@cloudflare/vitest-pool-workers` docs: https://developers.cloudflare.com/workers/testing/vitest-integration/
- DO Storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- `runInDurableObject` test helper: https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/
- Cloudflare DO limits: https://developers.cloudflare.com/durable-objects/platform/limits/
