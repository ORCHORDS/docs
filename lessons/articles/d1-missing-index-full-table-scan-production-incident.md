# D1 Missing Index Causing Full Table Scan in Production

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

The `/api/sessions/active` endpoint, called on every page load, began timing out for ~12% of requests during peak hours. D1 query duration p99 jumped from 35 ms to 4.8 s. The Worker CPU wall-clock limit (5 s) started returning HTTP 524s. No code change had been deployed; the table had grown past 3 M rows overnight.

## Context

The `sessions` table stores user session records keyed by `user_id`. A schema migration two sprints prior renamed the column from `uid` to `user_id`. The developer updated the SELECT query but did not notice the existing index was on the old `uid` column. D1 silently continued to function — the query returned correct rows — but used a full table scan on every request because no index on `user_id` existed.

---

## Root Cause: Index Was on Renamed Column, New Column Had No Index

```sql
-- Schema state after migration (incorrect)
CREATE TABLE sessions (
  id       TEXT PRIMARY KEY,
  user_id  TEXT NOT NULL,          -- renamed from uid
  token    TEXT NOT NULL,
  expires  INTEGER NOT NULL
);

-- Index still references old column name (no longer effective)
CREATE INDEX idx_sessions_uid ON sessions (uid);  -- uid no longer exists → dropped silently

-- Query issued by application
SELECT id, token, expires
  FROM sessions
 WHERE user_id = ?1
   AND expires > unixepoch();
```

SQLite drops an index whose column no longer exists after a column rename via a migration that recreates the table. The index name `idx_sessions_uid` still appears in `sqlite_master` but references a stale schema snapshot in some migration histories. A fresh `EXPLAIN QUERY PLAN` would have caught it immediately.

## Fix Step 1: Add the Correct Index

```sql
-- migrations/0014_fix_sessions_index.sql
CREATE INDEX IF NOT EXISTS idx_sessions_user_id
  ON sessions (user_id, expires);
```

Compound index on `(user_id, expires)` lets SQLite satisfy both filter predicates from the index without reading table rows for expired sessions.

## Fix Step 2: Add a Schema Assertion in the Migration Runner

```typescript
// src/db/migrate.ts
export async function assertIndexExists(
  db: D1Database,
  indexName: string,
  tableName: string,
): Promise<void> {
  const row = await db
    .prepare(
      `SELECT 1 FROM sqlite_master
        WHERE type = 'index'
          AND name = ?1
          AND tbl_name = ?2`,
    )
    .bind(indexName, tableName)
    .first<{ 1: number }>();

  if (!row) {
    throw new Error(
      `Index "${indexName}" on "${tableName}" is missing. ` +
        `Run pending migrations before deploying this Worker version.`,
    );
  }
}

// Called at Worker startup (once, using a module-scope flag)
let checked = false;
export async function assertSchemaReadiness(env: Env): Promise<void> {
  if (checked) return;
  await assertIndexExists(env.DB, "idx_sessions_user_id", "sessions");
  checked = true;
}
```

## Fix Step 3: Integrate Plan Check into CI

```typescript
// tests/db/sessions-query-plan.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { unstable_dev, type UnstableDevWorker } from "wrangler";

let worker: UnstableDevWorker;

beforeAll(async () => {
  worker = await unstable_dev("src/index.ts", {
    experimental: { disableExperimentalWarning: true },
  });
});

afterAll(() => worker.stop());

describe("sessions table query plan", () => {
  it("active-session lookup uses index scan, not table scan", async () => {
    const res = await worker.fetch("/__internal/qplan/sessions-active");
    expect(res.status).toBe(200);

    const body = await res.text();
    expect(body).toMatch(/USING INDEX/i);
    expect(body).not.toMatch(/SCAN sessions/i);
  });
});
```

Expose the internal endpoint only in non-production environments:

```typescript
// src/routes/internal.ts
export async function handleInternalQPlan(
  request: Request,
  env: Env,
): Promise<Response> {
  if (env.ENVIRONMENT === "production") {
    return new Response("Not found", { status: 404 });
  }

  const plan = await env.DB.prepare(
    `EXPLAIN QUERY PLAN
     SELECT id, token, expires
       FROM sessions
      WHERE user_id = 'probe'
        AND expires > 0`,
  ).all();

  return Response.json(plan.results);
}
```

## Fix Step 4: Validate Indexes After Every Column-Rename Migration

Make index validation a mandatory step in the migration checklist:

```typescript
// scripts/validate-indexes.ts  (run via `tsx scripts/validate-indexes.ts`)
import { execSync } from "node:child_process";

const REQUIRED_INDEXES = [
  { index: "idx_sessions_user_id", table: "sessions" },
  { index: "idx_tracks_user_published", table: "tracks" },
  // add new entries here when adding indexes
] as const;

for (const { index, table } of REQUIRED_INDEXES) {
  const result = execSync(
    `wrangler d1 execute DB --env staging --command \
      "SELECT name FROM sqlite_master WHERE type='index' AND name='${index}'"`,
    { encoding: "utf8" },
  );

  if (!result.includes(index)) {
    console.error(`MISSING: index "${index}" on table "${table}"`);
    process.exit(1);
  }
  console.log(`OK: ${index}`);
}
```

## Fix Step 5: Structured Logging for D1 Slow Queries

Use `console.log` with structured data picked up by Workers Tail:

```typescript
// src/lib/d1-slow-query-logger.ts
const SLOW_QUERY_THRESHOLD_MS = 200;

export async function queryWithLogging<T>(
  db: D1Database,
  query: string,
  bindings: unknown[],
  label: string,
): Promise<D1Result<T>> {
  const start = performance.now();
  const stmt = db.prepare(query);
  const result = await stmt.bind(...bindings).all<T>();
  const durationMs = performance.now() - start;

  if (durationMs > SLOW_QUERY_THRESHOLD_MS) {
    console.log(
      JSON.stringify({
        level: "warn",
        event: "slow_d1_query",
        label,
        durationMs: Math.round(durationMs),
        rows: result.results.length,
        queryPrefix: query.slice(0, 120),
      }),
    );
  }

  return result;
}
```

---

## Anti-Patterns

- **Renaming columns without auditing dependent indexes.** SQLite's table-recreation approach to column renames silently invalidates indexes on old column names.
- **Trusting that "it works" means "it is fast."** A missing index returns correct results — it just reads every row to do so.
- **Only checking EXPLAIN QUERY PLAN in development.** Dev databases are small; plans look cheap. Always check plan output against a staging database with production-scale row counts.
- **Not asserting schema state at Worker startup.** A Worker that queries a table without the expected index will silently degrade for all users.

## Gotchas

- `CREATE INDEX IF NOT EXISTS` is safe to run multiple times; it is a no-op if the index already exists.
- SQLite's `EXPLAIN QUERY PLAN` output format changed in SQLite 3.36. D1 uses a recent SQLite version; always test plan parsing against the current D1 SQLite build.
- Compound indexes are left-prefix matched. `(user_id, expires)` satisfies `WHERE user_id = ?`, but `(expires, user_id)` does not.
- D1 imposes a 1 GB database size limit per database (as of 2026). Index storage counts against this limit.

## Verification

1. `EXPLAIN QUERY PLAN` on the active-sessions query shows `USING INDEX idx_sessions_user_id`.
2. D1 query duration p99 for `/api/sessions/active` returns to ≤ 40 ms.
3. HTTP 524 (Worker CPU timeout) errors drop to zero.
4. CI index plan test passes on every PR touching `sessions` table queries or migrations.
5. `scripts/validate-indexes.ts` exits 0 on staging before the fix deploy.

## Related

- `d1-json-column-query-performance-regression-postmortem.md`
- `d1-prepared-statement-plan-cache-invalidation-regression.md`
- `index-before-not-after-performance-problem.md`
- `d1-schema-migration-table-lock-peak-traffic-postmortem.md`

## Sources

- SQLite EXPLAIN QUERY PLAN: https://www.sqlite.org/eqp.html
- SQLite ALTER TABLE (column rename): https://www.sqlite.org/lang_altertable.html
- Cloudflare D1 Indexes: https://developers.cloudflare.com/d1/reference/database-commands/#indexes
- Cloudflare D1 Limits: https://developers.cloudflare.com/d1/platform/limits/
