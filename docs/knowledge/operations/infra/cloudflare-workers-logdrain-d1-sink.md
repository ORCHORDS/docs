# Cloudflare Workers Log Drain to D1 Sink via Tail Worker

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case**: You want to capture structured logs emitted by your Workers (via `console.log`, custom log objects, or error traces) and store them in a queryable D1 database — without a third-party log service, without Logpush to an external bucket, and with sub-second latency from event to queryable row.

**Context**: Cloudflare's Tail Workers feature lets you attach a consumer Worker to any producer Worker. The tail Worker receives `TraceItem[]` events after each request completes, including all `console.*` calls, exceptions, fetch subrequests, and metadata (status, duration, CPU time). Batching these into D1 gives you a lightweight SQL log store queryable from any Worker or the Cloudflare dashboard's D1 SQL console. The pattern suits audit logging, error aggregation, and usage analytics at low-to-medium volume (D1 write throughput caps apply).

---

## D1 Schema Setup

```sql
-- migrations/0001_create_logs.sql
CREATE TABLE IF NOT EXISTS worker_logs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,           -- epoch ms from TraceItem.eventTimestamp
  worker_name TEXT    NOT NULL,
  ray_id      TEXT,
  outcome     TEXT    NOT NULL,           -- 'ok' | 'exception' | 'exceededCpu' | etc.
  status      INTEGER,                    -- HTTP response status if fetch event
  duration_ms REAL,
  cpu_ms      REAL,
  level       TEXT    NOT NULL DEFAULT 'info',  -- derived from console method
  message     TEXT    NOT NULL,
  error_name  TEXT,
  error_stack TEXT
);

CREATE INDEX IF NOT EXISTS idx_logs_ts     ON worker_logs (ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_worker ON worker_logs (worker_name, ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_outcome ON worker_logs (outcome) WHERE outcome != 'ok';
```

```bash
# Provision the D1 database (Wrangler)
wrangler d1 create worker-logs-db
wrangler d1 execute worker-logs-db --file=migrations/0001_create_logs.sql --remote
```

## Tail Worker Implementation

```typescript
// tail-worker/src/index.ts
export interface Env {
  LOG_DB: D1Database;
  LOG_WORKER_FILTER?: string; // optional: comma-separated worker names to include
}

interface LogRow {
  ts: number;
  worker_name: string;
  ray_id: string | null;
  outcome: string;
  status: number | null;
  duration_ms: number | null;
  cpu_ms: number | null;
  level: string;
  message: string;
  error_name: string | null;
  error_stack: string | null;
}

export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    const filter = env.LOG_WORKER_FILTER?.split(",").map((s) => s.trim());
    const rows: LogRow[] = [];

    for (const event of events) {
      const workerName = event.scriptName ?? "unknown";
      if (filter && !filter.includes(workerName)) continue;

      const fetchEvent = event.event && "request" in event.event ? event.event : null;
      const status = fetchEvent && "response" in fetchEvent
        ? (fetchEvent as { response?: { status: number } }).response?.status ?? null
        : null;

      // Emit one row per console.* log line
      for (const log of event.logs) {
        rows.push({
          ts: event.eventTimestamp,
          worker_name: workerName,
          ray_id: fetchEvent && "request" in fetchEvent
            ? ((fetchEvent as { request: { headers: Record<string, string> } })
                .request.headers["cf-ray"] ?? null)
            : null,
          outcome: event.outcome,
          status,
          duration_ms: event.wallTime ?? null,
          cpu_ms: event.cpuTime ?? null,
          level: log.level,
          message: log.message.map((m) => (typeof m === "string" ? m : JSON.stringify(m))).join(" "),
          error_name: null,
          error_stack: null,
        });
      }

      // Emit one row per exception
      for (const exc of event.exceptions) {
        rows.push({
          ts: event.eventTimestamp,
          worker_name: workerName,
          ray_id: null,
          outcome: event.outcome,
          status,
          duration_ms: event.wallTime ?? null,
          cpu_ms: event.cpuTime ?? null,
          level: "error",
          message: exc.message,
          error_name: exc.name,
          error_stack: null,
        });
      }
    }

    if (rows.length === 0) return;

    // Batch insert — D1 supports up to 100 statements per batch
    ctx.waitUntil(insertBatch(env.LOG_DB, rows));
  },
};

async function insertBatch(db: D1Database, rows: LogRow[]): Promise<void> {
  const stmt = db.prepare(
    `INSERT INTO worker_logs
       (ts, worker_name, ray_id, outcome, status, duration_ms, cpu_ms, level, message, error_name, error_stack)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  );

  // D1 batch executes all statements in a single SQLite transaction
  const statements = rows.map((r) =>
    stmt.bind(
      r.ts, r.worker_name, r.ray_id, r.outcome, r.status,
      r.duration_ms, r.cpu_ms, r.level, r.message, r.error_name, r.error_stack
    )
  );

  await db.batch(statements);
}
```

## Wrangler Configuration

```toml
# tail-worker/wrangler.toml
name = "log-drain-tail"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding      = "LOG_DB"
database_name = "worker-logs-db"
database_id  = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
LOG_WORKER_FILTER = "api-gateway,auth-worker,payment-worker"

# Tail workers are deployed normally; the tail binding is set on the producer
```

```toml
# Producer worker's wrangler.toml — attach the tail consumer
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[tail_consumers]]
service = "log-drain-tail"
```

## Querying Logs from D1

```typescript
// query-worker/src/index.ts — an internal admin Worker for log queries
export interface Env { LOG_DB: D1Database; }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const worker = url.searchParams.get("worker") ?? "%";
    const level  = url.searchParams.get("level")  ?? "%";
    const since  = Number(url.searchParams.get("since") ?? Date.now() - 3_600_000);
    const limit  = Math.min(Number(url.searchParams.get("limit") ?? 100), 500);

    const { results } = await env.LOG_DB
      .prepare(
        `SELECT ts, worker_name, ray_id, outcome, status, duration_ms, level, message, error_name
         FROM worker_logs
         WHERE ts >= ?
           AND worker_name LIKE ?
           AND level LIKE ?
         ORDER BY ts DESC
         LIMIT ?`
      )
      .bind(since, worker, level, limit)
      .all();

    return Response.json({ logs: results, count: results.length });
  },
};
```

## Terraform: Provisioning the Log Drain Infrastructure

```hcl
# terraform/log-drain.tf
resource "cloudflare_d1_database" "worker_logs" {
  account_id = var.cloudflare_account_id
  name       = "worker-logs-db"
}

resource "cloudflare_worker_script" "log_drain_tail" {
  account_id = var.cloudflare_account_id
  name       = "log-drain-tail"
  content    = file("${path.module}/../dist/tail-worker.js")

  d1_database_binding {
    name        = "LOG_DB"
    database_id = cloudflare_d1_database.worker_logs.id
  }

  plain_text_binding {
    name = "LOG_WORKER_FILTER"
    text = join(",", var.log_worker_names)
  }
}

# Attach the tail consumer to each producer via workers_script resource
# (Terraform Cloudflare provider v5+: tail_consumers block on the producer resource)
resource "cloudflare_worker_script" "api_gateway" {
  account_id = var.cloudflare_account_id
  name       = "api-gateway"
  content    = file("${path.module}/../dist/api-gateway.js")

  tail_consumers {
    service     = cloudflare_worker_script.log_drain_tail.name
    environment = "production"
  }
}
```

## Retention Cleanup Cron

```typescript
// Add to tail-worker or a separate cron Worker:
// Deletes rows older than 30 days to prevent unbounded D1 growth
export default {
  async scheduled(_: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
    ctx.waitUntil(
      env.LOG_DB.prepare("DELETE FROM worker_logs WHERE ts < ?").bind(cutoff).run()
    );
  },
};
```

---

**Anti-patterns**:
- Inserting one D1 statement per log line outside of `db.batch()` — each individual D1 write has ~5ms network overhead; batching amortizes this across all rows in an event batch.
- Storing raw JSON blobs instead of structured columns — prevents indexed queries on level, outcome, or worker name.
- Not using `ctx.waitUntil()` for the D1 write — tail worker execution ends when the handler returns; without `waitUntil` the write is abandoned.
- Tailing very high-throughput Workers (>10k RPS) without sampling — D1 write limits will be hit; add a `Math.random() < sampleRate` gate per event.
- Forgetting to deploy the tail worker before the producer — Cloudflare silently drops tail events if the consumer script is missing.

**Gotchas**:
- Tail Workers receive events asynchronously and may receive them out of order — do not rely on insertion order for sequencing.
- D1 `db.batch()` is limited to 100 statements; split large event batches into chunks of 100.
- `event.wallTime` (duration) is in milliseconds as a float; `event.cpuTime` is CPU-only ms — both may be `undefined` for non-fetch events (cron, queue).
- The `tail_consumers` binding in wrangler.toml requires the consumer to be deployed in the **same account** — cross-account tail is not supported.
- D1 is not suitable as the primary log sink above ~1M rows without periodic archival — query performance degrades without regular `VACUUM` and index maintenance.

**Verification**:
```bash
# Deploy tail worker first
wrangler deploy --config tail-worker/wrangler.toml

# Deploy producer with tail_consumers binding
wrangler deploy --config api-gateway/wrangler.toml

# Trigger some requests, then query D1
wrangler d1 execute worker-logs-db --remote \
  --command "SELECT level, COUNT(*) FROM worker_logs GROUP BY level ORDER BY 2 DESC"

# Check for recent errors
wrangler d1 execute worker-logs-db --remote \
  --command "SELECT ts, worker_name, message FROM worker_logs WHERE level='error' ORDER BY ts DESC LIMIT 10"
```

**Related**:
- `cloudflare-logpush-terraform-pipeline.md`
- `workers-opentelemetry-tail-workers.md`
- `cloudflare-d1-migrations-github-actions.md`
- `cloudflare-d1-time-travel-point-in-time-recovery.md`

**Sources**:
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/
