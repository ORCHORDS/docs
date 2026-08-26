# Workers Cron Trigger Does Not Block the Next Invocation — Parallel Runs Caused Data Corruption

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A billing cron job scheduled `*/5 * * * *` (every 5 minutes) started taking 7–9
minutes to run during high-traffic periods. Because Cloudflare fires cron triggers at
the scheduled wall-clock time regardless of whether a previous invocation is still
executing, two instances ran concurrently. Both instances read the same pending
invoices, both attempted to charge the same cards, and both marked the invoices as
paid. Customers were double-charged.

---

## Context

Cloudflare Workers cron triggers fire at the scheduled wall-clock time. There is no
built-in "skip if already running" or "serialise invocations" behaviour. If a Worker
invocation takes longer than the cron interval, the next invocation starts in a
separate isolate without any knowledge of the still-running previous one.

This is fundamentally different from cron daemons like Linux `cron` or GitHub Actions
`concurrency:` groups, which can be configured to skip or queue overlapping runs.

Workers have a **CPU time limit** (50 ms for the Free plan, up to 30 s on paid plans)
and a **wall-clock limit** (typically 30 s for free, up to 15 min for cron on Unbound
Workers). A slow downstream API call is billed to wall-clock time but not to CPU time,
so a job can appear within CPU limits while far exceeding the cron interval.

---

## The Execution Model

```
T=0:00  → Invocation A starts (invoice batch of 500)
T=0:05  → Invocation B starts (same invoice batch, A still running)
T=0:07  → Invocation A finishes (marks invoices paid)
T=0:08  → Invocation B finishes (marks same invoices paid again)
→ 500 customers double-charged
```

Neither invocation surfaces an error — from each isolate's perspective, it succeeded.

---

## Distributed Lock with a Durable Object

The most reliable way to prevent concurrent cron runs on Cloudflare Workers is a
Durable Object lock. DOs offer single-threaded, serialised execution by design.

```typescript
// src/cron-lock-do.ts
import { DurableObject } from "cloudflare:workers";

interface LockState {
  lockedAt: number;
  lockedBy: string;
}

const LOCK_TTL_MS = 10 * 60 * 1_000; // 10 minutes — must exceed max job duration

export class CronLockDO extends DurableObject {
  async tryAcquire(jobId: string): Promise<boolean> {
    const existing = await this.ctx.storage.get<LockState>("lock");

    if (existing) {
      const age = Date.now() - existing.lockedAt;
      if (age < LOCK_TTL_MS) {
        console.log(`Lock held by ${existing.lockedBy}, age=${age}ms — skipping.`);
        return false;
      }
      // Stale lock (previous run crashed without releasing) — steal it.
      console.warn(`Stealing stale lock from ${existing.lockedBy}, age=${age}ms`);
    }

    await this.ctx.storage.put<LockState>("lock", {
      lockedAt: Date.now(),
      lockedBy: jobId,
    });
    return true;
  }

  async release(jobId: string): Promise<void> {
    const existing = await this.ctx.storage.get<LockState>("lock");
    if (existing?.lockedBy === jobId) {
      await this.ctx.storage.delete("lock");
    }
    // If the lock belongs to a different jobId (e.g. stolen), leave it alone.
  }
}
```

---

## Cron Worker Using the Lock

```typescript
// src/index.ts
import { CronLockDO } from "./cron-lock-do";
export { CronLockDO };

export interface Env {
  CRON_LOCK: DurableObjectNamespace;
  DB: D1Database;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const jobId = `billing-${event.scheduledTime}`;
    const lockId = env.CRON_LOCK.idFromName("billing-job");
    const lock = env.CRON_LOCK.get(lockId);

    const acquired = await lock.tryAcquire(jobId);
    if (!acquired) {
      console.log(`[${jobId}] Previous invocation still running — skipping.`);
      return;
    }

    try {
      await runBillingJob(env.DB, jobId);
    } finally {
      // Always release, even if the job throws.
      await lock.release(jobId);
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Idempotent Job Design (Defence in Depth)

Even with a lock, implement idempotency so that a double-fire (e.g. lock failure due
to a D0 rollover or cold-start race) does not cause double-charges.

```typescript
// src/billing-job.ts
export async function runBillingJob(db: D1Database, jobId: string): Promise<void> {
  // Fetch only invoices that have not been claimed by any run yet.
  // Use a `claimed_by` column set atomically before processing.
  const pending = await db
    .prepare(
      `UPDATE invoices
       SET claimed_by = ?, claimed_at = CURRENT_TIMESTAMP
       WHERE status = 'pending' AND claimed_by IS NULL
       RETURNING id, amount_cents, stripe_customer_id`,
    )
    .bind(jobId)
    .all<{ id: string; amount_cents: number; stripe_customer_id: string }>();

  console.log(`[${jobId}] Claimed ${pending.results.length} invoices.`);

  for (const invoice of pending.results) {
    try {
      await chargeCustomer(invoice.stripe_customer_id, invoice.amount_cents, invoice.id);
      await db
        .prepare(`UPDATE invoices SET status = 'paid', paid_at = CURRENT_TIMESTAMP WHERE id = ?`)
        .bind(invoice.id)
        .run();
    } catch (err) {
      // On failure: release the claim so the next run can retry.
      await db
        .prepare(`UPDATE invoices SET claimed_by = NULL, claimed_at = NULL WHERE id = ?`)
        .bind(invoice.id)
        .run();
      console.error(`[${jobId}] Failed to charge invoice ${invoice.id}:`, err);
    }
  }
}
```

The `claimed_by` column acts as a per-row lock; the `UPDATE … WHERE claimed_by IS NULL`
is atomic in SQLite, so two concurrent invocations racing to claim the same row will
each see a disjoint set of invoices — even without the DO-level lock.

---

## Monitoring Cron Execution Time

Emit structured telemetry so you know when job duration approaches the cron interval.

```typescript
// src/billing-job.ts (addition)
export async function runBillingJobTimed(
  db: D1Database,
  jobId: string,
): Promise<void> {
  const start = Date.now();
  await runBillingJob(db, jobId);
  const durationMs = Date.now() - start;

  // Alert if the job took more than 80 % of the cron interval.
  const CRON_INTERVAL_MS = 5 * 60 * 1_000;
  if (durationMs > CRON_INTERVAL_MS * 0.8) {
    console.warn(
      JSON.stringify({
        level: "WARN",
        event: "cron_overrun_risk",
        jobId,
        durationMs,
        intervalMs: CRON_INTERVAL_MS,
        utilizationPct: Math.round((durationMs / CRON_INTERVAL_MS) * 100),
      }),
    );
  }
}
```

Route this structured log to Logpush → R2 or Analytics Engine and alert when
`utilizationPct > 80` on two consecutive runs.

---

## Wrangler Configuration

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "CRON_LOCK"
class_name = "CronLockDO"

[[migrations]]
tag = "v1"
new_classes = ["CronLockDO"]

[triggers]
crons = ["*/5 * * * *"]

[limits]
# Unbound billing job; set cpu_ms ceiling explicitly.
cpu_ms = 30_000
```

---

## Anti-patterns

- **Assuming only one invocation runs at a time** — Cloudflare makes no such
  guarantee. Always design cron Workers as if two copies may execute simultaneously.
- **KV as a distributed lock** — KV is eventually consistent; two Workers in different
  data centres can both read `lock=null` and both proceed. Use a Durable Object for
  locks that require strong consistency.
- **Lock TTL shorter than the job's maximum duration** — if the lock expires while the
  job is still running, a second invocation will steal it and start a concurrent run.
  Set TTL to at least 2× the P99 job duration.
- **Not releasing the lock in a `finally` block** — an uncaught exception before the
  `release` call leaves the lock held until the TTL expires, causing all subsequent
  invocations within that window to be skipped.

---

## Gotchas

- **CPU time ≠ wall-clock time**: a job that calls external APIs will spend most of
  its time waiting (not consuming CPU), so it can run for many minutes while reporting
  low CPU usage. Only wall-clock time is relevant for overrun detection.
- **Durable Object cold starts**: the first `lock.tryAcquire()` call after the DO has
  been evicted takes ~1–5 ms longer. On very tight cron intervals (< 1 minute), this
  can add up; size your TTL accordingly.
- **`event.scheduledTime`** is the *intended* fire time, not the actual start time.
  Two back-to-back cron invocations at T=0 and T=5 will have different
  `scheduledTime` values; use this to build deterministic `jobId` values for
  idempotency keys.
- `ctx.waitUntil()` extends the Worker's lifetime but does not extend cron isolation
  — the scheduled event's own lifetime limit still applies.

---

## Verification

```bash
# Simulate concurrent invocations locally with wrangler:
npx wrangler dev &
# Fire the scheduled handler twice in rapid succession:
curl http://localhost:8787/__scheduled?cron=*%2F5+*+*+*+*
curl http://localhost:8787/__scheduled?cron=*%2F5+*+*+*+*

# Check that the second call logs "Previous invocation still running — skipping."
# and that invoice rows are NOT claimed twice.

npx wrangler d1 execute BILLING_DB \
  --command "SELECT COUNT(*) FROM invoices WHERE status='paid' AND DATE(paid_at)=DATE('now');"
```

---

## Related

- `workers-cron-trigger-drift-missed-executions-postmortem.md`
- `durable-objects-storage-quota-limit-incident.md`
- `queue-consumers-must-be-idempotent.md`
- `idempotency-keys-for-all-payment-calls.md`
- `d1-write-contention-viral-event-postmortem.md`

---

## Sources

- Cloudflare Workers – Cron Triggers:
  https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare Durable Objects – Consistency model:
  https://developers.cloudflare.com/durable-objects/reference/in-memory-state/
- Internal postmortem #2766 (2026-01-30) — "Billing cron double-charged 500 customers"
- Stripe idempotency keys documentation:
  https://stripe.com/docs/api/idempotent_requests
