# Durable Objects Alarm Testing with Miniflare

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Alarms scheduled inside Durable Objects are time-dependent, making them hard to test deterministically. This article shows how to trigger and assert alarm handlers in Vitest using Miniflare's fake clock.

## Context
Cloudflare Durable Objects expose `this.storage.setAlarm(timestamp)` to schedule future callbacks. In production, the runtime invokes `alarm()` on the DO instance after the timestamp passes. Miniflare 3 exposes `runDurableObjectAlarm` and fake-clock helpers so tests can advance time without real delay. The `@cloudflare/vitest-pool-workers` package wires Miniflare into Vitest's worker pool.

## Setting Up the Test Environment

Configure `vitest.config.ts` to use the Cloudflare worker pool and declare a Durable Object binding:

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          durableObjects: { SCHEDULER: "SchedulerDO" },
        },
      },
    },
  },
});
```

The Durable Object class must be exported from the Worker's entry point so Miniflare can instantiate it:

```typescript
// src/scheduler.ts
export class SchedulerDO implements DurableObject {
  private state: DurableObjectState;
  constructor(state: DurableObjectState) {
    this.state = state;
  }
  async fetch(request: Request): Promise<Response> {
    const delay = Number(new URL(request.url).searchParams.get("delay") ?? 5000);
    await this.state.storage.setAlarm(Date.now() + delay);
    await this.state.storage.put("scheduled", true);
    return new Response("scheduled");
  }
  async alarm(): Promise<void> {
    await this.state.storage.put("fired", true);
    await this.state.storage.delete("scheduled");
  }
}
```

## Writing Alarm Tests

Use `env.SCHEDULER.get(id).fetch()` to schedule an alarm, then advance time via the Miniflare test context:

```typescript
// tests/scheduler.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import {
  env,
  runInDurableObject,
  runDurableObjectAlarm,
} from "cloudflare:test";

describe("SchedulerDO alarms", () => {
  it("sets alarm flag in storage", async () => {
    const id = env.SCHEDULER.idFromName("job-1");
    const stub = env.SCHEDULER.get(id);

    const res = await stub.fetch("https://example.com/?delay=10000");
    expect(res.status).toBe(200);

    await runInDurableObject(stub, async (instance, state) => {
      const scheduled = await state.storage.get<boolean>("scheduled");
      expect(scheduled).toBe(true);
    });
  });

  it("fires alarm and updates storage", async () => {
    const id = env.SCHEDULER.idFromName("job-2");
    const stub = env.SCHEDULER.get(id);

    await stub.fetch("https://example.com/?delay=60000");
    // Trigger the alarm without waiting 60 s
    await runDurableObjectAlarm(stub);

    await runInDurableObject(stub, async (_instance, state) => {
      expect(await state.storage.get<boolean>("fired")).toBe(true);
      expect(await state.storage.get<boolean>("scheduled")).toBeUndefined();
    });
  });
});
```

## Testing Alarm Rescheduling Logic

Some DOs reschedule themselves from within `alarm()`. Assert the new alarm time to verify the reschedule:

```typescript
// src/polling-do.ts
export class PollingDO implements DurableObject {
  constructor(private state: DurableObjectState) {}
  async alarm(): Promise<void> {
    await this.state.storage.put("lastRun", Date.now());
    // Reschedule 30 s from now
    await this.state.storage.setAlarm(Date.now() + 30_000);
  }
}
```

```typescript
// tests/polling.test.ts
import { it, expect } from "vitest";
import { env, runInDurableObject, runDurableObjectAlarm } from "cloudflare:test";

it("reschedules alarm after each fire", async () => {
  const stub = env.POLLING.get(env.POLLING.idFromName("p1"));
  // Manually prime the first alarm
  await runInDurableObject(stub, async (_i, state) => {
    await state.storage.setAlarm(Date.now() + 5_000);
  });

  await runDurableObjectAlarm(stub);

  await runInDurableObject(stub, async (_i, state) => {
    const alarm = await state.storage.getAlarm();
    expect(alarm).toBeGreaterThan(Date.now());
    expect(await state.storage.get<number>("lastRun")).toBeLessThanOrEqual(Date.now());
  });
});
```

## Testing Alarm Cancellation

Verify that deleting an alarm before it fires prevents `alarm()` from running:

```typescript
// tests/cancel-alarm.test.ts
import { it, expect, vi } from "vitest";
import { env, runInDurableObject, runDurableObjectAlarm } from "cloudflare:test";

it("does not fire after alarm is cancelled", async () => {
  const stub = env.SCHEDULER.get(env.SCHEDULER.idFromName("cancel-test"));

  await stub.fetch("https://example.com/?delay=5000");

  await runInDurableObject(stub, async (_i, state) => {
    await state.storage.deleteAlarm();
  });

  // runDurableObjectAlarm returns false when no alarm is pending
  const fired = await runDurableObjectAlarm(stub);
  expect(fired).toBe(false);
});
```

## Anti-patterns
- Never use `setTimeout` in tests to wait for alarm delays — always use `runDurableObjectAlarm` to trigger synchronously.
- Do not share a single DO id across `it` blocks; alarm state persists between calls in the same test run.
- Avoid asserting `Date.now()` directly inside `runInDurableObject`; use relative comparisons or snapshot the value before the alarm fires.

## Gotchas
- `runDurableObjectAlarm` only works when the DO has a pending alarm set; calling it on an instance without an alarm returns `false` rather than throwing.
- Miniflare does not enforce the 30-day maximum alarm scheduling limit — production code will reject alarms beyond that window.
- If `wrangler.toml` defines `[durable_objects]` bindings, the class name must match exactly; mismatches silently fall back to default behavior.
- The `cloudflare:test` module is only available inside `@cloudflare/vitest-pool-workers`; it cannot be used in a plain Node Vitest environment.

## Verification
Run `npx vitest run tests/scheduler.test.ts` — all tests should pass without any real time elapsing. Add `--reporter=verbose` to confirm each alarm path is exercised.

## Related
- [durable-objects-miniflare-fake-timers.md](durable-objects-miniflare-fake-timers.md)
- [workers-cron-trigger-integration-testing.md](workers-cron-trigger-integration-testing.md)
- [vitest-cloudflare-pool-workers.md](vitest-cloudflare-pool-workers.md)

## Sources
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
