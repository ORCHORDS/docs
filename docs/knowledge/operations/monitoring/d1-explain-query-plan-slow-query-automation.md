# D1 Slow Query Detection and EXPLAIN QUERY PLAN Automation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

D1 queries that took 4 ms in development exceed 400 ms in production
under realistic row counts and concurrent requests. The Cloudflare
dashboard shows p99 Worker CPU time but does not expose per-statement
D1 execution time. Without systematic slow query detection, regressions
land silently: a new index is dropped during a migration, a query plan
switches from `SEARCH` to `SCAN`, and the performance hit only surfaces
three days later in a customer complaint.

The team needs:
- Automatic capture of every D1 statement that exceeds a latency budget.
- A machine-readable query plan (`EXPLAIN QUERY PLAN`) for each slow
  statement, stored without blocking the hot path.
- A weekly roll-up in Analytics Engine so trends are visible before they
  become incidents.

---

## Context

D1 is Cloudflare's managed SQLite-at-the-edge database. SQLite's query
planner is deterministic for a given schema and index set, which means
`EXPLAIN QUERY PLAN` output does not change between runs for the same
statement shape. This makes plan capture cheap: run it once when a slow
query is first detected, cache the result in KV, and only re-run when
the statement fingerprint changes.

D1 does not expose `pg_stat_statements` or a native slow-query log.
Detection must happen inside the Worker:

1. Wrap every `db.prepare(...).all()` / `.run()` / `.first()` call with
   a thin timing shim.
2. If elapsed time exceeds the threshold (default: 100 ms), emit a D1
   statement to a `slow_queries` table (in a separate D1 database used
   for observability) AND schedule an async `EXPLAIN QUERY PLAN` via
   `ctx.waitUntil`.
3. An Analytics Engine data point records the anomaly for trend queries.

Mobile clients issue more concurrent read-heavy requests than desktop
sessions (playlist hydration, library sync), so the slow query budget
is split: 80 ms for read queries originating from mobile user-agents,
120 ms for desktop, and 200 ms for background jobs.

---

## Section 1: Timing Shim

```typescript
// src/lib/d1-traced.ts
export interface SlowQueryRecord {
  statement: string;
  fingerprint: string;      // SHA-256 of normalised statement
  elapsed_ms: number;
  device_type: "mobile" | "desktop" | "bot" | "unknown";
  route: string;
  timestamp: number;
}

function normalise(sql: string): string {
  // collapse literal values so plans are grouped by statement shape
  return sql
    .replace(/\b\d+\b/g, "?")
    .replace(/'[^']*'/g, "?")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

async function sha256hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function tracedQuery<T>(
  stmt: D1PreparedStatement,
  method: "all" | "run" | "first",
  ctx: ExecutionContext,
  env: Env,
  meta: { sql: string; route: string; deviceType: SlowQueryRecord["device_type"] },
): Promise<T> {
  const start = Date.now();
  const result = await (stmt[method] as () => Promise<T>)();
  const elapsed = Date.now() - start;

  const threshold =
    meta.deviceType === "mobile" ? 80 :
    meta.deviceType === "desktop" ? 120 : 200;

  if (elapsed > threshold) {
    const normalised = normalise(meta.sql);
    const fingerprint = await sha256hex(normalised);

    ctx.waitUntil(
      captureSlowQuery(
        { statement: meta.sql, fingerprint, elapsed_ms: elapsed,
          device_type: meta.deviceType, route: meta.route,
          timestamp: Date.now() },
        env,
      ),
    );
  }

  return result;
}
```

---

## Section 2: Slow Query Capture and EXPLAIN QUERY PLAN

```typescript
// src/lib/slow-query-capture.ts
import type { SlowQueryRecord } from "./d1-traced";

export async function captureSlowQuery(
  record: SlowQueryRecord,
  env: Env,
): Promise<void> {
  // 1. Write to observability D1 database
  await env.OBS_DB.prepare(`
    INSERT OR IGNORE INTO slow_queries
      (fingerprint, statement, elapsed_ms, device_type, route, captured_at)
    VALUES (?, ?, ?, ?, ?, ?)
  `).bind(
    record.fingerprint,
    record.statement,
    record.elapsed_ms,
    record.device_type,
    record.route,
    new Date(record.timestamp).toISOString(),
  ).run();

  // 2. Only run EXPLAIN QUERY PLAN if plan not already cached in KV
  const kvKey = `explain:${record.fingerprint}`;
  const cached = await env.SLOW_QUERY_KV.get(kvKey);

  if (!cached) {
    try {
      const plan = await env.APP_DB.prepare(
        `EXPLAIN QUERY PLAN ${record.statement}`,
      ).all();

      const planJson = JSON.stringify(plan.results);

      // Cache for 24 h — plan only changes when schema/indexes change
      await env.SLOW_QUERY_KV.put(kvKey, planJson, { expirationTtl: 86400 });

      // Store plan alongside the slow query record
      await env.OBS_DB.prepare(`
        UPDATE slow_queries SET explain_plan = ? WHERE fingerprint = ?
      `).bind(planJson, record.fingerprint).run();
    } catch {
      // EXPLAIN failures must never surface to users — swallow silently
    }
  }

  // 3. Emit to Analytics Engine for trend monitoring
  env.AE_SLOW_QUERIES.writeDataPoint({
    blobs: [
      record.fingerprint,
      record.statement.slice(0, 128),
      record.route,
      record.device_type,
    ],
    doubles: [record.elapsed_ms],
    indexes: [record.device_type],
  });
}
```

---

## Section 3: Observability Database Schema and wrangler.toml

```sql
-- migrations/0001_slow_queries.sql  (runs against OBS_DB)
CREATE TABLE IF NOT EXISTS slow_queries (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint   TEXT    NOT NULL UNIQUE,
  statement     TEXT    NOT NULL,
  elapsed_ms    INTEGER NOT NULL,
  device_type   TEXT    NOT NULL DEFAULT 'unknown',
  route         TEXT    NOT NULL DEFAULT '',
  captured_at   TEXT    NOT NULL,
  explain_plan  TEXT,
  hit_count     INTEGER NOT NULL DEFAULT 1,
  last_seen_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_slow_device ON slow_queries (device_type);
CREATE INDEX IF NOT EXISTS idx_slow_elapsed ON slow_queries (elapsed_ms DESC);
```

```toml
# wrangler.toml
name = "example project-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[d1_databases]]
binding = "APP_DB"
database_name = "example project-production"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[d1_databases]]
binding = "OBS_DB"
database_name = "example project-observability"
database_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"

[[kv_namespaces]]
binding = "SLOW_QUERY_KV"
id = "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"

[[analytics_engine_datasets]]
binding = "AE_SLOW_QUERIES"
dataset = "slow_queries"
```

---

## Section 4: Automated Weekly Plan Audit via Cron Trigger

A second Worker runs weekly and checks whether any cached EXPLAIN plan
contains a full-table `SCAN` and alerts if a previously-indexed query
has regressed.

```typescript
// src/plan-auditor.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const rows = await env.OBS_DB.prepare(`
      SELECT fingerprint, statement, explain_plan, device_type,
             AVG(elapsed_ms) as avg_ms, MAX(elapsed_ms) as max_ms
      FROM   slow_queries
      WHERE  captured_at > datetime('now', '-7 days')
        AND  explain_plan IS NOT NULL
      GROUP  BY fingerprint
      ORDER  BY avg_ms DESC
      LIMIT  50
    `).all<{
      fingerprint: string;
      statement: string;
      explain_plan: string;
      device_type: string;
      avg_ms: number;
      max_ms: number;
    }>();

    const regressions: string[] = [];

    for (const row of rows.results) {
      const plan: Array<{ detail: string }> = JSON.parse(row.explain_plan);
      const hasFullScan = plan.some(
        (p) => p.detail?.toUpperCase().includes("SCAN") &&
               !p.detail.toUpperCase().includes("COVERING"),
      );

      if (hasFullScan) {
        regressions.push(
          `[${row.device_type.toUpperCase()}] ${row.statement.slice(0, 80)} — ` +
          `avg ${row.avg_ms.toFixed(0)} ms / max ${row.max_ms} ms — FULL SCAN`,
        );
      }
    }

    if (regressions.length > 0) {
      await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `*D1 slow query audit — ${regressions.length} full-scan regression(s)*\n` +
                regressions.map((r) => `• ${r}`).join("\n"),
        }),
      });
    }
  },
};
```

```toml
# wrangler.toml addition for the auditor
[triggers]
crons = ["0 9 * * MON"]   # 09:00 UTC every Monday
```

---

## Anti-patterns

- **Running EXPLAIN QUERY PLAN on the hot path** — always defer to
  `ctx.waitUntil`. Even a cached KV read adds latency in p99 tail.
- **Using the production APP_DB for the slow_queries table** — writes
  to a busy table during a slow-query event can cause lock contention.
  A separate OBS_DB database avoids interference.
- **Alerting on every slow query event** — the capture is idempotent by
  fingerprint (`INSERT OR IGNORE`). Alert on weekly trends, not per-event.
- **Logging full SQL statements containing PII** — normalise before
  logging. The `normalise()` function collapses literals; do not store
  the raw statement if it contains user IDs or tokens.

---

## Gotchas

- `EXPLAIN QUERY PLAN` in SQLite (and D1) returns a list of rows with
  `id`, `parent`, `notused`, and `detail` columns. Parse `detail` for
  `SCAN` vs `SEARCH` to detect index usage.
- D1's `EXPLAIN QUERY PLAN` does **not** execute the query — it is safe
  to run on production, unlike PostgreSQL's `EXPLAIN ANALYZE`.
- KV `expirationTtl` of 86400 means a plan is re-captured after an
  index migration within 24 hours. For faster plan refresh after a
  deployment, delete the KV key explicitly in a post-deploy hook.
- The Analytics Engine `indexes` field is used for high-cardinality
  grouping (here: `device_type`). Limit unique index values to control
  sampling costs.
- D1 has a 50 ms CPU time limit per Worker invocation by default. The
  `OBS_DB` write inside `captureSlowQuery` must be inside `waitUntil`
  — otherwise it will count against the invoking request's CPU budget.

---

## Verification

```bash
# Apply the observability schema
wrangler d1 execute example project-observability \
  --file migrations/0001_slow_queries.sql \
  --remote

# Confirm slow_queries table exists
wrangler d1 execute example project-observability \
  --command "SELECT name FROM sqlite_master WHERE type='table';" \
  --remote

# Simulate a slow query write (local dev)
wrangler dev --local
# In another shell, curl a route known to run a heavy query
# then check:
wrangler d1 execute example project-observability \
  --command "SELECT fingerprint, elapsed_ms, explain_plan FROM slow_queries LIMIT 5;" \
  --remote

# Query Analytics Engine for last-7-days mobile slow query trend
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT blob4 AS device_type, avg(double1) AS avg_ms, count() AS n
      FROM slow_queries
      WHERE timestamp > now() - INTERVAL '7' DAY
      GROUP BY device_type
      ORDER BY avg_ms DESC"
```

---

## Related

- `database-query-monitoring.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `distributed-tracing-workers-d1-requests.md`
- `slo-error-budget-workers-pages.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- SQLite EXPLAIN QUERY PLAN — https://www.sqlite.org/eqp.html
- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare KV documentation — https://developers.cloudflare.com/kv/
