# Miniflare Durable Objects Fake Clock Testing

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Durable Object alarms fire after a real time delay (minimum 1 second, often minutes or hours). Unit tests that call `state.storage.setAlarm(Date.now() + 60_000)` then wait for the alarm handler to run either hang for a minute or require awkward polling loops. You need a way to advance simulated time without sleeping.

---

## Context

Miniflare v3+ (used by `vitest-pool-workers` under the hood) exposes a `FakeClockDurableObject` helper and `MiniflareTestEnv.clock` that let you manually advance `Date.now()` and trigger pending alarms synchronously inside a test. This is the Workers-native equivalent of Jest's `useFakeTimers` — but wired into the Durable Object storage layer so `state.storage.alarm()` and `state.storage.setAlarm()` obey the fake time.

Stack:

- `miniflare` ^4.0
- `@cloudflare/vitest-pool-workers` ^0.5
- `vitest` ^2.0
- `wrangler` ^4.0

---

## Setting Up the Test Environment

`vitest.config.ts`:

```ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          durableObjects: {
            COUNTER: "Counter",
          },
          // Enable fake timers for all Durable Objects
          fakeTimers: true,
        },
      },
    },
  },
});
```

`wrangler.toml` must declare the DO binding:

```toml
[[durable_objects.bindings]]
name = "COUNTER"
class_name = "Counter"

[[migrations]]
tag = "v1"
new_classes = ["Counter"]
```

---

## Writing the Durable Object Under Test

```ts
// src/counter.ts
export class Counter implements DurableObject {
  private count = 0;

  constructor(private state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/increment") {
      this.count++;
      // Schedule a reset alarm 5 minutes from now
      await this.state.storage.setAlarm(Date.now() + 5 * 60 * 1_000);
      return Response.json({ count: this.count });
    }
    return Response.json({ count: this.count });
  }

  async alarm(): Promise<void> {
    // Alarm fires: reset counter
    this.count = 0;
  }
}
```

---

## Advancing Fake Time in Tests

`@cloudflare/vitest-pool-workers` re-exports `runInDurableObject` and `getMiniflareDurableObjectState` for white-box access:

```ts
import { env, SELF, runInDurableObject } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";

describe("Counter DO alarm", () => {
  let id: DurableObjectId;
  let stub: DurableObjectStub;

  beforeEach(() => {
    id = env.COUNTER.newUniqueId();
    stub = env.COUNTER.get(id);
  });

  it("resets count when alarm fires", async () => {
    // Increment the counter
    const res = await stub.fetch("http://do/increment");
    expect((await res.json<{ count: number }>()).count).toBe(1);

    // Advance time past the 5-minute alarm window
    await runInDurableObject(stub, async (instance, doState) => {
      // Manually advance Miniflare's fake clock by 6 minutes
      await doState.advanceFakeTime(6 * 60 * 1_000);
      // The alarm should now have fired synchronously
    });

    const res2 = await stub.fetch("http://do/");
    expect((await res2.json<{ count: number }>()).count).toBe(0);
  });
});
```

Key: `doState.advanceFakeTime(ms)` drains all alarms whose scheduled time is <= the new fake `Date.now()` before resolving.

---

## Inspecting Pending Alarms Directly

You can assert that an alarm is scheduled without firing it:

```ts
import { runInDurableObject } from "cloudflare:test";

it("schedules an alarm after increment", async () => {
  await stub.fetch("http://do/increment");

  await runInDurableObject(stub, async (_instance, doState) => {
    const alarm = await doState.storage.getAlarm();
    expect(alarm).toBeDefined();
    // Alarm should be ~5 minutes in the future
    const delta = alarm! - Date.now();
    expect(delta).toBeGreaterThan(4 * 60 * 1_000);
    expect(delta).toBeLessThanOrEqual(5 * 60 * 1_000 + 500);
  });
});
```

---

## Testing Alarm Cancellation

```ts
it("cancels the alarm when count reaches zero via reset endpoint", async () => {
  // Set up initial alarm
  await stub.fetch("http://do/increment");

  await runInDurableObject(stub, async (_instance, doState) => {
    // Manually delete the alarm
    await doState.storage.deleteAlarm();
    const alarm = await doState.storage.getAlarm();
    expect(alarm).toBeNull();
  });
});
```

---

## Anti-patterns

- **Real `setTimeout` inside Durable Objects**: `setTimeout` is not supported in the Workers runtime; `state.storage.setAlarm()` is the only scheduling primitive — do not try to polyfill it.
- **`vi.useFakeTimers()` for DO alarms**: Vitest's built-in fake timers operate on the V8 isolate's timer queue, not on Miniflare's alarm storage. They do nothing to trigger `alarm()` handlers.
- **Sleeping in tests**: `await new Promise(r => setTimeout(r, 60_000))` makes CI pipelines unusable. Always use `advanceFakeTime`.
- **Not awaiting `advanceFakeTime`**: It returns a Promise that resolves only after all triggered alarm handlers complete. If you fire and forget it, your assertions race against the handler.

---

## Gotchas

- `fakeTimers: true` in Miniflare config is required; without it `advanceFakeTime` is a no-op and the clock never moves.
- When multiple Durable Objects share a single test worker, each DO instance has its own independent clock state. Advancing time on one stub does not affect another.
- The fake clock starts at the wall-clock time when the test suite begins. If your code checks `Date.now() < someAbsoluteTimestamp` you may need to `advanceFakeTime` to a specific epoch rather than a relative delta.
- Alarm handlers that throw do not re-schedule by default in Miniflare — mirror the production behavior (set the alarm again inside a try/catch in `alarm()`) if you want retry semantics.
- `runInDurableObject` serializes access; it cannot run concurrently with an in-flight `fetch()` to the same stub.

---

## Verification

```bash
# Run only alarm-related tests
pnpm vitest run --reporter=verbose src/counter.test.ts

# Confirm no real sleeps: test suite should finish in < 2 seconds
time pnpm vitest run src/counter.test.ts
```

Expected output: all tests pass, total wall time under 2 s.

---

## Related

- `miniflare-d1-test-seeding-fixtures.md`
- `miniflare-storage-backend-testing.md`
- `miniflare-v4-migration-guide.md`
- `vitest-pool-workers-cloudflare-test-api.md`
- `vitest-workers-miniflare-testing-setup.md`
- `durable-objects-local-debugging.md`

---

## Sources

- Miniflare fake timers API: https://miniflare.dev/testing/fakeTimers
- `@cloudflare/vitest-pool-workers` docs: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Durable Objects alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- `runInDurableObject` reference: https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/#runindurableobject
