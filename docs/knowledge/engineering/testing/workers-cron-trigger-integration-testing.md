# Workers Cron Trigger Integration Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Cloudflare Workers with `scheduled` event handlers run on cron triggers that cannot be invoked through a standard `fetch()` call. Without dedicated test patterns, the `scheduled` handler is never exercised in CI, leaving background jobs — database vacuums, digest emails, KV cache refreshes — untested until they fail silently in production. Vitest with `@cloudflare/vitest-pool-workers` provides `runScheduled` to invoke the handler directly against real local bindings with a synthetic event.

## Context

A Worker with a `scheduled` export receives a `ScheduledEvent` containing `cron` (the matching expression string) and `scheduledTime` (epoch milliseconds). The handler cannot be reached by HTTP, but Wrangler exposes `/__scheduled?cron=*+*+*+*+*` on its local dev server for manual smoke testing. In Vitest pool-workers tests, `runScheduled` from `cloudflare:test` calls the handler in the real Workers runtime with D1, KV, Queues, and R2 bindings available. Tests assert on binding state — rows deleted from D1, values written to KV, messages enqueued — rather than on return values, because `scheduled` handlers return `void`.

## Scheduled Worker Under Test

```typescript
// src/index.ts
export interface Env {
  DB:      D1Database;
  LOG_KV:  KVNamespace;
  NOTIFY:  Queue<{ type: string; count: number }>;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Delete expired sessions and count removed rows
    const row = await env.DB
      .prepare(`DELETE FROM sessions WHERE expires_at < ?1 RETURNING COUNT(*) AS count`)
      .bind(event.scheduledTime)
      .first<{ count: number }>();

    const deletedCount = row?.count ?? 0;

    ctx.waitUntil(
      env.LOG_KV.put(
        "vacuum:last_run",
        JSON.stringify({ time: event.scheduledTime, deletedCount }),
        { expirationTtl: 86_400 }
      )
    );

    if (deletedCount > 0) {
      ctx.waitUntil(env.NOTIFY.send({ type: "vacuum_complete", count: deletedCount }));
    }
  },
};
```

## Integration Tests for the Scheduled Handler

```typescript
// test/scheduled.spec.ts
import {
  env,
  createExecutionContext,
  waitOnExecutionContext,
  runScheduled,
} from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import worker from "../src/index";

const NOW = new Date("2026-08-23T03:00:00Z").getTime();
const EVENT = { scheduledTime: NOW, cron: "0 3 * * *" };

beforeEach(async () => {
  await env.DB.exec("DELETE FROM sessions");
  await env.LOG_KV.delete("vacuum:last_run");
});

describe("Cron vacuum job — scheduled handler", () => {
  it("deletes only expired sessions and records the count in KV", async () => {
    await env.DB.prepare(`
      INSERT INTO sessions (id, expires_at) VALUES
        ('sess-old-1',  ?1),
        ('sess-old-2',  ?2),
        ('sess-active', ?3)
    `).bind(NOW - 60_000, NOW - 1_000, NOW + 9_000_000).run();

    const ctx = createExecutionContext();
    await runScheduled(worker, EVENT, env, ctx);
    await waitOnExecutionContext(ctx);

    const remaining = await env.DB
      .prepare("SELECT id FROM sessions")
      .all<{ id: string }>();
    expect(remaining.results.map((r) => r.id)).toEqual(["sess-active"]);

    const log = await env.LOG_KV.get<{ deletedCount: number; time: number }>(
      "vacuum:last_run",
      "json"
    );
    expect(log).toMatchObject({ deletedCount: 2, time: NOW });
  });

  it("does not enqueue a notification when no sessions are deleted", async () => {
    await env.DB.prepare(`INSERT INTO sessions (id, expires_at) VALUES ('s1', ?1)`)
      .bind(NOW + 9_000_000)
      .run();

    const ctx = createExecutionContext();
    await runScheduled(worker, EVENT, env, ctx);
    await waitOnExecutionContext(ctx);

    // Miniflare's Queue binding exposes a batch inspection helper
    const batch = await env.NOTIFY.getMessage();
    expect(batch.messages).toHaveLength(0);
  });

  it("records the exact scheduledTime from the event in the KV log", async () => {
    const futureTime = new Date("2026-09-01T03:00:00Z").getTime();
    const ctx = createExecutionContext();
    await runScheduled(worker, { scheduledTime: futureTime, cron: "0 3 * * *" }, env, ctx);
    await waitOnExecutionContext(ctx);

    const log = await env.LOG_KV.get<{ time: number }>("vacuum:last_run", "json");
    expect(log?.time).toBe(futureTime);
  });

  it("enqueues one notification per vacuum run that removes sessions", async () => {
    await env.DB.prepare(`
      INSERT INTO sessions (id, expires_at) VALUES ('old-1', ?1), ('old-2', ?2)
    `).bind(NOW - 2_000, NOW - 1_000).run();

    const ctx = createExecutionContext();
    await runScheduled(worker, EVENT, env, ctx);
    await waitOnExecutionContext(ctx);

    const batch = await env.NOTIFY.getMessage();
    expect(batch.messages).toHaveLength(1);
    expect(batch.messages[0].body).toMatchObject({ type: "vacuum_complete", count: 2 });
  });
});
```

## Wrangler Configuration for Cron Triggers

```toml
# wrangler.toml
name               = "session-vacuum"
main               = "src/index.ts"
compatibility_date = "2026-07-01"

[triggers]
crons = ["0 3 * * *"]

[[d1_databases]]
binding       = "DB"
database_name = "sessions-db"
database_id   = "local"

[[queues.producers]]
binding = "NOTIFY"
queue   = "vacuum-notify"

[[kv_namespaces]]
binding = "LOG_KV"
id      = "local"
```

## Manual Trigger via Wrangler Dev

```bash
# Start local dev server and manually fire the scheduled handler
npx wrangler dev --local src/index.ts &
sleep 2

# Trigger via the /__scheduled HTTP endpoint (local mode only)
curl -s "http://localhost:8787/__scheduled?cron=0+3+*+*+*"
# {"result":"ok"}

# Inspect KV side-effect
npx wrangler kv:key get --binding=LOG_KV vacuum:last_run --local
```

## Anti-patterns

- Testing the `scheduled` handler by calling `worker.fetch(new Request("/__scheduled?..."))` — this path only works in `wrangler dev` local mode; it is not handled by the Worker itself and will return 404 in production
- Using `Date.now()` inside the handler instead of `event.scheduledTime` — makes the handler non-deterministic and prevents asserting on the exact time written to KV
- Asserting on side effects after a `setTimeout` delay instead of `waitOnExecutionContext` — misses `ctx.waitUntil()` work that may not have settled by the time the assertion runs

## Gotchas

- `runScheduled` is exported from `cloudflare:test` only when using `@cloudflare/vitest-pool-workers`; it does not exist in standard Vitest, Jest, or `@miniflare/core` environments — importing it from the wrong path produces a `Cannot find module` error at runtime, not at TypeScript compile time
- D1 `DELETE … RETURNING` requires SQLite 3.35+; the bundled version in Wrangler local mode may differ from the Workers production runtime — verify with `wrangler d1 execute --local --command "SELECT sqlite_version()"`
- Miniflare's Queue `getMessage()` is destructive: it dequeues messages and they are gone; call it exactly once per test, or accumulate messages in a shared array via a test-scoped consumer Worker binding

## Verification

```bash
npx vitest run test/scheduled.spec.ts --reporter=verbose
# Expected: 4 passing tests, side effects verified via D1/KV/Queue assertions

# Validate cron expression syntax at deploy time (no live deploy needed)
npx wrangler deploy --dry-run --outdir dist
# An invalid cron expression in [triggers].crons fails here with a clear error message
```

## Related

- `testing/durable-objects-miniflare-fake-timers.md`
- `testing/kv-testing-miniflare.md`
- `testing/miniflare-d1-integration-testing.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/queues/reference/local-development/
