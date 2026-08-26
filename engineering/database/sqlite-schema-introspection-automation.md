# Schema Introspection and Documentation Automation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your team's D1 / SQLite database schema has grown to 40+ tables. The schema lives
in migration files spread across `migrations/` but the authoritative live structure
drifts from the docs. New engineers spend hours mapping which columns exist, which
indexes are defined, and which foreign keys are active. You want:

- Automated schema documentation generated from the live database.
- A CI check that detects schema drift between migrations and production.
- A structured JSON representation of the schema consumable by code generators.

## Context

SQLite exposes its schema through two mechanisms:

1. **`sqlite_master` / `sqlite_schema`** — a system table that stores the DDL text
   for every object (table, index, trigger, view). `sqlite_schema` is the modern
   alias; both work in D1.
2. **`PRAGMA` statements** — `PRAGMA table_info(tbl)`, `PRAGMA foreign_key_list(tbl)`,
   `PRAGMA index_list(tbl)`, `PRAGMA index_info(idx)` provide structured metadata.

D1 exposes both through its SQL API, so introspection queries run identically in
local Wrangler (`--local`) and production D1.

## Introspection Queries

### List All Tables

```sql
SELECT name, sql
FROM sqlite_master
WHERE type = 'table'
  AND name NOT LIKE 'sqlite_%'   -- exclude internal tables
  AND name NOT LIKE 'd1_%'       -- exclude D1 internal tables
ORDER BY name;
```

### Column Details for a Table

```sql
-- PRAGMA table_info returns one row per column with:
-- cid (column index), name, type, notnull, dflt_value, pk (primary key position)
PRAGMA table_info('users');
```

Result:
```
cid | name       | type    | notnull | dflt_value       | pk
0   | id         | TEXT    | 1       | NULL             | 1
1   | email      | TEXT    | 1       | NULL             | 0
2   | created_at | INTEGER | 1       | (unixepoch())    | 0
```

### Foreign Keys for a Table

```sql
PRAGMA foreign_key_list('orders');
-- Returns: id, seq, table (referenced), from (local col), to (remote col),
--          on_update, on_delete, match
```

### Indexes for a Table

```sql
PRAGMA index_list('users');
-- Returns: seq, name, unique, origin (c=CREATE INDEX, u=UNIQUE, pk=PRIMARY KEY), partial

PRAGMA index_info('idx_users_email');
-- Returns: seqno, cid, name (column name)
```

### Extended Table Info (SQLite 3.37+)

```sql
PRAGMA table_xinfo('users');
-- Same as table_info but includes hidden columns (generated / virtual columns)
-- Extra column: hidden (0=normal, 1=virtual, 2=stored, 3=rowid alias)
```

## Schema Snapshot Worker Script

```typescript
// scripts/schema-snapshot.ts
// Run with: wrangler d1 execute DB --file=schema-snapshot-query.sql
// Or programmatically:

import { D1Database } from '@cloudflare/workers-types';

interface TableInfo {
  name: string;
  sql: string;
  columns: ColumnInfo[];
  indexes: IndexInfo[];
  foreignKeys: ForeignKeyInfo[];
}

interface ColumnInfo {
  cid: number;
  name: string;
  type: string;
  notnull: boolean;
  dflt_value: string | null;
  pk: number;
}

interface IndexInfo {
  name: string;
  unique: boolean;
  columns: string[];
  partial: boolean;
}

interface ForeignKeyInfo {
  id: number;
  table: string;
  from: string;
  to: string;
  on_delete: string;
  on_update: string;
}

interface SchemaSnapshot {
  captured_at: string;
  tables: TableInfo[];
}

export async function captureSchemaSnapshot(db: D1Database): Promise<SchemaSnapshot> {
  // 1. Get all user tables
  const tablesResult = await db
    .prepare(`
      SELECT name, sql
      FROM sqlite_master
      WHERE type = 'table'
        AND name NOT LIKE 'sqlite_%'
        AND name NOT LIKE 'd1_%'
        AND name NOT LIKE '_cf_%'
      ORDER BY name
    `)
    .all<{ name: string; sql: string }>();

  const tables: TableInfo[] = [];

  for (const table of tablesResult.results) {
    // 2. Column info
    const colResult = await db
      .prepare(`PRAGMA table_info('${table.name}')`)
      .all<ColumnInfo>();

    // 3. Index list
    const idxListResult = await db
      .prepare(`PRAGMA index_list('${table.name}')`)
      .all<{ name: string; unique: number; origin: string; partial: number }>();

    const indexes: IndexInfo[] = [];
    for (const idx of idxListResult.results) {
      if (idx.origin === 'pk') continue;  // Skip implicit primary key index
      const idxInfoResult = await db
        .prepare(`PRAGMA index_info('${idx.name}')`)
        .all<{ seqno: number; cid: number; name: string }>();

      indexes.push({
        name: idx.name,
        unique: idx.unique === 1,
        columns: idxInfoResult.results.map((r) => r.name),
        partial: idx.partial === 1,
      });
    }

    // 4. Foreign keys
    const fkResult = await db
      .prepare(`PRAGMA foreign_key_list('${table.name}')`)
      .all<ForeignKeyInfo>();

    tables.push({
      name: table.name,
      sql: table.sql,
      columns: colResult.results,
      indexes,
      foreignKeys: fkResult.results,
    });
  }

  return {
    captured_at: new Date().toISOString(),
    tables,
  };
}
```

## Markdown Documentation Generator

```typescript
// scripts/generate-schema-docs.ts

export function generateMarkdown(snapshot: SchemaSnapshot): string {
  const lines: string[] = [
    `# Database Schema`,
    ``,
    `> Auto-generated on ${snapshot.captured_at}. Do not edit manually.`,
    ``,
    `## Tables`,
    ``,
  ];

  for (const table of snapshot.tables) {
    lines.push(`### \`${table.name}\``, ``);

    // Column table
    lines.push(
      `| Column | Type | Nullable | Default | PK |`,
      `|--------|------|----------|---------|-----|`,
    );
    for (const col of table.columns) {
      lines.push(
        `| \`${col.name}\` | ${col.type} | ${col.notnull ? 'NO' : 'YES'} | ${col.dflt_value ?? '—'} | ${col.pk ? '✓' : ''} |`,
      );
    }
    lines.push(``);

    // Indexes
    if (table.indexes.length > 0) {
      lines.push(`**Indexes:**`, ``);
      for (const idx of table.indexes) {
        const unique = idx.unique ? ' UNIQUE' : '';
        const partial = idx.partial ? ' PARTIAL' : '';
        lines.push(`- \`${idx.name}\`${unique}${partial} on \`(${idx.columns.join(', ')})\``);
      }
      lines.push(``);
    }

    // Foreign keys
    if (table.foreignKeys.length > 0) {
      lines.push(`**Foreign Keys:**`, ``);
      for (const fk of table.foreignKeys) {
        lines.push(
          `- \`${fk.from}\` → \`${fk.table}(${fk.to})\`` +
          ` ON DELETE ${fk.on_delete} ON UPDATE ${fk.on_update}`,
        );
      }
      lines.push(``);
    }
  }

  return lines.join('\n');
}
```

## Schema Drift Detection

Compare the live schema snapshot against the expected schema generated from
migration files. Run this in CI after deploying migrations.

```typescript
// scripts/detect-drift.ts
import { execSync } from 'child_process';
import * as fs from 'fs';

interface DriftReport {
  missingTables: string[];
  extraTables: string[];
  columnDiffs: Array<{
    table: string;
    missing: string[];
    extra: string[];
    typeMismatch: Array<{ column: string; expected: string; actual: string }>;
  }>;
  missingIndexes: string[];
}

/**
 * Compares two schema snapshots and returns a drift report.
 * Pass the baseline (generated from migrations) and the live snapshot.
 */
export function detectDrift(
  baseline: SchemaSnapshot,
  live: SchemaSnapshot,
): DriftReport {
  const report: DriftReport = {
    missingTables: [],
    extraTables: [],
    columnDiffs: [],
    missingIndexes: [],
  };

  const baselineTables = new Map(baseline.tables.map((t) => [t.name, t]));
  const liveTables = new Map(live.tables.map((t) => [t.name, t]));

  // Tables in baseline but not in live
  for (const name of baselineTables.keys()) {
    if (!liveTables.has(name)) report.missingTables.push(name);
  }

  // Tables in live but not in baseline (unexpected tables)
  for (const name of liveTables.keys()) {
    if (!baselineTables.has(name)) report.extraTables.push(name);
  }

  // Column-level diffs for shared tables
  for (const [name, baseTable] of baselineTables) {
    const liveTable = liveTables.get(name);
    if (!liveTable) continue;

    const baseCols = new Map(baseTable.columns.map((c) => [c.name, c]));
    const liveCols = new Map(liveTable.columns.map((c) => [c.name, c]));

    const missing = [...baseCols.keys()].filter((k) => !liveCols.has(k));
    const extra   = [...liveCols.keys()].filter((k) => !baseCols.has(k));
    const typeMismatch = [];

    for (const [col, baseCol] of baseCols) {
      const liveCol = liveCols.get(col);
      if (liveCol && liveCol.type !== baseCol.type) {
        typeMismatch.push({ column: col, expected: baseCol.type, actual: liveCol.type });
      }
    }

    if (missing.length || extra.length || typeMismatch.length) {
      report.columnDiffs.push({ table: name, missing, extra, typeMismatch });
    }

    // Index drift
    const baseIdxNames = new Set(baseTable.indexes.map((i) => i.name));
    const liveIdxNames = new Set(liveTable.indexes.map((i) => i.name));
    for (const idx of baseIdxNames) {
      if (!liveIdxNames.has(idx)) report.missingIndexes.push(`${name}.${idx}`);
    }
  }

  return report;
}

/** Exit code 1 if drift detected — use in CI. */
export function assertNoDrift(report: DriftReport): void {
  const problems = [
    ...report.missingTables.map((t) => `Missing table: ${t}`),
    ...report.extraTables.map((t) => `Unexpected table: ${t}`),
    ...report.missingIndexes.map((i) => `Missing index: ${i}`),
    ...report.columnDiffs.flatMap((d) => [
      ...d.missing.map((c) => `${d.table}: missing column ${c}`),
      ...d.extra.map((c) => `${d.table}: unexpected column ${c}`),
      ...d.typeMismatch.map(
        (m) => `${d.table}.${m.column}: type ${m.actual} (expected ${m.expected})`,
      ),
    ]),
  ];

  if (problems.length > 0) {
    console.error('Schema drift detected:\n' + problems.map((p) => `  - ${p}`).join('\n'));
    process.exit(1);
  }

  console.log('Schema matches baseline. No drift detected.');
}
```

## CI/CD Integration

```yaml
# .github/workflows/schema-check.yml
name: Schema Drift Check

on:
  push:
    branches: [main]
  pull_request:

jobs:
  schema-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Run migrations on local D1
        run: npx wrangler d1 migrations apply DB --local

      - name: Capture local schema snapshot
        run: npx tsx scripts/schema-snapshot.ts --local > /tmp/live-schema.json

      - name: Generate baseline from migration files
        run: npx tsx scripts/build-baseline-snapshot.ts > /tmp/baseline-schema.json

      - name: Compare snapshots
        run: npx tsx scripts/detect-drift.ts /tmp/baseline-schema.json /tmp/live-schema.json
```

## Anti-patterns

- **Relying solely on migration files for schema truth**: Migration files accumulate
  drift when hotfixes are applied directly to production. The live schema is the
  ground truth — introspect it.
- **Parsing DDL SQL strings**: `sqlite_master.sql` stores the original DDL as text.
  Parsing it with regex to extract column names is fragile. Always use `PRAGMA
  table_info` for structured metadata.
- **Checking schema in application startup on every request**: Schema introspection
  runs O(table_count) queries. Cache the snapshot in a KV or Durable Object and
  refresh on deployment, not per request.
- **Comparing raw DDL strings across environments**: Column ordering, whitespace,
  and comment differences make string comparison unreliable. Compare structured
  PRAGMA output instead.

## Gotchas

- `sqlite_master` is named `sqlite_schema` in SQLite 3.37+. Both names work in D1.
  Use `sqlite_master` for broader compatibility.
- D1 internal tables (prefixed `d1_` and `_cf_`) appear in `sqlite_master`. Filter
  them out with `AND name NOT LIKE 'd1_%' AND name NOT LIKE '_cf_%'`.
- `PRAGMA table_info` does not return check constraints or expression-based defaults
  beyond their literal string. Use the `sql` column from `sqlite_master` to inspect
  those.
- Virtual tables (FTS5 shadow tables: `*_data`, `*_idx`, `*_content`) appear as
  separate entries in `sqlite_master`. Filter them with
  `AND type != 'table' OR name NOT LIKE '%_data'` or inspect `type = 'shadow'`
  (SQLite 3.37+).
- Foreign key pragma returns an empty set if foreign keys are disabled. Run
  `PRAGMA foreign_keys = ON` before introspecting FK data.

## Verification

```sql
-- List all tables and their column counts
SELECT
  m.name AS table_name,
  COUNT(ti.name) AS column_count
FROM sqlite_master m,
     pragma_table_info(m.name) ti
WHERE m.type = 'table'
  AND m.name NOT LIKE 'sqlite_%'
  AND m.name NOT LIKE 'd1_%'
GROUP BY m.name
ORDER BY m.name;

-- Find tables with no indexes (potential performance risk)
SELECT m.name
FROM sqlite_master m
WHERE m.type = 'table'
  AND m.name NOT LIKE 'sqlite_%'
  AND NOT EXISTS (
    SELECT 1
    FROM sqlite_master idx
    WHERE idx.type = 'index'
      AND idx.tbl_name = m.name
      AND idx.origin != 'pk'
  )
ORDER BY m.name;

-- Find all foreign keys across all tables
SELECT
  m.name AS table_name,
  fk."from" AS column_name,
  fk."table" AS ref_table,
  fk."to" AS ref_column
FROM sqlite_master m,
     pragma_foreign_key_list(m.name) fk
WHERE m.type = 'table'
  AND m.name NOT LIKE 'sqlite_%'
ORDER BY m.name, fk.id;
```

## Related

- `d1-migrations-wrangler-ci-cd.md` — Wrangler migration workflow
- `d1-schema-versioning-wrangler-migrations.md` — versioning and applying migrations
- `migration-linting-ci.md` — linting migrations for dangerous changes
- `schema-as-code-drizzle-atlas.md` — code-first schema management
- `backward-compatible-migrations.md` — safe schema evolution patterns

## Sources

- SQLite `sqlite_master` documentation: sqlite.org/schematab.html
- SQLite PRAGMA documentation: sqlite.org/pragma.html
- Cloudflare D1 SQL API: developers.cloudflare.com/d1/worker-api/d1-database
