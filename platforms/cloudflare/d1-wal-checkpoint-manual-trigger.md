# D1 WAL Checkpoint Manual Trigger Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your D1 database WAL (Write-Ahead Log) file grows unbounded during a bulk-import or high-write burst, causing read queries to slow down as SQLite must replay a long WAL chain. You need to force a WAL checkpoint from inside a Worker to compact the WAL back into the main database file and restore read performance.

## Context

D1 runs on SQLite in WAL mode. Writes append to a WAL file; reads see a consistent snapshot by scanning the WAL before the main file. When the WAL grows large — typically after thousands of write transactions — SQLite checkpoints automatically, but auto-checkpoint thresholds may not fire fast enough under D1's managed environment. Workers can issue `PRAGMA wal_checkpoint(TRUNCATE)` via `db.exec()` to force an immediate full checkpoint. This is a maintenance operation: the Worker holds a brief exclusive lock, so it should run outside of peak traffic or in a Cron Trigger.

## Checking WAL Status Before Checkpointing

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Returns: busy pages, log pages, checkpointed pages
    const status = await env.DB.prepare(
      "PRAGMA wal_checkpoint(PASSIVE)"
    ).first<{ busy: number; log: number; checkpointed: number }>();

    return Response.json({
      busy: status?.busy,
      logPages: status?.log,
      checkpointedPages: status?.checkpointed,
      needsFullCheckpoint: (status?.busy ?? 0) > 0,
    });
  },
} satisfies ExportedHandler<Env>;

interface Env {
  DB: D1Database;
}
```

## Forcing a Full Checkpoint via TRUNCATE Mode

```typescript
// TRUNCATE resets the WAL file to zero bytes after checkpointing
// Use over FULL or RESTART when you want disk space reclaimed immediately
export async function forceCheckpoint(db: D1Database): Promise<void> {
  const result = await db
    .prepare("PRAGMA wal_checkpoint(TRUNCATE)")
    .first<{ busy: number; log: number; checkpointed: number }>();

  if ((result?.busy ?? 0) > 0) {
    // busy > 0 means active readers blocked some pages; retry after a pause
    throw new Error(
      `Checkpoint incomplete: ${result?.busy} pages blocked by active readers`
    );
  }

  console.log(`Checkpoint complete. Pages written: ${result?.checkpointed}`);
}
```

## Scheduled Checkpoint via Cron Trigger

```typescript
// wrangler.toml:
// [[triggers]]
// crons = ["0 3 * * *"]   # 3 AM UTC daily

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runCheckpoint(env.DB));
  },
} satisfies ExportedHandler<Env>;

async function runCheckpoint(db: D1Database): Promise<void> {
  const MAX_RETRIES = 3;
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    const result = await db
      .prepare("PRAGMA wal_checkpoint(TRUNCATE)")
      .first<{ busy: number; log: number; checkpointed: number }>();

    if ((result?.busy ?? 0) === 0) {
      console.log(`[checkpoint] success on attempt ${attempt}, pages: ${result?.checkpointed}`);
      return;
    }

    // Exponential back-off between retries
    await new Promise((r) => setTimeout(r, attempt * 500));
  }

  console.error("[checkpoint] could not complete after max retries");
}
```

## Post-Bulk-Import Checkpoint Pattern

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (new URL(req.url).pathname !== "/import") return new Response("Not found", { status: 404 });

    const rows: Array<{ id: string; value: string }> = await req.json();

    // Batch writes in chunks of 100
    const CHUNK = 100;
    for (let i = 0; i < rows.length; i += CHUNK) {
      const chunk = rows.slice(i, i + CHUNK);
      const stmts = chunk.map((r) =>
        env.DB.prepare("INSERT INTO events (id, value) VALUES (?, ?)").bind(r.id, r.value)
      );
      await env.DB.batch(stmts);
    }

    // Compact WAL immediately after the import completes
    await env.DB.prepare("PRAGMA wal_checkpoint(TRUNCATE)").run();

    return Response.json({ imported: rows.length });
  },
} satisfies ExportedHandler<Env>;
```

## Monitoring WAL Growth with Analytics Engine

```typescript
export async function emitWalMetrics(db: D1Database, ae: AnalyticsEngineDataset): Promise<void> {
  const status = await db
    .prepare("PRAGMA wal_checkpoint(PASSIVE)")
    .first<{ busy: number; log: number; checkpointed: number }>();

  ae.writeDataPoint({
    blobs: ["d1_wal_status"],
    doubles: [
      status?.log ?? 0,
      status?.checkpointed ?? 0,
      status?.busy ?? 0,
    ],
    indexes: ["production"],
  });
}
```

## Anti-patterns

- Running `TRUNCATE` checkpoint during peak read traffic — it briefly blocks new readers until all current readers drain; prefer off-peak Cron Triggers.
- Calling checkpoint after every single write — SQLite's auto-checkpoint handles normal cadence; manual triggers are for bulk operations or maintenance windows only.
- Ignoring `busy > 0` return — a partial checkpoint leaves WAL pages un-compacted; always check and retry.
- Using `RESTART` mode instead of `TRUNCATE` — `RESTART` does not zero the WAL file, so the file stays large even after checkpointing.

## Gotchas

- D1 is serverless SQLite; Cloudflare's infrastructure also runs periodic checkpoints independently. Manual `PRAGMA wal_checkpoint` is additive, not a replacement.
- The checkpoint PRAGMA returns a single row with columns `busy`, `log`, `checkpointed` — use `.first()` not `.all()`.
- In D1's multi-region read-replica architecture, checkpointing on the primary does not immediately reflect on replicas; replicas catch up asynchronously.
- `db.exec("PRAGMA wal_checkpoint(TRUNCATE)")` does not return result rows — use `.prepare().first()` to capture the outcome.
- Checkpoint latency increases linearly with WAL size; a WAL with millions of pages can cause the Worker to approach its CPU time limit on the Standard tier.

## Verification

```bash
# Check WAL page count before and after
wrangler d1 execute MY_DB --command "PRAGMA wal_checkpoint(PASSIVE);"

# Confirm WAL mode is active
wrangler d1 execute MY_DB --command "PRAGMA journal_mode;"

# Inspect page count after TRUNCATE
wrangler d1 execute MY_DB --command "PRAGMA page_count; PRAGMA freelist_count;"
```

## Related

- `d1-pragma-tuning.md` — WAL mode configuration, cache size, and synchronous pragmas
- `d1-best-practices.md` — batch write patterns and transaction hygiene
- `workers-cron-triggers.md` — scheduling maintenance Workers
- `cloudflare-workers-analytics-engine-custom-metrics.md` — emitting WAL metrics
- `workers-unbound-cpu-time-management.md` — CPU budget for long-running maintenance tasks

## Sources

- https://developers.cloudflare.com/d1/reference/database-commands/
- https://www.sqlite.org/wal.html#ckpt
- https://developers.cloudflare.com/d1/build-with-d1/d1-and-database-writes/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
