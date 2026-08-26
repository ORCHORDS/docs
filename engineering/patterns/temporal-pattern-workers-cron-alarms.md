# Temporal Pattern: Cron Triggers + Durable Object Alarms

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need two distinct scheduling granularities in the same system: coarse, fleet-wide
coordination (e.g., hourly data sync for all tenants) handled by a cron trigger, and
fine-grained, per-entity timers (e.g., a trial expiry exactly 14 days after signup,
retry in 37 seconds) that survive Worker restarts and can be cancelled or rescheduled
at runtime. A single cron trigger cannot express per-entity delays; plain `setTimeout`
in Workers does not survive across requests or invocations.

## Context

Cloudflare Workers Scheduled Events (`cron triggers`) fire at fixed wall-clock
intervals across the entire Worker fleet. They are appropriate for global housekeeping
tasks where every invocation does the same type of work. Durable Object Alarms, by
contrast, are per-DO-instance, persist through hibernation, and fire once at an
absolute timestamp that the DO itself sets. Combining both gives you a two-level
temporal architecture: cron handles the "enumerate and dispatch" phase; DO alarms
handle the "fire at the right moment for this specific entity" phase.

This pattern is the Cloudflare-native equivalent of a job scheduler with delayed
tasks: no external cron database, no polling loop, no missed fires after cold starts.

---

## Architecture

```
Cron Trigger (hourly)
  └─ Scheduled Worker
       └─ queries D1 for entities due for scheduling
            └─ for each entity → stubs DO by entity ID
                 └─ DO.schedule(targetTimestamp)
                      └─ DO.alarm() fires at targetTimestamp
                           └─ executes per-entity work (email, charge, sync, etc.)
                                └─ optionally re-arms itself for next occurrence
```

## Durable Object with Alarm Support

```typescript
// src/entity-scheduler.do.ts
import { DurableObject } from "cloudflare:workers";
import { Env } from "./types";

interface ScheduledTask {
  entityId: string;
  taskType: "trial_expiry" | "renewal_charge" | "report_generation";
  scheduledFor: number;   // Unix ms
  payload: Record<string, unknown>;
}

export class EntityScheduler extends DurableObject<Env> {
  private task: ScheduledTask | null = null;

  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
    // Restore task from storage on cold start
    this.ctx.blockConcurrencyWhile(async () => {
      this.task = (await this.ctx.storage.get<ScheduledTask>("task")) ?? null;
    });
  }

  // Called by the cron Worker or by the application to (re)schedule a task
  async schedule(task: ScheduledTask): Promise<void> {
    this.task = task;
    await this.ctx.storage.put("task", task);

    const existing = await this.ctx.storage.getAlarm();
    // Only update the alarm if it would change by more than 1 second to avoid
    // unnecessary writes on idempotent re-scheduling calls
    if (!existing || Math.abs(existing - task.scheduledFor) > 1000) {
      await this.ctx.storage.setAlarm(task.scheduledFor);
    }
  }

  // Cancel a pending alarm and clear stored task
  async cancel(): Promise<void> {
    await this.ctx.storage.deleteAlarm();
    await this.ctx.storage.delete("task");
    this.task = null;
  }

  // Durable Object alarm handler — runs at the scheduled time
  async alarm(): Promise<void> {
    if (!this.task) return;

    const task = this.task;
    console.log(`[EntityScheduler] Firing ${task.taskType} for entity ${task.entityId}`);

    try {
      await this.executeTask(task);
      // Clear task after successful execution
      await this.ctx.storage.delete("task");
      this.task = null;
    } catch (err) {
      console.error(`[EntityScheduler] Task failed, will retry in 60s:`, err);
      // Re-arm alarm for retry; Workers runtime will re-invoke alarm()
      await this.ctx.storage.setAlarm(Date.now() + 60_000);
    }
  }

  private async executeTask(task: ScheduledTask): Promise<void> {
    switch (task.taskType) {
      case "trial_expiry":
        await this.handleTrialExpiry(task);
        break;
      case "renewal_charge":
        await this.handleRenewalCharge(task);
        break;
      case "report_generation":
        await this.handleReportGeneration(task);
        break;
      default:
        throw new Error(`Unknown task type: ${(task as any).taskType}`);
    }
  }

  private async handleTrialExpiry(task: ScheduledTask): Promise<void> {
    const tenantId = task.payload.tenantId as string;
    await this.env.DB.prepare(
      "UPDATE tenants SET plan = 'free', trial_expired_at = ? WHERE id = ?"
    ).bind(Date.now(), tenantId).run();

    // Publish event for notification Worker
    await this.env.EVENTS_QUEUE.send({
      type: "tenant.trial_expired",
      tenantId,
      at: Date.now(),
    });
  }

  private async handleRenewalCharge(task: ScheduledTask): Promise<void> {
    // Delegate to billing service binding
    const res = await this.env.BILLING_WORKER.fetch(
      new Request("https://internal/charge", {
        method: "POST",
        body: JSON.stringify(task.payload),
        headers: { "Content-Type": "application/json" },
      })
    );
    if (!res.ok) throw new Error(`Billing charge failed: ${res.status}`);
  }

  private async handleReportGeneration(task: ScheduledTask): Promise<void> {
    // placeholder: generate report and store in R2
    console.log(`Generating report for entity ${task.entityId}`);
  }
}
```

## Cron Worker: Enumerate and Dispatch

```typescript
// src/cron-worker.ts
import { Env } from "./types";

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Find entities that need scheduling (new or rescheduled since last run)
    const due = await env.DB.prepare(`
      SELECT id, trial_ends_at, renewal_date, task_type
      FROM scheduling_queue
      WHERE dispatched_at IS NULL
        AND scheduled_for <= ?
    `).bind(Date.now() + 24 * 60 * 60 * 1000 /* 24h lookahead */).all<{
      id: string;
      trial_ends_at: number | null;
      renewal_date: number | null;
      task_type: string;
    }>();

    const dispatches = due.results.map(async (row) => {
      const scheduledFor = row.trial_ends_at ?? row.renewal_date ?? Date.now();
      const stub = env.ENTITY_SCHEDULER.get(
        env.ENTITY_SCHEDULER.idFromName(row.id)
      );

      await stub.schedule({
        entityId: row.id,
        taskType: row.task_type as any,
        scheduledFor,
        payload: { tenantId: row.id },
      });

      // Mark as dispatched so we don't re-dispatch on the next cron run
      await env.DB.prepare(
        "UPDATE scheduling_queue SET dispatched_at = ? WHERE id = ?"
      ).bind(Date.now(), row.id).run();
    });

    await Promise.allSettled(dispatches);
    console.log(`Dispatched ${due.results.length} scheduled tasks`);
  },
};
```

## Runtime Scheduling from Application Code

```typescript
// src/api-worker.ts — immediate scheduling from application events
import { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/trials" && request.method === "POST") {
      const { tenantId, trialDays = 14 } = await request.json<{
        tenantId: string;
        trialDays?: number;
      }>();

      // Create tenant in D1
      await env.DB.prepare(
        "INSERT INTO tenants (id, plan, trial_expires_at) VALUES (?, 'trial', ?)"
      ).bind(tenantId, Date.now() + trialDays * 86400_000).run();

      // Schedule trial expiry alarm immediately — no cron lag
      const stub = env.ENTITY_SCHEDULER.get(
        env.ENTITY_SCHEDULER.idFromName(`trial:${tenantId}`)
      );
      await stub.schedule({
        entityId: tenantId,
        taskType: "trial_expiry",
        scheduledFor: Date.now() + trialDays * 86400_000,
        payload: { tenantId },
      });

      return Response.json({ tenantId, trialDays }, { status: 201 });
    }

    if (url.pathname.startsWith("/api/trials/") && request.method === "DELETE") {
      const tenantId = url.pathname.split("/").pop()!;
      const stub = env.ENTITY_SCHEDULER.get(
        env.ENTITY_SCHEDULER.idFromName(`trial:${tenantId}`)
      );
      await stub.cancel();
      return new Response(null, { status: 204 });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## Anti-patterns

- **Using cron alone for per-entity timing**: a 1-minute cron polling D1 for due
  tasks creates O(tenants) DB reads per minute and still has up to 60-second jitter.
- **`setTimeout` for deferred work**: it does not persist; if the Worker goes idle
  before the timeout fires, the work is lost.
- **Setting alarms far in the future without a ledger**: if the DO is deleted or
  evicted, the alarm is gone. Keep a D1 record of all scheduled tasks so you can
  reconcile and re-arm from the cron job.
- **Re-scheduling on every cron run**: calling `schedule()` unconditionally causes
  unnecessary DO activations and storage writes. Gate on dispatched_at IS NULL.
- **Silently swallowing alarm errors**: failures in `alarm()` that don't re-arm
  lose the task permanently. Always retry or write to a dead-letter queue.

## Gotchas

- `setAlarm()` accepts an absolute Unix millisecond timestamp, not a delay. Compute
  `Date.now() + delayMs` yourself.
- DO alarm fires are best-effort within a few seconds of the target time; they are
  not guaranteed to be exact. For SLA-critical tasks, verify the current time inside
  `alarm()` and skip if more than N seconds late.
- A DO with a pending alarm cannot be evicted. Cancelling unused alarms is important
  for both cost and DO instance hygiene.
- The alarm fires in the DO's single-threaded execution context. Long-running alarm
  handlers block other requests to the same DO. Offload heavy work via Queue message
  or service binding so the alarm handler is fast.
- `ctx.blockConcurrencyWhile` in the constructor is required to safely initialize
  state from storage before any request or alarm handler runs concurrently.

## Verification

```typescript
// integration test (Vitest + @cloudflare/vitest-pool-workers)
import { SELF } from "cloudflare:test";

it("schedules and fires trial expiry alarm", async () => {
  const res = await SELF.fetch("https://example.com/api/trials", {
    method: "POST",
    body: JSON.stringify({ tenantId: "t_test", trialDays: 0 }), // 0 days → fires immediately
    headers: { "Content-Type": "application/json" },
  });
  expect(res.status).toBe(201);

  // Advance the test clock past the alarm time and trigger alarm processing
  await scheduler.wait(100); // vitest-pool-workers utility
  // Assert side effect: tenant plan should be "free"
  const tenant = await env.DB.prepare("SELECT plan FROM tenants WHERE id = ?")
    .bind("t_test").first<{ plan: string }>();
  expect(tenant?.plan).toBe("free");
});
```

## Related

- `distributed-lock-durable-objects.md` — locking within DO for idempotent alarm execution
- `outbox-pattern-d1-reliable-publishing.md` — reliable event emission from alarm handlers
- `memento-pattern-durable-objects-state-snapshot.md` — snapshotting DO state before alarm
- `cron-scheduling.md` — basic cron trigger patterns

## Sources

- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/durable-objects/best-practices/
- https://developers.cloudflare.com/durable-objects/reference/in-memory-state/
