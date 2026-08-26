# Testing Cloudflare Workers Scheduled Cron Triggers with Vitest

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Worker exports a `scheduled` handler that runs periodic cleanup jobs,
aggregates analytics, or polls external APIs. The handler is hard to test manually
(`wrangler dev` requires a manual `curl` to the `/__scheduled` endpoint), and it's
invisible to standard `fetch`-based Vitest tests. You want unit and integration tests
that exercise `scheduled()` directly, assert on D1/KV/R2 side-effects, and run in CI
without a live Cloudflare account.

## Context

`@cloudflare/vitest-pool-workers` (vitest-pool-workers) exposes a `SELF` helper that
lets tests dispatch simulated `ScheduledEvent`s into the Worker under test. Combined
with Miniflare's in-process D1/KV/R2 emulation, cron handlers become as testable as
fetch handlers. The key is the `scheduledTime` and `cron` fields on the dispatched
event, which mirror what the runtime sends to production Workers.

Stack: Vitest ≥ 2.x, @cloudflare/vitest-pool-workers, Miniflare 4.x, TypeScript, D1.

## Worker Under Test

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  CLEANUP_CRON: string; // "0 3 * * *"
}

export default {
  async fetch(_req: Request, _env: Env): Promise<Response> {
    return new Response("ok");
  },

  async scheduled(
    event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    ctx.waitUntil(runCleanup(event.scheduledTime, env));
  },
} satisfies ExportedHandler<Env>;

async function runCleanup(scheduledTime: number, env: Env): Promise<void> {
  const cutoff = new Date(scheduledTime - 7 * 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 10);

  await env.DB.prepare(
    "DELETE FROM events WHERE created_at < ?"
  )
    .bind(cutoff)
    .run();
}
```

## Vitest + Pool Workers Configuration

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          d1Databases: { DB: "test-db" },
        },
      },
    },
  },
});
```

`wrangler.toml` (test-compatible):

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[[d1_databases]]
binding = "DB"
database_name = "mydb"
database_id = "00000000-0000-0000-0000-000000000000"

[triggers]
crons = ["0 3 * * *"]

[vars]
CLEANUP_CRON = "0 3 * * *"
```

## Dispatching a ScheduledEvent in Tests

```typescript
// src/index.test.ts
import {
  env,
  runInDurableObject,
  SELF,
} from "cloudflare:test";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

// Seed helper
async function seedEvents(db: D1Database, dates: string[]): Promise<void> {
  await db.exec(`
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL
    )
  `);
  for (const d of dates) {
    await db.prepare("INSERT INTO events (created_at) VALUES (?)").bind(d).run();
  }
}

describe("scheduled cleanup", () => {
  beforeEach(async () => {
    // Reset the table for each test
    await (env.DB as D1Database).exec(
      "DROP TABLE IF EXISTS events"
    );
    await seedEvents(env.DB as D1Database, [
      "2026-08-01", // older than 7 days from scheduledTime
      "2026-08-10", // older than 7 days
      "2026-08-20", // within 7 days
      "2026-08-23", // today
    ]);
  });

  it("deletes rows older than 7 days relative to scheduledTime", async () => {
    // scheduledTime = 2026-08-23T03:00:00Z in milliseconds
    const scheduledTime = new Date("2026-08-23T03:00:00Z").getTime();

    // SELF.scheduled() dispatches a ScheduledEvent to the worker
    const result = await SELF.scheduled({
      scheduledTime,
      cron: "0 3 * * *",
    });

    // result.outcome is "ok" or "exception"
    expect(result.outcome).toBe("ok");

    const { results } = await (env.DB as D1Database)
      .prepare("SELECT created_at FROM events ORDER BY created_at")
      .all<{ created_at: string }>();

    expect(results.map((r) => r.created_at)).toEqual([
      "2026-08-20",
      "2026-08-23",
    ]);
  });

  it("is a no-op when no rows are older than 7 days", async () => {
    const scheduledTime = new Date("2020-01-01T03:00:00Z").getTime();

    const result = await SELF.scheduled({ scheduledTime, cron: "0 3 * * *" });
    expect(result.outcome).toBe("ok");

    const { results } = await (env.DB as D1Database)
      .prepare("SELECT COUNT(*) AS n FROM events")
      .all<{ n: number }>();

    // All 4 rows inserted in beforeEach are in the future relative to 2020
    expect(results[0].n).toBe(4);
  });

  it("exposes the cron expression on the event", async () => {
    // Test that the worker can branch on event.cron if it handles multiple crons
    const result = await SELF.scheduled({
      scheduledTime: Date.now(),
      cron: "*/5 * * * *",
    });
    // Worker doesn't branch in this example; just assert outcome is ok
    expect(result.outcome).toBe("ok");
  });
});
```

## Testing Workers with Multiple Cron Expressions

When a Worker handles different cron schedules with different logic:

```typescript
// Multi-cron worker
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    switch (event.cron) {
      case "*/5 * * * *":
        await heartbeat(env);
        break;
      case "0 3 * * *":
        await dailyCleanup(env);
        break;
      default:
        console.warn("unknown cron:", event.cron);
    }
  },
} satisfies ExportedHandler<Env>;
```

Test each branch independently:

```typescript
it("runs heartbeat on 5-minute cron", async () => {
  const result = await SELF.scheduled({
    scheduledTime: Date.now(),
    cron: "*/5 * * * *",
  });
  expect(result.outcome).toBe("ok");
  // assert heartbeat KV key was written
  const val = await (env.KV as KVNamespace).get("heartbeat:last");
  expect(val).not.toBeNull();
});

it("runs daily cleanup on 03:00 cron", async () => {
  const result = await SELF.scheduled({
    scheduledTime: Date.now(),
    cron: "0 3 * * *",
  });
  expect(result.outcome).toBe("ok");
});
```

## Testing Error Paths

```typescript
it("returns outcome 'exception' when the handler throws", async () => {
  // Force an error by dropping the table before the cron runs
  await (env.DB as D1Database).exec("DROP TABLE events");

  const result = await SELF.scheduled({
    scheduledTime: Date.now(),
    cron: "0 3 * * *",
  });

  // vitest-pool-workers captures the throw and sets outcome to "exception"
  expect(result.outcome).toBe("exception");
});
```

## Anti-patterns

- **Manually constructing `ScheduledEvent`** — Do not instantiate `new ScheduledEvent()`.
  Use `SELF.scheduled()` from `cloudflare:test`; it handles the runtime simulation and
  `waitUntil` promise tracking correctly.
- **Asserting before `waitUntil` settles** — `SELF.scheduled()` awaits all
  `ctx.waitUntil()` promises before resolving. Do not add artificial `setTimeout`
  delays; the test helper handles this.
- **Sharing D1 state across tests without a `beforeEach` reset** — Miniflare's in-memory
  D1 persists across tests in the same file unless you explicitly drop/truncate tables.
  Always reset in `beforeEach`.
- **Testing cron logic via `fetch /__scheduled`** — That endpoint is a Wrangler dev
  convenience only; it does not exist in production and is not available in
  vitest-pool-workers. Use `SELF.scheduled()` instead.

## Gotchas

- `SELF.scheduled()` returns `{ outcome: "ok" | "exception" }`. A thrown error in the
  handler does NOT re-throw in the test; check `result.outcome` explicitly.
- `scheduledTime` is a Unix timestamp in **milliseconds** (not seconds). Using seconds
  produces a date in 1970, which silently passes but cuts nothing in date-range queries.
- If your worker uses `event.scheduledTime` to compute relative dates, seed test data
  relative to the exact `scheduledTime` you pass — hardcoded "7 days ago" row dates
  only work for a specific `scheduledTime`.
- The `cron` field on `ScheduledEvent` is a string. Turborepo/Wrangler validate the
  expression format at deploy time; Miniflare does not — you can pass any string in
  tests, which is intentional for branch-coverage testing.

## Verification

```bash
# Run only scheduled-handler tests
pnpm vitest run --reporter=verbose src/index.test.ts

# Expected output:
# ✓ deletes rows older than 7 days relative to scheduledTime
# ✓ is a no-op when no rows are older than 7 days
# ✓ exposes the cron expression on the event
# ✓ returns outcome 'exception' when the handler throws
```

Trigger manually against a local `wrangler dev` instance (supplementary, not a
replacement for unit tests):

```bash
# In one terminal
wrangler dev --local

# In another terminal
curl "http://localhost:8787/__scheduled?cron=0+3+*+*+*"
```

## Related

- `vitest-workers-miniflare-testing-setup.md`
- `vitest-workers-queue-batch-testing.md`
- `miniflare-d1-test-seeding-fixtures.md`
- `miniflare-durable-objects-fake-clock-testing.md`
- `wrangler-dev-local-d1-r2-kv.md`

## Sources

- Cloudflare Workers Scheduled Handlers: https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
- vitest-pool-workers SELF API: https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/
- Miniflare testing docs: https://miniflare.dev/docs/testing
