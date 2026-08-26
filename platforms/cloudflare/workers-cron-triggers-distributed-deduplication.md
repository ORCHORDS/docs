# Workers Cron Triggers Distributed Deduplication Pattern

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A scheduled Worker runs on multiple Cloudflare PoPs simultaneously during cron fan-out,
or the same cron fires twice in quick succession due to a retry. The job mutates shared
state (a D1 table, an R2 file, a third-party API) and double-execution causes duplicate
records, double-charged billing events, or corrupted aggregates.

You need a lightweight, edge-native deduplication guard that prevents a cron job from
running more than once per scheduled window without adding an external coordination
service.

---

## Context

Cloudflare Workers' `scheduled` handler is invoked by the cron engine. For global
accounts, the engine typically fires the job from a single PoP, but retries on failure
can cause back-to-back executions within the same window. During deploys or traffic
events, rare fan-outs to two PoPs have been observed.

Deduplication options on the Workers platform:

| Mechanism | TTL precision | Atomic CAS | Cost |
|-----------|--------------|------------|------|
| KV `putIfAbsent` (metadata trick) | ~60 s global consistency | No (eventual) | Cheap |
| Durable Object transaction | 1 ms | Yes (strong) | Per-DO request |
| D1 `INSERT OR IGNORE` + epoch | SQL precision | Yes (per-region) | Per query |

example project platform recommendation: use **Durable Objects** for strong deduplication when the
job mutates financial or audit data; use **KV** for best-effort deduplication of
idempotent analytics jobs.

---

## Pattern 1 — KV Best-Effort Lock

```typescript
// src/scheduled/analytics-rollup.ts
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const windowKey = `cron:lock:${event.scheduledTime}`;

    // Attempt to claim the window; KV.put with expiration acts as a TTL lock
    // putIfAbsent is not a native KV primitive — we use a read-then-write with
    // a conditional on an existing value.
    const existing = await env.CRON_LOCKS.get(windowKey);
    if (existing !== null) {
      console.log(`[cron] window ${event.scheduledTime} already claimed — skipping`);
      return;
    }

    // Write the lock with a 5-minute TTL (enough to cover retry windows)
    await env.CRON_LOCKS.put(windowKey, '1', { expirationTtl: 300 });

    // KV is eventually consistent — small race window exists here.
    // For best-effort jobs (analytics, cache warming) this is acceptable.
    ctx.waitUntil(runAnalyticsRollup(env));
  },
};

async function runAnalyticsRollup(env: Env): Promise<void> {
  const hour = new Date().toISOString().slice(0, 13); // e.g. "2026-08-23T14"
  await env.DB.prepare(
    `INSERT OR IGNORE INTO hourly_rollups (hour, computed_at)
     VALUES (?1, unixepoch())`,
  ).bind(hour).run();
  // ... aggregation logic
}
```

---

## Pattern 2 — Durable Object Strong Lock

```typescript
// src/do/cron-coordinator.ts
export class CronCoordinator implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(req: Request): Promise<Response> {
    const { windowKey, ttlMs } = await req.json<{ windowKey: string; ttlMs: number }>();

    // Transactional check-and-set — only one instance of this DO exists globally
    const claimed = await this.state.storage.transaction(async (txn) => {
      const existing = await txn.get<number>(windowKey);
      if (existing !== undefined && Date.now() - existing < ttlMs) {
        return false; // already claimed within TTL
      }
      await txn.put(windowKey, Date.now());
      return true;
    });

    return Response.json({ claimed });
  }
}
```

```typescript
// src/scheduled/billing-sync.ts
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const windowKey = `billing-sync:${event.scheduledTime}`;

    // Route to a single global DO instance using a fixed name
    const id = env.CRON_COORDINATOR.idFromName('global');
    const stub = env.CRON_COORDINATOR.get(id);

    const resp = await stub.fetch('https://do/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ windowKey, ttlMs: 5 * 60 * 1000 }),
    });
    const { claimed } = await resp.json<{ claimed: boolean }>();

    if (!claimed) {
      console.log(`[billing-sync] window ${event.scheduledTime} already running`);
      return;
    }

    ctx.waitUntil(runBillingSync(env));
  },
};

async function runBillingSync(env: Env): Promise<void> {
  // Strong guarantee: only one instance reaches here per window
  const rows = await env.DB.prepare(
    `SELECT id, amount FROM pending_charges WHERE synced = 0 LIMIT 500`,
  ).all<{ id: string; amount: number }>();

  for (const row of rows.results) {
    // idempotent external call + mark synced
    await chargeExternal(row, env);
    await env.DB.prepare('UPDATE pending_charges SET synced = 1 WHERE id = ?')
      .bind(row.id).run();
  }
}
```

---

## Pattern 3 — D1 Idempotency Table

```typescript
// src/scheduled/report-generator.ts
//
// Use D1 INSERT OR IGNORE to claim a window atomically at the database layer.
// This works for single-region D1 but is not multi-region atomic.

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const windowId = String(event.scheduledTime); // Unix ms timestamp

    const result = await env.DB.prepare(
      `INSERT OR IGNORE INTO cron_windows (window_id, worker_run_at)
       VALUES (?1, unixepoch())`,
    ).bind(windowId).run();

    if (result.meta.changes === 0) {
      console.log(`[report] window ${windowId} already processed`);
      return;
    }

    ctx.waitUntil(generateReports(env));
  },
};
```

```sql
-- migration: create the deduplication table
CREATE TABLE IF NOT EXISTS cron_windows (
  window_id   TEXT PRIMARY KEY,
  worker_run_at INTEGER NOT NULL,
  completed_at  INTEGER
);

-- Auto-expire old windows after 7 days via D1 scheduled cleanup
-- (or use a separate cron to DELETE WHERE worker_run_at < unixepoch() - 604800)
```

---

## Wrangler Configuration

```toml
# wrangler.toml
[triggers]
crons = ["0 * * * *"]   # every hour

[[kv_namespaces]]
binding = "CRON_LOCKS"
id      = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[durable_objects.bindings]]
name       = "CRON_COORDINATOR"
class_name = "CronCoordinator"

[[migrations]]
tag  = "v1"
new_classes = ["CronCoordinator"]

[[d1_databases]]
binding      = "DB"
database_id  = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
database_name = "example project-prod"
```

---

## Retry-Safe Job Cursor Pattern

```typescript
// For long-running cron jobs, checkpoint progress so retries resume where they left off
async function processInBatches(env: Env, windowId: string): Promise<void> {
  const cursorKey = `cron:cursor:${windowId}`;
  let cursor = (await env.CRON_LOCKS.get(cursorKey)) ?? '0';

  while (true) {
    const rows = await env.DB.prepare(
      `SELECT id FROM items WHERE id > ?1 ORDER BY id LIMIT 100`,
    ).bind(cursor).all<{ id: string }>();

    if (rows.results.length === 0) break;

    for (const row of rows.results) {
      await processItem(row.id, env);
      cursor = row.id;
    }

    // Persist cursor after each batch so a retry can resume here
    await env.CRON_LOCKS.put(cursorKey, cursor, { expirationTtl: 3600 });
  }

  // Clean up cursor on successful completion
  await env.CRON_LOCKS.delete(cursorKey);
}
```

---

## Observability: Detecting Duplicate Executions

```typescript
// Emit a metric when a duplicate is detected to alert on unexpected fan-out
import { WorkersAnalyticsEngine } from './types';

async function recordDedupEvent(
  env: Env,
  windowKey: string,
  claimed: boolean,
): Promise<void> {
  env.ANALYTICS.writeDataPoint({
    blobs: ['cron_dedup', windowKey],
    doubles: [claimed ? 1 : 0],
    indexes: [claimed ? 'claimed' : 'skipped'],
  });
}
```

```sql
-- Query duplicate skip rate in Analytics Engine SQL API
SELECT
  blob2 AS window_key,
  SUM(double1) AS claimed_count,
  COUNT(*) - SUM(double1) AS skipped_count
FROM ANALYTICS_ENGINE_DATASET
WHERE blob1 = 'cron_dedup'
  AND timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY blob2
HAVING skipped_count > 0
ORDER BY skipped_count DESC;
```

---

## Anti-patterns

- **Using `Date.now()` as the window key** — precision varies by millisecond across PoPs.
  Always use `event.scheduledTime`, which is the canonical cron-scheduled timestamp.
- **Skipping deduplication for "idempotent" jobs** — even truly idempotent jobs can cause
  double resource consumption (API rate limits, CPU time) if dedup is omitted.
- **Locking too broadly** — a single global lock for all cron types blocks unrelated jobs.
  Namespace lock keys per cron type (`billing:`, `analytics:`, etc.).
- **Never expiring lock keys** — without TTL, a crashed job leaves a permanent lock.
  Always set `expirationTtl` or use the D1 cleanup cron pattern.
- **Assuming DO strong consistency across bindings** — two different DO stub names produce
  different DO instances. Always use `idFromName('global')` with a fixed string.

---

## Gotchas

- `event.scheduledTime` is a Unix timestamp in **milliseconds** (not seconds) in the
  TypeScript type but the actual value from the cron engine is in seconds since epoch —
  verify with `console.log(event.scheduledTime)` before using as a string key.
- KV writes made during `scheduled` are not visible within the same invocation due to
  cache layers; the lock only protects against a second invocation starting after the
  first KV write propagates (~60 s globally).
- Durable Object `idFromName` always returns the same globally unique DO, but routing
  to it counts as a subrequest and consumes from the Workers subrequest budget (1 000/req).
- D1 `INSERT OR IGNORE` is atomic per write but D1 primary writers are regional; during
  a primary failover, two inserts at different PoPs could both succeed briefly.

---

## Verification

```typescript
// Vitest integration test — confirm only one execution per window
import { env } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';

describe('cron deduplication', () => {
  it('second invocation with same scheduledTime is skipped', async () => {
    const scheduledTime = 1_700_000_000_000;
    let execCount = 0;

    // Patch runAnalyticsRollup to count calls
    const originalRun = globalThis.__runAnalyticsRollup;
    globalThis.__runAnalyticsRollup = async () => { execCount++; };

    const event = { scheduledTime, cron: '0 * * * *' } as ScheduledEvent;
    await (await import('./analytics-rollup')).default.scheduled(event, env, {} as any);
    await (await import('./analytics-rollup')).default.scheduled(event, env, {} as any);

    expect(execCount).toBe(1);
    globalThis.__runAnalyticsRollup = originalRun;
  });
});
```

---

## Related

- `cloudflare-workers-cron-triggers-scheduling.md`
- `workers-cron-triggers.md`
- `durable-objects-distributed-lock-leader-election.md`
- `kv-eventually-consistent.md`
- `d1-transactions-isolation.md`

---

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://developers.cloudflare.com/d1/reference/database-commands/
