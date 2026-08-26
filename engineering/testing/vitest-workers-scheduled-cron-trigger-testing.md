# Vitest Workers Scheduled Cron Trigger Testing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cloudflare Workers scheduled cron triggers fire outside the normal HTTP request cycle, making them impossible to test via standard fetch mocking. On example project / example.com, cron triggers handle daily digest emails, anonymous session pruning, and trending-post score decay — all business-critical but invisible to integration tests that only exercise the `fetch` handler.

## Context

The `@cloudflare/vitest-pool-workers` pool runs Workers in a real workerd runtime, giving access to the `scheduled` export through `SELF.scheduled(...)`. Vitest fake timers interact poorly with the Workers event loop, so cron testing relies on direct invocation rather than wall-clock advancement. The `ExecutionContext` mock provided by the pool captures `waitUntil` promises automatically.

## Test Setup

Install the pool and configure `wrangler.toml` with a cron schedule so the runtime registers the trigger:

```toml
# wrangler.toml
[triggers]
crons = ["0 3 * * *", "*/5 * * * *"]
```

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
          compatibilityDate: "2024-09-23",
          compatibilityFlags: ["nodejs_compat"],
        },
      },
    },
  },
});
```

```typescript
// src/worker.ts  (handler under test)
export interface Env {
  DB: D1Database;
  KV: KVNamespace;
}

export default {
  async scheduled(
    controller: ScheduledController,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    if (controller.cron === "0 3 * * *") {
      ctx.waitUntil(pruneExpiredSessions(env.DB));
    }
    if (controller.cron === "*/5 * * * *") {
      ctx.waitUntil(decayTrendingScores(env.DB, env.KV));
    }
  },
};
```

## Test Cases

Use `SELF.scheduled` from `cloudflare:test` to invoke the handler with an explicit cron string:

```typescript
// src/worker.test.ts
import {
  env,
  SELF,
  createExecutionContext,
  waitOnExecutionContext,
} from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";

describe("scheduled cron triggers", () => {
  beforeEach(async () => {
    // Seed deterministic data via D1
    await env.DB.exec(`
      INSERT INTO sessions (id, user_id, expires_at)
      VALUES
        ('sess-1', 'anon-001', datetime('now', '-1 day')),
        ('sess-2', 'anon-002', datetime('now', '+1 day'));
    `);
    await env.DB.exec(`
      INSERT INTO posts (id, score, updated_at)
      VALUES
        ('post-1', 9000, datetime('now', '-2 days')),
        ('post-2', 100,  datetime('now'));
    `);
  });

  it("prunes expired sessions on the 0 3 * * * cron", async () => {
    const ctx = createExecutionContext();
    await SELF.scheduled({ scheduledTime: Date.now(), cron: "0 3 * * *" }, ctx);
    await waitOnExecutionContext(ctx);

    const { results } = await env.DB.prepare(
      "SELECT id FROM sessions"
    ).all<{ id: string }>();

    expect(results.map((r) => r.id)).toEqual(["sess-2"]);
  });

  it("decays trending scores on the */5 * * * * cron", async () => {
    const ctx = createExecutionContext();
    await SELF.scheduled(
      { scheduledTime: Date.now(), cron: "*/5 * * * *" },
      ctx
    );
    await waitOnExecutionContext(ctx);

    const row = await env.DB.prepare(
      "SELECT score FROM posts WHERE id = 'post-1'"
    ).first<{ score: number }>();

    expect(row!.score).toBeLessThan(9000);
  });

  it("is a no-op for an unrecognised cron expression", async () => {
    const ctx = createExecutionContext();
    // Should not throw even for an unknown cron string
    await expect(
      SELF.scheduled({ scheduledTime: Date.now(), cron: "0 0 1 1 *" }, ctx)
    ).resolves.toBeUndefined();
  });
});
```

## Assertions

Assert side-effects through D1 queries and KV reads rather than inspecting return values — scheduled handlers return `void`:

```typescript
it("writes decay timestamp to KV after score decay run", async () => {
  const ctx = createExecutionContext();
  await SELF.scheduled({ scheduledTime: Date.now(), cron: "*/5 * * * *" }, ctx);
  await waitOnExecutionContext(ctx);

  const lastRun = await env.KV.get("cron:score-decay:last-run");
  expect(lastRun).not.toBeNull();

  const ts = Number(lastRun);
  expect(ts).toBeGreaterThan(Date.now() - 5_000);
  expect(ts).toBeLessThanOrEqual(Date.now());
});

it("does not double-prune within the same execution", async () => {
  const ctx = createExecutionContext();
  await SELF.scheduled({ scheduledTime: Date.now(), cron: "0 3 * * *" }, ctx);
  await waitOnExecutionContext(ctx);

  // Expired session already gone; second call must not error
  const ctx2 = createExecutionContext();
  await expect(
    SELF.scheduled({ scheduledTime: Date.now(), cron: "0 3 * * *" }, ctx2)
  ).resolves.toBeUndefined();
  await waitOnExecutionContext(ctx2);
});
```

## CI Integration

```yaml
# .github/workflows/test.yml
name: Worker Tests
on: [push, pull_request]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Run vitest (workers pool)
        run: pnpm vitest run --reporter=verbose
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

For scheduled-only test suites add a dedicated project:

```typescript
// vitest.config.ts — separate project for cron tests
export default defineWorkersConfig({
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: "cron",
          include: ["**/*.cron.test.ts"],
        },
      },
    ],
  },
});
```

## Anti-patterns

- Using `vi.useFakeTimers()` inside the Workers pool — the workerd runtime has its own clock; fake timers only affect the test frame.
- Calling the exported `scheduled` function directly instead of `SELF.scheduled` — skips binding injection and `waitUntil` capture.
- Asserting on console output to verify side effects — always query D1 / KV for state changes.
- Hard-coding `Date.now()` comparisons without tolerance — CI runners can be slow; use `toBeGreaterThan(Date.now() - 5_000)`.
- Forgetting to call `waitOnExecutionContext` — `waitUntil` promises run asynchronously and their results are invisible if not awaited.

## Gotchas

- `SELF.scheduled` is only available when the worker has a `scheduled` export; the call throws otherwise.
- Multiple `waitUntil` calls inside a single handler are all awaited by `waitOnExecutionContext` — order of resolution is non-deterministic.
- `controller.scheduledTime` is the UNIX timestamp in milliseconds; the cron schedule string is in `controller.cron`.
- D1 `exec` in `beforeEach` does not wrap in a transaction; use `db.batch` or explicit `BEGIN`/`COMMIT` for atomicity in test setup.
- The Workers pool reuses a single D1 instance across tests in the same file unless you explicitly reset tables in `afterEach`.

## Verification

```bash
pnpm vitest run src/worker.test.ts --reporter=verbose
# Expect: 4 tests pass, 0 skipped
```

Add `--coverage` to confirm the `scheduled` branch is fully covered:

```bash
pnpm vitest run --coverage src/worker.test.ts
```

## Related

- [workers-cron-trigger-integration-testing.md](workers-cron-trigger-integration-testing.md)
- [durable-objects-alarm-testing-miniflare.md](durable-objects-alarm-testing-miniflare.md)
- [vitest-cloudflare-pool-workers.md](vitest-cloudflare-pool-workers.md)
- [d1-test-fixtures-wrangler-seed.md](d1-test-fixtures-wrangler-seed.md)

## Sources

- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
- https://miniflare.dev/testing/vitest
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
