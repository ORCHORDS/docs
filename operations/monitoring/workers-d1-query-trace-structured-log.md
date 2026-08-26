# D1 Query Performance Tracing with Structured Logs in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
D1 queries in a production Worker are slow, but you have no visibility into which queries are the bottleneck or how many rows they return. You need a lightweight tracing layer that writes structured JSON logs consumable by `wrangler tail` without adding a third-party APM SDK.

---

## Context
Cloudflare Workers can emit structured logs to `console.log()` which are streamed in real-time via `wrangler tail`. When serialized as JSON, these logs can be filtered, aggregated, and piped through `jq` for local triage or forwarded to a log sink (Logpush, Workers Logpush to R2/S3) for long-term storage. Wrapping every D1 call in a timing helper makes slow-query detection automatic and provides the raw data needed to decide which columns require indexes. D1's prepared statements are pre-compiled per-isolate, so the overhead of the helper function itself is negligible compared to the network round-trip to the D1 database.

---

## Setup / Config

```toml
# wrangler.toml
name = "d1-trace-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "prod"
database_id = "YOUR_DATABASE_ID"
```

Enable Tail Workers or use `wrangler tail` for local streaming:

```bash
wrangler tail d1-trace-worker --format json
```

---

## Implementation

```typescript
// src/trace.ts
export interface QueryTrace {
  query: string;
  params: unknown[];
  durationMs: number;
  rowCount: number;
  success: boolean;
  error?: string;
}

/**
 * Wrap a D1 prepared statement execution in a timing helper.
 * Logs a structured JSON record to console.log after every query.
 */
export async function traceQuery<T extends Record<string, unknown>>(
  db: D1Database,
  query: string,
  params: unknown[] = []
): Promise<D1Result<T>> {
  const start = performance.now();
  let result: D1Result<T>;
  let success = true;
  let errorMsg: string | undefined;

  try {
    const stmt = db.prepare(query);
    result = await (params.length ? stmt.bind(...params) : stmt).all<T>();
  } catch (err) {
    success = false;
    errorMsg = err instanceof Error ? err.message : String(err);
    // Re-throw so the caller's error handling is unaffected
    throw err;
  } finally {
    const durationMs = Math.round((performance.now() - start) * 100) / 100;

    const trace: QueryTrace = {
      query,
      params,
      durationMs,
      rowCount: success ? (result!.results?.length ?? 0) : 0,
      success,
      ...(errorMsg ? { error: errorMsg } : {}),
    };

    // wrangler tail --format json surfaces this as a structured log entry
    console.log(JSON.stringify({ level: "query", ...trace }));
  }

  return result!;
}

/** Convenience: run a single-row fetch */
export async function traceQueryFirst<T extends Record<string, unknown>>(
  db: D1Database,
  query: string,
  params: unknown[] = []
): Promise<T | null> {
  const start = performance.now();
  let row: T | null = null;
  let success = true;
  let errorMsg: string | undefined;

  try {
    const stmt = db.prepare(query);
    row = await (params.length ? stmt.bind(...params) : stmt).first<T>();
    success = true;
  } catch (err) {
    success = false;
    errorMsg = err instanceof Error ? err.message : String(err);
    throw err;
  } finally {
    const durationMs = Math.round((performance.now() - start) * 100) / 100;
    console.log(
      JSON.stringify({
        level: "query",
        query,
        params,
        durationMs,
        rowCount: row !== null ? 1 : 0,
        success,
        ...(errorMsg ? { error: errorMsg } : {}),
      })
    );
  }

  return row;
}
```

```typescript
// src/index.ts
import { traceQuery, traceQueryFirst } from "./trace";

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/users") {
      const users = await traceQuery(
        env.DB,
        "SELECT id, email, created_at FROM users ORDER BY created_at DESC LIMIT 50"
      );
      return Response.json(users.results);
    }

    if (url.pathname.startsWith("/users/")) {
      const id = url.pathname.split("/")[2];
      const user = await traceQueryFirst(
        env.DB,
        "SELECT * FROM users WHERE id = ?",
        [id]
      );
      if (!user) return new Response("not found", { status: 404 });
      return Response.json(user);
    }

    return new Response("not found", { status: 404 });
  },
};
```

---

## Filtering Slow Queries with wrangler tail + jq

```bash
# Stream all query logs and pretty-print them
wrangler tail d1-trace-worker --format json | \
  jq 'select(.logs[]?.message[]? | type == "string" and startswith("{\"level\":\"query\"")) |
      .logs[].message[] | fromjson'

# Filter only queries slower than 100 ms
wrangler tail d1-trace-worker --format json 2>/dev/null | \
  jq --argjson threshold 100 '
    .logs[]?.message[]? |
    select(type == "string") |
    . as $raw |
    try fromjson catch null |
    select(. != null and .level == "query" and .durationMs > $threshold)
  '

# Aggregate average duration per unique query (run for 60s, then Ctrl-C)
wrangler tail d1-trace-worker --format json 2>/dev/null | \
  jq -r '.logs[]?.message[]? | select(type=="string") | try fromjson | select(.level=="query") | [.query, (.durationMs|tostring)] | @tsv' | \
  awk -F'\t' '{ sum[$1]+=$2; cnt[$1]++ } END { for (q in sum) printf "avg=%.1fms count=%d query=%s\n", sum[q]/cnt[q], cnt[q], q }'
```

---

## D1 Index Recommendations from Slow Query Patterns

Once you have slow query logs, look for:

| Pattern | Recommendation |
|---|---|
| `WHERE column = ?` with high `durationMs` | `CREATE INDEX idx_table_column ON table(column);` |
| `ORDER BY created_at DESC` full-scan | `CREATE INDEX idx_table_created ON table(created_at DESC);` |
| `JOIN` between large tables without index | Add index on the FK column of the larger table |
| `LIKE '%term%'` prefix wildcard | Consider FTS5 virtual table: `CREATE VIRTUAL TABLE fts USING fts5(...)` |

```bash
# Apply index via wrangler d1 execute
wrangler d1 execute prod \
  --command "CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at DESC);"

# Verify index is used (check for 'USING INDEX' in plan)
wrangler d1 execute prod \
  --command "EXPLAIN QUERY PLAN SELECT id FROM users ORDER BY created_at DESC LIMIT 50;"
```

---

## Anti-patterns
- **Logging `params` that contain PII** — sanitize or redact sensitive bind parameters (emails, tokens) before the `console.log` call.
- **Using `.run()` instead of `.all()` for read queries** — `.run()` does not return `results`, so `rowCount` will always be 0; use `.all()` for SELECTs.
- **Measuring time with `Date.now()`** — `performance.now()` has sub-millisecond resolution; `Date.now()` rounds to 1 ms and cannot distinguish fast queries.
- **Logging every query in production at high RPS** — at thousands of requests per second, structured logs can hit the 128 KB log limit per invocation; add a sampling flag (`LOG_QUERIES=1` env var) to toggle tracing.

---

## Gotchas
- `performance.now()` in Workers is clamped to 0.1 ms precision for security; sub-0.1 ms measurements will always read as 0.
- `wrangler tail` only streams logs from the single closest data center at the time of connection; deploy a Tail Worker for global coverage.
- D1 is a globally distributed SQLite; latency from a Worker to D1 depends on which location the request hit. Log the `CF-Ray` header alongside query traces to correlate colocation.
- Errors thrown by `.all()` include the SQLite error code in the message string; parse it with a regex if you want to categorize errors (e.g., `SQLITE_CONSTRAINT`).

---

## Verification

```bash
# Deploy the Worker
wrangler deploy

# In terminal 1: start the tail stream
wrangler tail d1-trace-worker --format json 2>/dev/null | \
  jq '.logs[]?.message[]? | select(type=="string") | try fromjson | select(.level=="query")'

# In terminal 2: trigger a query
curl https://d1-trace-worker.example.workers.dev/users

# Expected output in terminal 1:
# {
#   "level": "query",
#   "query": "SELECT id, email, created_at FROM users ORDER BY created_at DESC LIMIT 50",
#   "params": [],
#   "durationMs": 12.4,
#   "rowCount": 23,
#   "success": true
# }
```

---

## Related
- `workers-opentelemetry-trace-export-d1.md`
- `workers-uptime-cron-d1-alert-queue.md`

---

## Sources
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Workers Runtime: performance.now() — https://developers.cloudflare.com/workers/runtime-apis/performance/
- wrangler tail reference — https://developers.cloudflare.com/workers/wrangler/commands/#tail
