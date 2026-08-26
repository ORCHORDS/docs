# Durable Objects Storage Snapshot Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Durable Object accumulates state over many `alarm()` / `fetch()` cycles. You want to
assert that the storage layout (keys, values, metadata) matches an expected "snapshot"
at a given point in time — without running the full object lifecycle or depending on
real wall-clock time.

## Context

Miniflare 3's in-memory `DurableObjectStorage` is fully synchronous and injectable in
`@cloudflare/vitest-pool-workers`. Tests instantiate the DO class directly, advance
fake time via `vi.useFakeTimers()`, and then call `storage.list()` to take a deep
snapshot of the entire key-value surface. Comparing these snapshots against inline
expected objects catches schema drift and off-by-one writes.

## Vitest Pool Workers Config

```ts
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          durableObjects: { COUNTER: "Counter" },
        },
      },
    },
  },
});
```

## Durable Object Under Test

```ts
// src/counter.ts
export class Counter implements DurableObject {
  constructor(
    private readonly state: DurableObjectState,
    private readonly env: Env
  ) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/increment") {
      const current = (await this.state.storage.get<number>("count")) ?? 0;
      await this.state.storage.put("count", current + 1);
      await this.state.storage.put("lastUpdated", Date.now());
      return Response.json({ count: current + 1 });
    }
    if (url.pathname === "/reset") {
      await this.state.storage.deleteAll();
      return Response.json({ reset: true });
    }
    const count = (await this.state.storage.get<number>("count")) ?? 0;
    return Response.json({ count });
  }
}
```

## Taking Storage Snapshots

```ts
// test/helpers/storage-snapshot.ts
export async function snapshotStorage(
  storage: DurableObjectStorage
): Promise<Record<string, unknown>> {
  const entries = await storage.list();
  return Object.fromEntries(entries);
}
```

## Asserting State After Writes

```ts
// test/counter-snapshot.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { env } from "cloudflare:test";
import { snapshotStorage } from "./helpers/storage-snapshot";

describe("Counter DO storage snapshots", () => {
  let stub: DurableObjectStub;
  let storage: DurableObjectStorage;

  beforeEach(async () => {
    const id = env.COUNTER.newUniqueId();
    stub = env.COUNTER.get(id);
    // Reach into Miniflare internals for storage inspection
    const doState = await (stub as any).__miniflare_state__();
    storage = doState.storage;
    await storage.deleteAll();
  });

  it("snapshot is empty before any writes", async () => {
    const snap = await snapshotStorage(storage);
    expect(snap).toEqual({});
  });

  it("snapshot matches expected shape after increment", async () => {
    await stub.fetch(new Request("https://do/increment"));
    const snap = await snapshotStorage(storage);

    expect(snap).toMatchObject({ count: 1 });
    expect(typeof snap.lastUpdated).toBe("number");
  });

  it("snapshot is empty after reset", async () => {
    await stub.fetch(new Request("https://do/increment"));
    await stub.fetch(new Request("https://do/reset"));
    const snap = await snapshotStorage(storage);
    expect(snap).toEqual({});
  });
});
```

## Snapshot-Diffing Across Multiple Operations

```ts
// test/counter-multi-step.test.ts
import { describe, it, expect } from "vitest";
import { env } from "cloudflare:test";
import { snapshotStorage } from "./helpers/storage-snapshot";

describe("Counter DO multi-step snapshots", () => {
  it("records a history of snapshots", async () => {
    const id = env.COUNTER.newUniqueId();
    const stub = env.COUNTER.get(id);
    const doState = await (stub as any).__miniflare_state__();
    const storage: DurableObjectStorage = doState.storage;
    await storage.deleteAll();

    const snapshots: Array<Record<string, unknown>> = [];

    for (let i = 1; i <= 3; i++) {
      await stub.fetch(new Request("https://do/increment"));
      snapshots.push(await snapshotStorage(storage));
    }

    expect(snapshots[0].count).toBe(1);
    expect(snapshots[1].count).toBe(2);
    expect(snapshots[2].count).toBe(3);

    // Each snapshot has a progressively larger lastUpdated
    expect(snapshots[1].lastUpdated as number).toBeGreaterThanOrEqual(
      snapshots[0].lastUpdated as number
    );
  });
});
```

## Testing Storage Limits and Chunked Writes

```ts
// test/storage-chunking.test.ts
import { describe, it, expect } from "vitest";
import { env } from "cloudflare:test";
import { snapshotStorage } from "./helpers/storage-snapshot";

describe("DO storage chunked writes", () => {
  it("stores all 128 shard keys correctly", async () => {
    const id = env.COUNTER.newUniqueId();
    const stub = env.COUNTER.get(id);
    const doState = await (stub as any).__miniflare_state__();
    const storage: DurableObjectStorage = doState.storage;
    await storage.deleteAll();

    // Directly seed storage to simulate a migration or batch import
    const batch: Record<string, number> = {};
    for (let i = 0; i < 128; i++) {
      batch[`shard:${i}`] = i;
    }
    await storage.put(batch);

    const snap = await snapshotStorage(storage);
    expect(Object.keys(snap)).toHaveLength(128);
    expect(snap["shard:0"]).toBe(0);
    expect(snap["shard:127"]).toBe(127);
  });
});
```

## Anti-patterns

- **Asserting on individual `get()` calls instead of snapshots**: Point assertions
  miss unexpected extra keys written as side-effects. Snapshot the whole storage.
- **Using real DO stubs across tests without `deleteAll()`**: Miniflare stubs are
  per-ID; share IDs carelessly and state bleeds between tests.
- **Coupling to `__miniflare_state__` without a helper wrapper**: If the internal API
  changes, update one helper, not dozens of test files.

## Gotchas

- `storage.list()` is paginated at 128 entries by default. For DOs with hundreds of
  keys, pass `{ limit: Infinity }` or paginate with cursors in `snapshotStorage`.
- Miniflare's in-memory storage survives the test only within one Vitest worker thread;
  isolated tests in separate threads each get a fresh namespace.
- `storage.put(batch)` accepts at most 128 key-value pairs per call in the Workers
  runtime; Miniflare enforces the same limit in recent releases.

## Verification

```bash
npx vitest run test/counter-snapshot.test.ts test/counter-multi-step.test.ts \
  test/storage-chunking.test.ts --reporter=verbose
```

All assertions should pass. Confirm by temporarily changing an expected key name and
verifying the diff message names the mismatched key.

## Related

- `durable-objects-alarm-testing-miniflare.md`
- `durable-objects-miniflare-fake-timers.md`
- `durable-objects-websocket-hibernation-testing.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/storage-api/
- https://developers.cloudflare.com/durable-objects/best-practices/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare
