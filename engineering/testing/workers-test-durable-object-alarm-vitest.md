# Testing Durable Object Alarms with Vitest

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Durable Object schedules work via `this.storage.setAlarm()` and you need to verify that the `alarm()` handler runs correctly, writes expected rows to D1, reschedules itself, and cleans up state on cancellation — all without waiting for real wall-clock time to elapse.

---

## Context
Miniflare v3 (used internally by `@cloudflare/vitest-pool-workers`) provides `runWithMiniflareDurableObjectStub`, which returns a handle to a DO instance running inside the test process. The companion `getMiniflareDurableObjectState` utility exposes the DO's `DurableObjectStorage` so you can read internal state and manually trigger the `alarm()` method by calling `state.storage.runAlarm()` — this bypasses the scheduler entirely and fires the handler synchronously within your test's async context.

---

## Setup / Config

```toml
# wrangler.toml
name = "alarm-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[durable_objects.bindings]]
name = "SCHEDULER"
class_name = "SchedulerDO"

[[d1_databases]]
binding = "DB"
database_name = "alarm-db"
database_id = "local-alarm-db-id"

[durable_objects]
bindings = [{name = "SCHEDULER", class_name = "SchedulerDO"}]
```

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS job_log (
  id         TEXT PRIMARY KEY,
  job_type   TEXT NOT NULL,
  ran_at     TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'success'
);
```

## Implementation

```typescript
// src/scheduler-do.ts
export interface Env {
  DB: D1Database;
  SCHEDULER: DurableObjectNamespace;
}

export class SchedulerDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/schedule") {
      const { jobType, delayMs } = await request.json<{
        jobType: string;
        delayMs: number;
      }>();

      // Persist job type so alarm() knows what to do
      await this.state.storage.put("pendingJobType", jobType);

      const fireAt = Date.now() + delayMs;
      await this.state.storage.setAlarm(fireAt);

      return Response.json({ scheduled: true, fireAt });
    }

    if (request.method === "DELETE" && url.pathname === "/cancel") {
      await this.state.storage.deleteAlarm();
      await this.state.storage.delete("pendingJobType");
      return Response.json({ cancelled: true });
    }

    return new Response("Not found", { status: 404 });
  }

  async alarm(): Promise<void> {
    const jobType = await this.state.storage.get<string>("pendingJobType");
    if (!jobType) return;

    // Write a record to D1
    await this.env.DB
      .prepare(
        "INSERT INTO job_log (id, job_type, ran_at, status) VALUES (?, ?, datetime('now'), 'success')"
      )
      .bind(crypto.randomUUID(), jobType)
      .run();

    // Clear the job and reschedule for 1 hour later
    await this.state.storage.delete("pendingJobType");
    await this.state.storage.put("pendingJobType", `${jobType}-repeat`);
    await this.state.storage.setAlarm(Date.now() + 60 * 60 * 1_000);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const id = env.SCHEDULER.idFromName("global");
    const stub = env.SCHEDULER.get(id);
    return stub.fetch(request);
  },
};
```

## Testing Alarms

```typescript
// src/scheduler-do.test.ts
import {
  env,
  runWithMiniflareDurableObjectStub,
  getMiniflareDurableObjectState,
} from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import type { Env } from "./scheduler-do";

const typedEnv = env as unknown as Env;

async function getDoState(name: string) {
  const id = typedEnv.SCHEDULER.idFromName(name);
  return getMiniflareDurableObjectState(id);
}

async function cleanDb() {
  await typedEnv.DB.exec("DELETE FROM job_log");
}

describe("SchedulerDO alarm", () => {
  beforeEach(async () => {
    await cleanDb();
  });

  it("fires alarm() and writes a D1 row", async () => {
    await runWithMiniflareDurableObjectStub(
      typedEnv.SCHEDULER,
      "alarm-test",
      async (stub) => {
        // Schedule a job via the fetch handler
        const scheduleRes = await stub.fetch(
          new Request("https://do.internal/schedule", {
            method: "POST",
            body: JSON.stringify({ jobType: "send-email", delayMs: 5000 }),
            headers: { "Content-Type": "application/json" },
          })
        );
        expect(scheduleRes.status).toBe(200);

        // Manually trigger the alarm — no real time passes
        const doState = await getDoState("alarm-test");
        await doState.storage.runAlarm();

        // Assert D1 was written
        const row = await typedEnv.DB
          .prepare("SELECT * FROM job_log WHERE job_type = ?")
          .bind("send-email")
          .first<{ job_type: string; status: string }>();

        expect(row).not.toBeNull();
        expect(row!.job_type).toBe("send-email");
        expect(row!.status).toBe("success");
      }
    );
  });

  it("reschedules the alarm after firing", async () => {
    await runWithMiniflareDurableObjectStub(
      typedEnv.SCHEDULER,
      "reschedule-test",
      async (stub) => {
        await stub.fetch(
          new Request("https://do.internal/schedule", {
            method: "POST",
            body: JSON.stringify({ jobType: "sync-data", delayMs: 1000 }),
            headers: { "Content-Type": "application/json" },
          })
        );

        const doState = await getDoState("reschedule-test");
        await doState.storage.runAlarm();

        // alarm() should have set a new alarm and updated pendingJobType
        const nextJob = await doState.storage.get<string>("pendingJobType");
        expect(nextJob).toBe("sync-data-repeat");

        const nextAlarm = await doState.storage.getAlarm();
        expect(nextAlarm).not.toBeNull();
        // Should be ~1 hour in the future (allow +/-5 seconds for test execution)
        const diffMs = nextAlarm! - Date.now();
        expect(diffMs).toBeGreaterThan(60 * 60 * 1_000 - 5_000);
        expect(diffMs).toBeLessThan(60 * 60 * 1_000 + 5_000);
      }
    );
  });

  it("cancellation removes alarm and clears state", async () => {
    await runWithMiniflareDurableObjectStub(
      typedEnv.SCHEDULER,
      "cancel-test",
      async (stub) => {
        // Schedule first
        await stub.fetch(
          new Request("https://do.internal/schedule", {
            method: "POST",
            body: JSON.stringify({ jobType: "cleanup", delayMs: 10000 }),
            headers: { "Content-Type": "application/json" },
          })
        );

        const doState = await getDoState("cancel-test");
        // Confirm alarm is set
        expect(await doState.storage.getAlarm()).not.toBeNull();

        // Cancel via the fetch handler
        const cancelRes = await stub.fetch(
          new Request("https://do.internal/cancel", { method: "DELETE" })
        );
        expect(cancelRes.status).toBe(200);

        // Alarm should be cleared
        expect(await doState.storage.getAlarm()).toBeNull();
        // State should be cleared
        expect(await doState.storage.get("pendingJobType")).toBeUndefined();

        // No D1 rows should have been written (alarm never fired)
        const rows = await typedEnv.DB.prepare("SELECT id FROM job_log").all();
        expect(rows.results).toHaveLength(0);
      }
    );
  });

  it("does not write to D1 if pendingJobType is missing", async () => {
    await runWithMiniflareDurableObjectStub(
      typedEnv.SCHEDULER,
      "empty-alarm-test",
      async () => {
        // Fire alarm without scheduling anything first
        const doState = await getDoState("empty-alarm-test");
        await doState.storage.runAlarm();

        const rows = await typedEnv.DB.prepare("SELECT id FROM job_log").all();
        expect(rows.results).toHaveLength(0);
      }
    );
  });
});
```

---

## Anti-patterns
- **Sleeping to let alarms fire** — `setTimeout` or `waitFor` loops that wait for real clock advancement are flaky and slow; use `doState.storage.runAlarm()` to trigger the handler instantly.
- **Testing alarm logic through the Worker's `fetch` handler only** — the alarm path is separate from fetch; test `alarm()` directly via `runAlarm()` to get full coverage.
- **Not asserting the reschedule** — if your alarm is supposed to self-reschedule, assert `getAlarm()` after `runAlarm()` to confirm the new timestamp was set.
- **Sharing DO names across tests** — each test should use a unique `idFromName()` argument to avoid state leaking between `runWithMiniflareDurableObjectStub` calls.

---

## Gotchas
- `runWithMiniflareDurableObjectStub` creates an isolated DO instance that exists only within its callback; state written inside is discarded afterwards.
- `doState.storage.runAlarm()` is a Miniflare test-only API — it does not exist in production and will throw if called outside the test pool.
- Alarms in production require a real Durable Object with a paid Workers plan; local testing with Miniflare works on free tier.
- `getMiniflareDurableObjectState` must be called with the same `DurableObjectId` used by the stub — derive it from `idFromName("same-name")`.
- If `alarm()` throws, `runAlarm()` will reject; wrap in `try/catch` in the test if you want to assert error recovery behavior.

---

## Verification

```bash
# Apply D1 schema locally
npx wrangler d1 execute alarm-db --local --file=schema.sql

# Run alarm tests
npx vitest run src/scheduler-do.test.ts

# Verbose output to see each alarm test case
npx vitest run --reporter=verbose src/scheduler-do.test.ts
```

---

## Related
- `workers-integration-test-d1-seed-fixtures.md`
- `workers-test-queue-consumer-mock-batch.md`

---

## Sources
- Cloudflare Durable Object alarms — https://developers.cloudflare.com/durable-objects/api/alarms/
- Miniflare Durable Object testing — https://miniflare.dev/testing/durable-objects
- Vitest pool workers — https://developers.cloudflare.com/workers/testing/vitest-integration/
