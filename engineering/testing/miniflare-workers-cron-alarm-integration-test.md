# Miniflare Workers Cron Alarm Integration Test

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Durable Objects can schedule `alarm()` callbacks at a precise future timestamp, making them the recommended mechanism for per-entity scheduled work on Cloudflare Workers. On example project / example.com, a `PostExpiryObject` alarm soft-deletes anonymous posts after a configurable TTL and a `RateLimiterObject` alarm resets per-user sliding windows. Testing that alarms fire, execute correct side effects, and re-schedule themselves requires time-travel capabilities unavailable in production or via real cron triggers.

## Context

Miniflare (embedded in `@cloudflare/vitest-pool-workers`) exposes `runDurableObjectAlarm(stub)` from `cloudflare:test`, which immediately fires the next scheduled alarm on a Durable Object without advancing wall-clock time. This allows deterministic, synchronous alarm testing inside Vitest. When combined with `getMiniflareDurableObjectStorage`, tests can also assert on storage state before and after the alarm fires.

## Test Setup

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "POST_EXPIRY"
class_name = "PostExpiryObject"

[[durable_objects.bindings]]
name = "RATE_LIMITER"
class_name = "RateLimiterObject"

[[d1_databases]]
binding = "DB"
database_name = "example project-local"
database_id = "00000000-0000-0000-0000-000000000002"
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          compatibilityDate: "2024-09-23",
        },
      },
    },
  },
});
```

```typescript
// src/objects/post-expiry-object.ts
export class PostExpiryObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const { postId, ttlSeconds } = await request.json<{
      postId: string;
      ttlSeconds: number;
    }>();
    await this.state.storage.put("postId", postId);
    await this.state.storage.setAlarm(Date.now() + ttlSeconds * 1_000);
    return new Response("scheduled");
  }

  async alarm(): Promise<void> {
    const postId = await this.state.storage.get<string>("postId");
    if (!postId) return;

    await this.env.DB.prepare(
      "UPDATE posts SET deleted_at = datetime('now') WHERE id = ? AND deleted_at IS NULL"
    )
      .bind(postId)
      .run();

    await this.state.storage.delete("postId");
  }
}
```

## Test Cases

```typescript
// src/objects/post-expiry-object.test.ts
import {
  env,
  runDurableObjectAlarm,
  getMiniflareDurableObjectStorage,
  createExecutionContext,
} from "cloudflare:test";
import { describe, it, expect, beforeAll, afterEach } from "vitest";
import { SELF } from "cloudflare:test";

beforeAll(async () => {
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS posts (
      id TEXT PRIMARY KEY,
      body TEXT NOT NULL,
      author_hash TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      deleted_at TEXT
    );
  `);
});

afterEach(async () => {
  await env.DB.exec("DELETE FROM posts");
});

describe("PostExpiryObject alarm", () => {
  it("soft-deletes the post when the alarm fires", async () => {
    // Insert a live post
    await env.DB.prepare(
      "INSERT INTO posts (id, body, author_hash) VALUES (?, ?, ?)"
    )
      .bind("post-ttl-1", "Expiring post", "aabbccdd")
      .run();

    // Schedule the alarm via the Durable Object
    const id = env.POST_EXPIRY.idFromName("post-ttl-1");
    const stub = env.POST_EXPIRY.get(id);
    await stub.fetch("http://internal/schedule", {
      method: "POST",
      body: JSON.stringify({ postId: "post-ttl-1", ttlSeconds: 3600 }),
    });

    // Verify alarm is stored
    const storage = await getMiniflareDurableObjectStorage(id);
    const scheduled = await storage.getAlarm();
    expect(scheduled).not.toBeNull();
    expect(scheduled).toBeGreaterThan(Date.now());

    // Fire the alarm immediately
    await runDurableObjectAlarm(stub);

    // Post must now be soft-deleted
    const row = await env.DB.prepare(
      "SELECT deleted_at FROM posts WHERE id = 'post-ttl-1'"
    ).first<{ deleted_at: string | null }>();
    expect(row?.deleted_at).not.toBeNull();
  });

  it("clears the stored postId from DO storage after firing", async () => {
    await env.DB.prepare(
      "INSERT INTO posts (id, body, author_hash) VALUES (?, ?, ?)"
    )
      .bind("post-ttl-2", "Another post", "11223344")
      .run();

    const id = env.POST_EXPIRY.idFromName("post-ttl-2");
    const stub = env.POST_EXPIRY.get(id);
    await stub.fetch("http://internal/schedule", {
      method: "POST",
      body: JSON.stringify({ postId: "post-ttl-2", ttlSeconds: 60 }),
    });

    await runDurableObjectAlarm(stub);

    const storage = await getMiniflareDurableObjectStorage(id);
    const postId = await storage.get("postId");
    expect(postId).toBeUndefined();
  });

  it("is idempotent — alarm on already-deleted post does not error", async () => {
    await env.DB.prepare(
      `INSERT INTO posts (id, body, author_hash, deleted_at)
       VALUES (?, ?, ?, datetime('now'))`
    )
      .bind("post-ttl-3", "Already deleted", "cafebabe")
      .run();

    const id = env.POST_EXPIRY.idFromName("post-ttl-3");
    const stub = env.POST_EXPIRY.get(id);
    await stub.fetch("http://internal/schedule", {
      method: "POST",
      body: JSON.stringify({ postId: "post-ttl-3", ttlSeconds: 1 }),
    });

    // Should resolve without throwing
    await expect(runDurableObjectAlarm(stub)).resolves.toBeUndefined();
  });

  it("does not fire when no alarm is scheduled", async () => {
    const id = env.POST_EXPIRY.idFromName("no-alarm");
    const stub = env.POST_EXPIRY.get(id);

    // runDurableObjectAlarm returns false when no alarm is pending
    const fired = await runDurableObjectAlarm(stub);
    expect(fired).toBe(false);
  });
});

describe("RateLimiterObject alarm — window reset", () => {
  it("resets the hit count when the sliding window alarm fires", async () => {
    const id = env.RATE_LIMITER.idFromName("user-anon-001");
    const stub = env.RATE_LIMITER.get(id);

    // Simulate 5 requests to fill the window
    for (let i = 0; i < 5; i++) {
      await stub.fetch("http://internal/hit");
    }

    const storage = await getMiniflareDurableObjectStorage(id);
    const before = await storage.get<number>("hits");
    expect(before).toBe(5);

    await runDurableObjectAlarm(stub);

    const after = await storage.get<number>("hits");
    expect(after ?? 0).toBe(0);
  });
});
```

## Assertions

Use `getMiniflareDurableObjectStorage` to assert on internal DO state without coupling tests to the public fetch interface:

```typescript
it("alarm re-schedules itself for recurring expiry check", async () => {
  const id = env.POST_EXPIRY.idFromName("recurring-post");
  const stub = env.POST_EXPIRY.get(id);

  await stub.fetch("http://internal/schedule", {
    method: "POST",
    body: JSON.stringify({ postId: "recurring-post", ttlSeconds: 86400, recurring: true }),
  });

  await runDurableObjectAlarm(stub);

  const storage = await getMiniflareDurableObjectStorage(id);
  const nextAlarm = await storage.getAlarm();
  // A recurring DO should have re-set its alarm after firing
  expect(nextAlarm).not.toBeNull();
  expect(nextAlarm).toBeGreaterThan(Date.now());
});
```

## CI Integration

```yaml
# .github/workflows/test.yml
name: Durable Object Alarm Tests
on: [push, pull_request]

jobs:
  do-alarms:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Run DO alarm integration tests
        run: pnpm vitest run src/objects/ --reporter=verbose
      - name: Upload coverage
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-do
          path: coverage/
```

## Anti-patterns

- Using `vi.useFakeTimers()` to advance time and expect `alarm()` to fire automatically — the workerd runtime manages its own alarm clock, not the JavaScript timer queue.
- Calling `alarm()` directly on the class instance instead of via `runDurableObjectAlarm(stub)` — skips the DO storage lifecycle and `blockConcurrencyWhile` semantics.
- Asserting only via the DO's `fetch` handler after the alarm — test D1 and storage state directly for precision.
- Forgetting `afterEach` cleanup of D1 rows — alarm tests that share post IDs interfere with each other.
- Checking `storage.getAlarm()` before awaiting `stub.fetch(...)` to schedule it — the alarm is not set until the fetch completes.

## Gotchas

- `runDurableObjectAlarm` returns `false` when no alarm is pending rather than throwing — check the return value in tests that expect an alarm to be set.
- Miniflare's DO storage is in-memory per test run; alarms do not persist across Vitest process restarts.
- `setAlarm` accepts an absolute timestamp in milliseconds; passing a relative duration without `Date.now()` is a common off-by-one error.
- The `alarm()` method runs inside `blockConcurrencyWhile` in production; Miniflare enforces the same single-threaded DO semantics.
- DO alarms in production have a minimum delay of 0 ms but maximum scheduling precision of ~1 s; Miniflare fires them immediately when `runDurableObjectAlarm` is called, which is more deterministic than production.

## Verification

```bash
pnpm vitest run src/objects/post-expiry-object.test.ts --reporter=verbose
# Expect: 5 tests pass, all alarm side-effects verified via D1 and storage queries

# Verify idempotency:
pnpm vitest run --reporter=verbose -t "idempotent"
```

## Related

- [durable-objects-alarm-testing-miniflare.md](durable-objects-alarm-testing-miniflare.md)
- [durable-objects-miniflare-fake-timers.md](durable-objects-miniflare-fake-timers.md)
- [workers-cron-trigger-integration-testing.md](workers-cron-trigger-integration-testing.md)
- [vitest-workers-scheduled-cron-trigger-testing.md](vitest-workers-scheduled-cron-trigger-testing.md)

## Sources

- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://miniflare.dev/testing/durable-objects
- https://developers.cloudflare.com/durable-objects/best-practices/alarms/
