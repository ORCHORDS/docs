# D1 WAL Checkpoint Manual Optimization — Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Write throughput on a D1 database degrades over time in production. PRAGMA `wal_autocheckpoint` defaults keep the WAL file larger than expected, query latency spikes during automatic checkpoints, and you need deterministic checkpoint windows — e.g. during off-peak Cron Triggers — rather than letting SQLite choose.

---

## Context

D1 is backed by SQLite running in WAL (Write-Ahead Log) mode. In WAL mode every write appends to the WAL file; readers snapshot the latest commit and scan the WAL forward. Periodically SQLite *checkpoints* — it copies committed WAL frames back into the main database file and resets the WAL pointer.

Cloudflare manages the physical WAL file, but as of 2026 D1 exposes enough PRAGMA surface to influence checkpoint behaviour from within a Worker binding. Key levers:

| PRAGMA | Purpose |
|---|---|
| `wal_autocheckpoint` | Trigger threshold (pages); 0 disables auto-checkpoint |
| `wal_checkpoint(MODE)` | Trigger a checkpoint manually; modes: PASSIVE, FULL, RESTART, TRUNCATE |
| `page_count` / `freelist_count` | Measure database file fragmentation |

Manual checkpoints are useful for:
- Shifting checkpoint cost to Cron Triggers (off-peak)
- Ensuring a clean WAL before a schema migration
- Reducing reader latency spikes caused by large auto-checkpoint stalls

---

## Disabling Auto-checkpoint Before Heavy Writes

```typescript
// src/lib/d1-checkpoint.ts
import type { D1Database } from "@cloudflare/workers-types";

export async function disableAutoCheckpoint(db: D1Database): Promise<void> {
  // Setting to 0 disables automatic checkpointing entirely.
  // Callers are responsible for running manual checkpoints.
  await db.prepare("PRAGMA wal_autocheckpoint = 0").run();
}

export async function restoreAutoCheckpoint(
  db: D1Database,
  pages = 1000
): Promise<void> {
  await db.prepare(`PRAGMA wal_autocheckpoint = ${pages}`).run();
}
```

---

## Querying WAL Status

Before deciding whether a checkpoint is needed, measure the WAL lag:

```typescript
// src/lib/wal-status.ts
import type { D1Database } from "@cloudflare/workers-types";

interface WalStatus {
  walFrames: number;     // Frames written since last checkpoint
  pageCount: number;     // Total pages in main database file
  freelistCount: number; // Unused pages (fragmentation indicator)
  walSizeRatio: number;  // walFrames / pageCount — high = checkpoint needed
}

export async function getWalStatus(db: D1Database): Promise<WalStatus> {
  const [walRow, pageRow, freeRow] = await db.batch([
    db.prepare("PRAGMA wal_checkpoint(PASSIVE)"), // lightweight probe
    db.prepare("PRAGMA page_count"),
    db.prepare("PRAGMA freelist_count"),
  ]);

  // PASSIVE returns (busy, log, checkpointed) — we want `log`
  const busy = (walRow.results[0] as any)?.busy ?? 0;
  const log = (walRow.results[0] as any)?.log ?? 0;
  const pageCount = (pageRow.results[0] as any)?.page_count ?? 1;
  const freelistCount = (freeRow.results[0] as any)?.freelist_count ?? 0;

  return {
    walFrames: log,
    pageCount,
    freelistCount,
    walSizeRatio: log / pageCount,
  };
}
```

---

## Manual Checkpoint via Cron Trigger

```typescript
// src/handlers/checkpoint-cron.ts
import type { D1Database } from "@cloudflare/workers-types";
import { getWalStatus } from "../lib/wal-status";

interface CheckpointResult {
  mode: string;
  busy: number;
  log: number;
  checkpointed: number;
  durationMs: number;
}

/**
 * Run an appropriate checkpoint mode based on WAL pressure.
 *
 * PASSIVE  – non-blocking; readers keep running; WAL may not fully drain
 * FULL     – waits for readers to finish, then checkpoints; WAL drains
 * RESTART  – like FULL, then resets WAL write position to 0 (next writes reuse frames)
 * TRUNCATE – like RESTART, then physically truncates the WAL file to 0 bytes
 */
export async function runScheduledCheckpoint(
  db: D1Database
): Promise<CheckpointResult> {
  const status = await getWalStatus(db);
  const start = Date.now();

  // Choose aggressiveness based on WAL pressure
  let mode: "PASSIVE" | "FULL" | "RESTART" | "TRUNCATE";
  if (status.walSizeRatio < 0.1) {
    mode = "PASSIVE";
  } else if (status.walSizeRatio < 0.4) {
    mode = "FULL";
  } else {
    // High WAL pressure — truncate to reclaim disk space
    mode = "TRUNCATE";
  }

  const result = await db
    .prepare(`PRAGMA wal_checkpoint(${mode})`)
    .first<{ busy: number; log: number; checkpointed: number }>();

  return {
    mode,
    busy: result?.busy ?? -1,
    log: result?.log ?? -1,
    checkpointed: result?.checkpointed ?? -1,
    durationMs: Date.now() - start,
  };
}
```

---

## Wrangler Scheduled Handler Integration

```typescript
// src/index.ts
import type { Env } from "./types";
import { runScheduledCheckpoint } from "./handlers/checkpoint-cron";
import { disableAutoCheckpoint, restoreAutoCheckpoint } from "./lib/d1-checkpoint";

export default {
  async scheduled(
    event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    if (event.cron === "0 3 * * *") {
      // 03:00 UTC daily — checkpoint window
      ctx.waitUntil(
        (async () => {
          try {
            // Pause auto-checkpoints so Cron owns the window
            await disableAutoCheckpoint(env.DB);
            const result = await runScheduledCheckpoint(env.DB);
            console.log("Checkpoint complete", JSON.stringify(result));
          } finally {
            // Always re-enable, even on failure
            await restoreAutoCheckpoint(env.DB, 1000);
          }
        })()
      );
    }
  },
} satisfies ExportedHandler<Env>;
```

```toml
# wrangler.toml (relevant excerpt)
[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[triggers]
crons = ["0 3 * * *"]
```

---

## Checkpoint Before Schema Migrations

Ensure a clean WAL state before running DDL statements to reduce the risk of a migration interleaving with uncommitted WAL frames:

```typescript
// src/lib/migration-guard.ts
import type { D1Database } from "@cloudflare/workers-types";

export async function checkpointBeforeMigration(
  db: D1Database
): Promise<void> {
  // TRUNCATE gives the cleanest slate: drains WAL + truncates file
  const result = await db
    .prepare("PRAGMA wal_checkpoint(TRUNCATE)")
    .first<{ busy: number; log: number; checkpointed: number }>();

  if (result && result.busy > 0) {
    throw new Error(
      `Checkpoint blocked by ${result.busy} active readers — abort migration`
    );
  }

  const remaining = (result?.log ?? 0) - (result?.checkpointed ?? 0);
  if (remaining > 0) {
    throw new Error(
      `WAL not fully drained: ${remaining} frames remain — retry migration later`
    );
  }
}
```

---

## Monitoring Checkpoint Health

```typescript
// src/lib/checkpoint-metrics.ts
import type { D1Database } from "@cloudflare/workers-types";

export interface CheckpointHealth {
  healthy: boolean;
  walFrames: number;
  walSizeRatio: number;
  recommendation: string;
}

export async function checkCheckpointHealth(
  db: D1Database
): Promise<CheckpointHealth> {
  const { walFrames, pageCount, walSizeRatio, freelistCount } =
    await getWalStatus(db);

  let recommendation = "WAL healthy — no action required";
  let healthy = true;

  if (walSizeRatio > 0.5) {
    healthy = false;
    recommendation = "WAL pressure high — schedule TRUNCATE checkpoint";
  } else if (freelistCount / pageCount > 0.3) {
    recommendation = "High fragmentation — consider VACUUM after checkpoint";
  }

  return { healthy, walFrames, walSizeRatio, recommendation };
}

// Re-export for convenience
import { getWalStatus } from "./wal-status";
```

---

## Anti-patterns

- **Never run `RESTART` or `TRUNCATE` during peak traffic.** These modes block new writes until all existing readers finish, causing latency spikes visible to end users.
- **Don't disable auto-checkpoint indefinitely.** An unbounded WAL file causes all readers to scan from frame 0 on every query. Always re-enable or call TRUNCATE periodically.
- **Don't checkpoint from request handlers.** Checkpoint duration is unpredictable (tens to hundreds of milliseconds). Use Cron Triggers or Durable Object alarms.
- **Don't rely on `PASSIVE` for pre-migration cleanup.** PASSIVE returns immediately even when the WAL is not fully drained (`log > checkpointed`). Use `FULL` or `TRUNCATE` before DDL.
- **Don't skip the `busy > 0` guard.** If readers are active, `FULL`/`RESTART`/`TRUNCATE` will wait — this can stall a Worker past the CPU time limit.

---

## Gotchas

- **D1 replication model**: D1 has a primary writer and read replicas. Manual checkpoint PRAGMAs only act on the primary. Replicas sync asynchronously — immediately querying a replica after a TRUNCATE checkpoint may return slightly stale data.
- **`wal_autocheckpoint = 0` survives the connection**: In D1, each Worker invocation gets a fresh connection. Setting `wal_autocheckpoint = 0` in one request does NOT persist to the next — you must set it at the start of every invocation that needs it.
- **PRAGMA return shapes differ by mode**: `PASSIVE`/`FULL`/`RESTART`/`TRUNCATE` all return `(busy, log, checkpointed)` but `wal_autocheckpoint` returns the current page threshold. Parse accordingly.
- **Cloudflare may impose checkpoint limits**: As D1 matures, Cloudflare may restrict certain checkpoint modes in shared environments. Always test in a preview database first.

---

## Verification

```typescript
// Verify checkpoint ran successfully
async function verifyCheckpoint(db: D1Database): Promise<boolean> {
  const result = await db
    .prepare("PRAGMA wal_checkpoint(PASSIVE)")
    .first<{ busy: number; log: number; checkpointed: number }>();

  if (!result) return false;

  const drained = result.log === result.checkpointed;
  const noBlockers = result.busy === 0;

  console.log("Checkpoint verification:", {
    drained,
    noBlockers,
    log: result.log,
    checkpointed: result.checkpointed,
  });

  return drained && noBlockers;
}
```

Run the Cron handler via `wrangler dev --test-scheduled` and confirm the log output shows `checkpointed === log` and `busy === 0`.

---

## Related

- `d1-wal-mode-read-performance-workers.md` — WAL mode read latency optimizations
- `d1-vacuum-incremental-maintenance-workers.md` — VACUUM after checkpoint to reclaim space
- `d1-migrations-wrangler-ci-cd.md` — Migration runner that calls checkpoint guard
- `d1-materialized-view-simulation-cron.md` — Another Cron Trigger pattern for DB maintenance
- `sqlite-wal-mode.md` — SQLite WAL internals reference

---

## Sources

- SQLite WAL documentation: https://www.sqlite.org/wal.html
- SQLite `wal_checkpoint` PRAGMA: https://www.sqlite.org/pragma.html#pragma_wal_checkpoint
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
