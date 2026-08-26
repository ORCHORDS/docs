# D1 Schema Drift Detection and Validation in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
After several rapid deploys the live D1 database schema no longer matches what your TypeScript code and migration files expect, causing silent runtime errors, missing columns, or stale indexes. You need automated drift detection that runs on deploy or on a schedule and alerts before data integrity is compromised.

## Context
Unlike traditional databases, D1 is schema-on-write: there is no external schema registry enforcing structure at the engine level beyond what your migration files create. Wrangler applies migrations idempotently via `d1_migrations`, but manual fixes, aborted migrations, or environment-specific patches can leave the live schema in a state that diverges from source control. SQLite's `sqlite_master` and `PRAGMA table_info()` expose the full schema at runtime, making it possible to build a lightweight drift detector entirely in Workers TypeScript.

## Extracting the Live Schema

```typescript
// src/schema/introspect.ts
export interface ColumnDef {
  cid:       number;
  name:      string;
  type:      string;
  notnull:   number;
  dflt_value: string | null;
  pk:        number;
}

export interface IndexInfo {
  name:    string;
  unique:  number;
  origin:  string;
  partial: number;
}

export interface LiveSchema {
  tables:  Record<string, ColumnDef[]>;
  indexes: Record<string, IndexInfo & { columns: string[] }>;
}

export async function introspectSchema(db: D1Database): Promise<LiveSchema> {
  // Get all user-created tables (exclude sqlite_ internals and d1_ migration tables)
  const { results: tableRows } = await db.prepare(
    `SELECT name FROM sqlite_master
     WHERE type = 'table'
       AND name NOT LIKE 'sqlite_%'
       AND name NOT LIKE '_cf_%'
       AND name NOT LIKE 'd1_%'
     ORDER BY name`
  ).all<{ name: string }>();

  const tables: Record<string, ColumnDef[]> = {};
  const indexes: Record<string, IndexInfo & { columns: string[] }> = {};

  for (const { name } of tableRows) {
    const { results: cols } = await db.prepare(
      `PRAGMA table_info(?)`
    ).bind(name).all<ColumnDef>();
    tables[name] = cols;

    const { results: idxList } = await db.prepare(
      `PRAGMA index_list(?)`
    ).bind(name).all<IndexInfo>();

    for (const idx of idxList) {
      if (idx.origin === 'pk') continue; // skip implicit rowid index
      const { results: idxCols } = await db.prepare(
        `PRAGMA index_info(?)`
      ).bind(idx.name).all<{ seqno: number; cid: number; name: string }>();
      indexes[idx.name] = { ...idx, columns: idxCols.map((c) => c.name) };
    }
  }

  return { tables, indexes };
}
```

## Defining the Expected Schema

```typescript
// src/schema/expected.ts
// Hand-authored or generated from your migration files at build time
export const EXPECTED_SCHEMA = {
  tables: {
    users: [
      { name: 'id',         type: 'TEXT',    notnull: 1, pk: 1 },
      { name: 'email',      type: 'TEXT',    notnull: 1, pk: 0 },
      { name: 'created_at', type: 'INTEGER', notnull: 1, pk: 0 },
    ],
    posts: [
      { name: 'id',         type: 'TEXT',    notnull: 1, pk: 1 },
      { name: 'user_id',    type: 'TEXT',    notnull: 1, pk: 0 },
      { name: 'title',      type: 'TEXT',    notnull: 1, pk: 0 },
      { name: 'body',       type: 'TEXT',    notnull: 0, pk: 0 },
      { name: 'created_at', type: 'INTEGER', notnull: 1, pk: 0 },
    ],
  },
  requiredIndexes: [
    'idx_posts_user_id',
    'idx_users_email',
  ],
} as const;
```

## Diffing Live vs Expected

```typescript
// src/schema/drift.ts
import { LiveSchema, introspectSchema } from './introspect';
import { EXPECTED_SCHEMA } from './expected';

export interface DriftReport {
  missingTables:   string[];
  extraTables:     string[];
  columnDrifts:    Array<{ table: string; column: string; issue: string }>;
  missingIndexes:  string[];
  clean:           boolean;
}

export async function detectDrift(db: D1Database): Promise<DriftReport> {
  const live = await introspectSchema(db);
  const report: DriftReport = {
    missingTables:  [],
    extraTables:    [],
    columnDrifts:   [],
    missingIndexes: [],
    clean:          false,
  };

  // Missing tables
  for (const table of Object.keys(EXPECTED_SCHEMA.tables)) {
    if (!live.tables[table]) report.missingTables.push(table);
  }

  // Per-table column drift
  for (const [table, expectedCols] of Object.entries(EXPECTED_SCHEMA.tables)) {
    const liveCols = live.tables[table] ?? [];
    const liveColMap = Object.fromEntries(liveCols.map((c) => [c.name, c]));

    for (const exp of expectedCols) {
      const liveCol = liveColMap[exp.name];
      if (!liveCol) {
        report.columnDrifts.push({ table, column: exp.name, issue: 'missing' });
        continue;
      }
      if (liveCol.type.toUpperCase() !== exp.type.toUpperCase()) {
        report.columnDrifts.push({
          table, column: exp.name,
          issue: `type mismatch: expected ${exp.type}, got ${liveCol.type}`,
        });
      }
      if (liveCol.notnull !== exp.notnull) {
        report.columnDrifts.push({
          table, column: exp.name,
          issue: `NOT NULL mismatch: expected ${exp.notnull}, got ${liveCol.notnull}`,
        });
      }
    }
  }

  // Missing indexes
  for (const idx of EXPECTED_SCHEMA.requiredIndexes) {
    if (!live.indexes[idx]) report.missingIndexes.push(idx);
  }

  report.clean =
    report.missingTables.length  === 0 &&
    report.columnDrifts.length   === 0 &&
    report.missingIndexes.length === 0;

  return report;
}
```

## Surfacing Drift via a Health Endpoint

```typescript
// src/routes/health.ts
import { detectDrift } from '../schema/drift';

export async function handleHealthCheck(
  request: Request,
  env: { DB: D1Database; SCHEMA_CHECK_SECRET: string },
): Promise<Response> {
  const secret = new URL(request.url).searchParams.get('secret');
  if (secret !== env.SCHEMA_CHECK_SECRET) {
    return new Response('Forbidden', { status: 403 });
  }

  const report = await detectDrift(env.DB);
  const status = report.clean ? 200 : 500;

  return new Response(JSON.stringify(report, null, 2), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Automated Alerts via Cron Trigger

```typescript
// src/scheduled.ts
import { detectDrift } from './schema/drift';

export async function handleScheduled(
  _event: ScheduledEvent,
  env: { DB: D1Database; ALERT_WEBHOOK_URL: string },
): Promise<void> {
  const report = await detectDrift(env.DB);
  if (report.clean) return;

  await fetch(env.ALERT_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `*D1 Schema Drift Detected*\n` +
        `Missing tables: ${report.missingTables.join(', ') || 'none'}\n` +
        `Column issues: ${report.columnDrifts.length}\n` +
        `Missing indexes: ${report.missingIndexes.join(', ') || 'none'}`,
      report,
    }),
  });
}
```

## Anti-patterns
- Comparing raw `CREATE TABLE` DDL strings — whitespace and ordering differences cause false positives; compare parsed column metadata instead
- Running drift detection on every inbound request — the `PRAGMA table_info` loop adds ~5–20 ms per table; restrict to a dedicated health endpoint or scheduled job
- Blocking deploys solely on extra tables — additive schema drift (new columns, new tables) is usually safe; alert on destructive or type-mismatch drift only
- Hardcoding the expected schema as a large constant — generate it programmatically from your migration SQL files during the build step for a single source of truth

## Gotchas
- `PRAGMA table_info(?)` with a bound parameter works in D1; some older SQLite versions require string interpolation — test in a local `wrangler dev` session first
- D1's `sqlite_master` may not reflect indexes created by another session until the next read transaction begins; always introspect within a fresh Worker request
- `PRAGMA index_list` returns implicit `pk`-origin indexes for `WITHOUT ROWID` tables; filter these out to avoid false "extra index" reports
- Schema changes made outside Wrangler migrations (e.g., via the D1 console) do not update `_cf_KV`; the Wrangler migration table tracks only what Wrangler applied

## Verification

```bash
# Run introspection locally
wrangler d1 execute MY_DB --local --command \
  "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name;"

wrangler d1 execute MY_DB --local --command \
  "PRAGMA table_info(users);"

# Simulate drift: drop a column (not possible in SQLite directly; use a test DB instead)
wrangler d1 execute MY_DB --local --command \
  "CREATE TABLE users_bak AS SELECT id, created_at FROM users;"
# Then re-run drift detection and confirm the email column is flagged as missing
```

## Related
- [d1-migrations-wrangler-ci-cd.md](d1-migrations-wrangler-ci-cd.md)
- [d1-schema-versioning-wrangler-migrations.md](d1-schema-versioning-wrangler-migrations.md)
- [sqlite-schema-introspection-automation.md](sqlite-schema-introspection-automation.md)
- [backward-compatible-migrations.md](backward-compatible-migrations.md)

## Sources
- SQLite sqlite_master table: https://www.sqlite.org/schematab.html
- SQLite PRAGMA table_info: https://www.sqlite.org/pragma.html#pragma_table_info
- Cloudflare D1 migrations: https://developers.cloudflare.com/d1/reference/migrations/
