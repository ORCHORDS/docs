# Detecting Slow D1 Queries via Tail Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application uses D1 for persistence and you are seeing elevated p95 response times but cannot identify which queries are the bottleneck. You want automatic capture of slow queries in production without adding instrumentation to every query call site.

## Context

A Tail Worker is a special Worker bound to a primary ("producer") Worker. After the primary Worker completes a request, the runtime delivers a `TailEvent` to the Tail Worker containing the request metadata, outcome, CPU time, and — crucially — all `console.log` / `console.error` output emitted during the request. You can instrument D1 queries to log their duration and parse those log lines in the Tail Worker to detect slow queries without modifying the primary Worker's business logic beyond adding a thin timing wrapper.

---

## Instrumented D1 Query Wrapper

```typescript
// src/db.ts  (runs inside your main application Worker)
export interface Env {
  DB: D1Database;
}

/**
 * Wraps a D1 prepared statement with timing.
 * Emits: `D1 query: <hash> <duration_ms>ms <endpoint>`
 * The Tail Worker parses this log line to detect slow queries.
 */
export async function timedQuery<T = unknown>(
  stmt: D1PreparedStatement,
  queryHash: string,   // short identifier, e.g. MD5 of the SQL string
  endpoint: string     // request pathname, e.g. '/api/users'
): Promise<D1Result<T>> {
  const start = performance.now();
  try {
    const result = await stmt.all<T>();
    const duration = Math.round(performance.now() - start);
    // Structured log line the Tail Worker will parse:
    console.log(`D1 query: ${queryHash} ${duration}ms ${endpoint}`);
    return result;
  } catch (err) {
    const duration = Math.round(performance.now() - start);
    console.error(`D1 query error: ${queryHash} ${duration}ms ${endpoint} ${String(err)}`);
    throw err;
  }
}

// Usage in your main Worker:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const stmt = env.DB.prepare('SELECT * FROM products WHERE category = ?').bind('electronics');
    const rows = await timedQuery(stmt, 'products_by_cat', url.pathname);
    return Response.json(rows.results);
  },
};
```

---

## Tail Worker: Parsing Logs and Writing Slow Queries to D1

```typescript
// src/tail-worker.ts
export interface TailEnv {
  SLOW_DB: D1Database;    // separate D1 database for observability data
  SLOW_QUERY_THRESHOLD_MS: string;  // e.g. "100"
}

const LOG_PATTERN = /^D1 query: (\S+) (\d+)ms (\S+)$/;

interface TailLog {
  message: unknown[];
  level: string;
  timestamp: number;
}

interface TailEvent {
  event: { request: { url: string; method: string } } | null;
  logs: TailLog[];
  outcome: string;
  scriptName: string | null;
}

export default {
  async tail(events: TailEvent[], env: TailEnv): Promise<void> {
    const threshold = parseInt(env.SLOW_QUERY_THRESHOLD_MS ?? '100', 10);

    const inserts: Array<{ queryHash: string; durationMs: number; endpoint: string }> = [];

    for (const event of events) {
      for (const log of event.logs) {
        const message = String(log.message[0] ?? '');
        const match = LOG_PATTERN.exec(message);
        if (!match) continue;

        const [, queryHash, durationStr, endpoint] = match;
        const durationMs = parseInt(durationStr, 10);

        if (durationMs > threshold) {
          inserts.push({ queryHash, durationMs, endpoint });
        }
      }
    }

    if (inserts.length === 0) return;

    // Batch insert slow queries
    const stmt = env.SLOW_DB.prepare(
      `INSERT INTO slow_queries (query_hash, duration_ms, endpoint, logged_at)
       VALUES (?, ?, ?, datetime('now'))`
    );
    await env.SLOW_DB.batch(
      inserts.map(({ queryHash, durationMs, endpoint }) =>
        stmt.bind(queryHash, durationMs, endpoint)
      )
    );
  },
};
```

---

## D1 Schema for Slow Query Storage

```sql
-- migrations/0001_slow_queries.sql
CREATE TABLE IF NOT EXISTS slow_queries (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  query_hash  TEXT    NOT NULL,
  duration_ms INTEGER NOT NULL,
  endpoint    TEXT    NOT NULL,
  logged_at   TEXT    NOT NULL   -- ISO-8601 UTC, stored as TEXT in D1
);

CREATE INDEX idx_slow_queries_hash    ON slow_queries (query_hash);
CREATE INDEX idx_slow_queries_logged  ON slow_queries (logged_at);
```

---

## Weekly Cron: Top 10 Slowest Query Patterns

```typescript
// src/slow-query-summarizer.ts
// Add to wrangler.toml: [[triggers]] crons = ["0 9 * * 1"]
export default {
  async scheduled(_event: ScheduledEvent, env: TailEnv & { REPORT_WEBHOOK: string }) {
    const result = await env.SLOW_DB.prepare(`
      SELECT
        query_hash,
        COUNT(*)           AS occurrences,
        AVG(duration_ms)   AS avg_ms,
        MAX(duration_ms)   AS max_ms,
        MIN(duration_ms)   AS min_ms
      FROM slow_queries
      WHERE logged_at >= datetime('now', '-7 days')
      GROUP BY query_hash
      ORDER BY avg_ms DESC
      LIMIT 10
    `).all();

    const report = result.results
      .map((row: Record<string, unknown>, i) =>
        `${i + 1}. hash=${row.query_hash}  occurrences=${row.occurrences}  ` +
        `avg=${Math.round(row.avg_ms as number)}ms  max=${row.max_ms}ms`
      )
      .join('\n');

    await fetch(env.REPORT_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: `*Weekly Slow D1 Query Report*\n\`\`\`\n${report}\n\`\`\``,
      }),
    });

    // Prune rows older than 30 days to manage D1 storage
    await env.SLOW_DB.prepare(
      `DELETE FROM slow_queries WHERE logged_at < datetime('now', '-30 days')`
    ).run();
  },
};
```

---

## wrangler.toml Binding Snippet

```toml
# wrangler.toml (main application Worker)
name = "my-app"

[[tail_consumers]]
service = "my-app-tail"

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id   = "<app-db-id>"

# wrangler.toml (tail Worker — separate file / directory)
name = "my-app-tail"

[[d1_databases]]
binding = "SLOW_DB"
database_name = "slow-query-db"
database_id   = "<slow-db-id>"

[vars]
SLOW_QUERY_THRESHOLD_MS = "100"
```

---

## Anti-patterns

- **Logging full SQL strings** — these often contain user-supplied values; log only a hash or enum identifier.
- **Tail Worker writing back to the primary app's D1 database** — creates a circular dependency and risks lock contention; use a separate D1 database for observability.
- **Parsing unstructured log lines with fragile regex** — prefix all timing logs with a unique sentinel (e.g. `D1 query:`) and keep the format rigid.
- **Ignoring the Tail Worker 15-second CPU limit** — batch D1 inserts rather than inserting one row per log line.

## Gotchas

- Tail Workers only receive logs from Workers on the same Cloudflare account; cross-account tailing is not supported.
- The `logs` array in a `TailEvent` is capped at 100 entries per request; very chatty Workers may have logs truncated.
- `performance.now()` in Workers returns wall-clock milliseconds but resets between requests; do not subtract across request boundaries.
- Tail Workers are not invoked for Workers that return a response from Cache; instrument cache-bypass paths if needed.

## Verification

1. Deploy both Workers and the D1 schema migration.
2. Send a request that triggers the instrumented query.
3. Wait ~5 seconds (Tail Worker delivery is near-real-time but asynchronous).
4. Query `SELECT * FROM slow_queries ORDER BY logged_at DESC LIMIT 5;` in the SLOW_DB.
5. Verify `query_hash`, `duration_ms`, and `endpoint` are populated.

## Related

- `workers-latency-percentile-tracking-analytics-engine.md`
- `cloudflare-synthetic-monitoring-cron-workers.md`

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/performance/
