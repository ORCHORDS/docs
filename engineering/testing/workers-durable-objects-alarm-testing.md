# Testing Durable Object Alarms with Miniflare

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Durable Object schedules recurring alarms — for example to flush a batched write buffer to D1 every 30 seconds — and you need to verify that the alarm handler fires, mutates state correctly, and reschedules itself without waiting for real-world time to advance. Live integration tests that sleep for 30+ seconds are impractical in CI.

---

## Context

Durable Object alarms are set via `this.ctx.storage.setAlarm(timestamp)` and fire by calling the DO's `alarm()` method. Miniflare, the local Workers runtime used inside `@cloudflare/vitest-pool-workers`, exposes a `runDurableObjectAlarm(stub)` helper that fires a pending alarm immediately without advancing the wall clock. You can combine this with Miniflare's `getMiniflareDurableObjectStorage` to inspect raw KV storage values after the alarm fires, making it possible to assert both side effects (D1 rows written) and internal state (alarm rescheduled or cleared).

---

## Setup / Config

`wrangler.toml`:
```toml
[[durable_objects.bindings]]
name = "WRITE_BUFFER"
class_name = "WriteBufferDO"

[[d1_databases]]
binding = "DB"
database_name = "orchords-local"
database_id = "00000000-0000-0000-0000-000000000000"
```

`vitest.config.ts`:
```typescript
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          durableObjects: { WRITE_BUFFER: "WriteBufferDO" },
          d1Databases: ["DB"],
        },
      },
    },
  },
});
```

`src/write-buffer-do.ts`:
```typescript
const FLUSH_INTERVAL_MS = 30_000;

export interface Env {
  DB: D1Database;
}

interface BufferedEvent {
  trackId: string;
  count: number;
}

export class WriteBufferDO implements DurableObject {
  private readonly storage: DurableObjectStorage;
  private readonly db: D1Database;

  constructor(state: DurableObjectState, env: Env) {
    this.storage = state.storage;
    this.db = env.DB;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/increment") {
      const { trackId } = await request.json<{ trackId: string }>();
      const current = (await this.storage.get<number>(`count:${trackId}`)) ?? 0;
      await this.storage.put(`count:${trackId}`, current + 1);

      // Schedule flush alarm if not already set
      const existing = await this.storage.getAlarm();
      if (!existing) {
        await this.storage.setAlarm(Date.now() + FLUSH_INTERVAL_MS);
      }

      return new Response("ok");
    }

    return new Response("Not Found", { status: 404 });
  }

  async alarm(): Promise<void> {
    // Read all buffered counts
    const entries = await this.storage.list<number>({ prefix: "count:" });

    if (entries.size === 0) return;

    // Flush to D1
    const stmt = this.db.prepare(
      `INSERT INTO track_play_counts (track_id, play_count, flushed_at)
       VALUES (?, ?, unixepoch())
       ON CONFLICT (track_id) DO UPDATE SET
         play_count  = play_count + excluded.play_count,
         flushed_at  = excluded.flushed_at`
    );

    const batch = [...entries.entries()].map(([key, count]) =>
      stmt.bind(key.replace("count:", ""), count)
    );

    await this.db.batch(batch);

    // Clear buffered counts
    await this.storage.delete([...entries.keys()]);

    // Reschedule alarm for the next interval
    await this.storage.setAlarm(Date.now() + FLUSH_INTERVAL_MS);
  }
}
```

---

## Test Implementation

`src/write-buffer-do.test.ts`:
```typescript
import {
  env,
  createExecutionContext,
  runDurableObjectAlarm,
  getMiniflareDurableObjectStorage,
} from "cloudflare:test";
import { describe, it, expect, beforeAll, afterEach } from "vitest";

async function getStub(): Promise<DurableObjectStub> {
  const id = env.WRITE_BUFFER.idFromName("test-buffer");
  return env.WRITE_BUFFER.get(id);
}

beforeAll(async () => {
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS track_play_counts (
      track_id   TEXT PRIMARY KEY,
      play_count INTEGER NOT NULL DEFAULT 0,
      flushed_at INTEGER
    )
  `);
});

afterEach(async () => {
  await env.DB.exec("DELETE FROM track_play_counts");
  // Reset DO storage between tests by getting a fresh name-derived ID
});

describe("WriteBufferDO alarms", () => {
  it("flushes buffered counts to D1 when alarm fires", async () => {
    const stub = await getStub();
    const ctx = createExecutionContext();

    // Buffer two increments for track-a
    await stub.fetch(new Request("http://do/increment", {
      method: "POST",
      body: JSON.stringify({ trackId: "track-a" }),
      headers: { "Content-Type": "application/json" },
    }));
    await stub.fetch(new Request("http://do/increment", {
      method: "POST",
      body: JSON.stringify({ trackId: "track-a" }),
      headers: { "Content-Type": "application/json" },
    }));
    // One increment for track-b
    await stub.fetch(new Request("http://do/increment", {
      method: "POST",
      body: JSON.stringify({ trackId: "track-b" }),
      headers: { "Content-Type": "application/json" },
    }));

    // Fire the alarm immediately — no real-world wait
    await runDurableObjectAlarm(stub);

    const rows = await env.DB.prepare(
      "SELECT track_id, play_count FROM track_play_counts ORDER BY track_id"
    ).all<{ track_id: string; play_count: number }>();

    expect(rows.results).toEqual([
      { track_id: "track-a", play_count: 2 },
      { track_id: "track-b", play_count: 1 },
    ]);
  });

  it("clears in-memory buffer after flush", async () => {
    const stub = await getStub();

    await stub.fetch(new Request("http://do/increment", {
      method: "POST",
      body: JSON.stringify({ trackId: "track-c" }),
      headers: { "Content-Type": "application/json" },
    }));

    await runDurableObjectAlarm(stub);

    // Inspect raw DO storage — count key should be gone
    const id = env.WRITE_BUFFER.idFromName("test-buffer");
    const storage = await getMiniflareDurableObjectStorage(id);
    const keys = await storage.list({ prefix: "count:" });

    expect(keys.size).toBe(0);
  });

  it("reschedules alarm after flush", async () => {
    const stub = await getStub();

    await stub.fetch(new Request("http://do/increment", {
      method: "POST",
      body: JSON.stringify({ trackId: "track-d" }),
      headers: { "Content-Type": "application/json" },
    }));

    await runDurableObjectAlarm(stub);

    // The alarm handler calls setAlarm() again — storage should have a future alarm
    const id = env.WRITE_BUFFER.idFromName("test-buffer");
    const storage = await getMiniflareDurableObjectStorage(id);
    const nextAlarm = await storage.getAlarm();

    expect(nextAlarm).not.toBeNull();
    expect(nextAlarm!).toBeGreaterThan(Date.now());
  });

  it("skips flush and does not reschedule when buffer is empty", async () => {
    const stub = await getStub();

    // Fire alarm without buffering anything — simulates spurious wakeup
    await runDurableObjectAlarm(stub);

    const count = await env.DB.prepare(
      "SELECT COUNT(*) as cnt FROM track_play_counts"
    ).first<{ cnt: number }>();
    expect(count?.cnt).toBe(0);

    const id = env.WRITE_BUFFER.idFromName("test-buffer");
    const storage = await getMiniflareDurableObjectStorage(id);
    // No rescheduled alarm because handler returns early
    const nextAlarm = await storage.getAlarm();
    expect(nextAlarm).toBeNull();
  });

  it("accumulates counts across multiple flush cycles", async () => {
    const stub = await getStub();

    // First cycle
    await stub.fetch(new Request("http://do/increment", {
      method: "POST",
      body: JSON.stringify({ trackId: "track-e" }),
      headers: { "Content-Type": "application/json" },
    }));
    await runDurableObjectAlarm(stub);

    // Second cycle
    await stub.fetch(new Request("http://do/increment", {
      method: "POST",
      body: JSON.stringify({ trackId: "track-e" }),
      headers: { "Content-Type": "application/json" },
    }));
    await runDurableObjectAlarm(stub);

    const row = await env.DB.prepare(
      "SELECT play_count FROM track_play_counts WHERE track_id = 'track-e'"
    ).first<{ play_count: number }>();

    expect(row?.play_count).toBe(2);
  });
});
```

---

## Anti-patterns

- **Using `setTimeout` to wait for alarms** — the local DO alarm does not run on a real timer; you must call `runDurableObjectAlarm()` explicitly.
- **Testing alarm scheduling via `Date.now()` comparisons without faking the clock** — the next alarm timestamp is relative to the moment the handler runs; use `toBeGreaterThan(Date.now())` loosely or fix `Date.now` with `vi.setSystemTime()`.
- **Sharing a single DO stub identity across tests** — DO storage persists within the Miniflare session; use unique `idFromName()` strings per test or delete keys in `afterEach`.
- **Asserting `alarm()` return value** — the platform ignores the return value; assert on side effects (D1 rows, storage state) instead.

---

## Gotchas

- `runDurableObjectAlarm(stub)` throws if no alarm is currently scheduled; always buffer at least one event before calling it, or guard with `storage.getAlarm() !== null`.
- `getMiniflareDurableObjectStorage` requires the DO `id` object (from `idFromName`/`idFromString`), **not** the stub — they are distinct values.
- The `alarm()` method receives no arguments; all context must come from `this.storage`.
- Batching D1 statements with `db.batch()` is the only way to write multiple rows atomically in a single alarm invocation; individual `await db.prepare().run()` calls inside a loop are slower and not atomic.

---

## Verification

```bash
# Run DO alarm tests
npx vitest run src/write-buffer-do.test.ts

# List scheduled alarms in local dev
npx wrangler dev --local  # then inspect the Miniflare REPL for alarm state

# Check D1 flush results
npx wrangler d1 execute orchords-local --local --command "SELECT * FROM track_play_counts"
```

---

## Related

- `workers-d1-migration-test-vitest.md`
- `workers-queue-consumer-testing-vitest.md`

---

## Sources

- Durable Object Alarms Docs — https://developers.cloudflare.com/durable-objects/api/alarms/
- Miniflare runDurableObjectAlarm — https://miniflare.dev/testing/durable-objects#alarms
- Vitest Pool Workers — https://developers.cloudflare.com/workers/testing/vitest-integration/
