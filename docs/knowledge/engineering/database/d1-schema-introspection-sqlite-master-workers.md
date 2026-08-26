# D1 Schema Introspection sqlite_master Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker needs to verify that expected tables, columns, or indexes exist before running migrations, to guard against schema drift, or to generate dynamic queries at runtime without hard-coding column lists. The application must discover schema structure programmatically at request or boot time without access to external metadata stores.

## Context

SQLite exposes every DDL object (tables, indexes, views, triggers) in the read-only system table `sqlite_schema` (alias `sqlite_master` for backwards compatibility). Each row stores the object `type`, `name`, `tbl_name`, `rootpage`, and the original `sql` DDL string. D1 Workers can query `sqlite_schema` the same way they query user tables — via `db.prepare('SELECT … FROM sqlite_schema').all()`. The `PRAGMA table_info(table_name)` and `PRAGMA index_list(table_name)` commands return column and index metadata respectively. These are read-only catalog queries and do not count against D1 write limits.

## Listing Tables and Views

Query `sqlite_schema` to enumerate all user-created objects:

```typescript
// src/db/introspect.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface SchemaObject {
  type: 'table' | 'index' | 'view' | 'trigger';
  name: string;
  tbl_name: string;
  sql: string | null;
}

/**
 * Return all user-defined tables in the database.
 * Excludes SQLite internal shadow tables (prefixed with 'sqlite_')
 * and FTS5 shadow tables (suffixed with '_data', '_idx', etc.).
 */
export async function listTables(db: D1Database): Promise<string[]> {
  const { results } = await db
    .prepare(
      `SELECT name
       FROM sqlite_schema
       WHERE type = 'table'
         AND name NOT LIKE 'sqlite_%'
         AND name NOT LIKE '%_fts_%'
         AND name NOT LIKE '%_config'
         AND name NOT LIKE '%_content'
         AND name NOT LIKE '%_docsize'
         AND name NOT LIKE '%_data'
         AND name NOT LIKE '%_idx'
         AND name NOT LIKE '%_segdir'
         AND name NOT LIKE '%_segments'
       ORDER BY name`
    )
    .all<{ name: string }>();

  return results.map((r) => r.name);
}

/**
 * Return the DDL SQL string for any named object.
 * Returns null if the object does not exist.
 */
export async function getDDL(
  db: D1Database,
  objectName: string
): Promise<string | null> {
  const row = await db
    .prepare(
      `SELECT sql FROM sqlite_schema WHERE name = ? AND type IN ('table','view','index')`
    )
    .bind(objectName)
    .first<{ sql: string | null }>();

  return row?.sql ?? null;
}

/**
 * Check whether a specific table exists.
 */
export async function tableExists(db: D1Database, tableName: string): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ? LIMIT 1`
    )
    .bind(tableName)
    .first<{ 1: number }>();

  return row !== null;
}
```

## Column Introspection with PRAGMA table_info

`PRAGMA table_info(table)` returns one row per column with name, type, nullability, default value, and primary key position:

```typescript
// src/db/introspect.ts (continued)

export interface ColumnInfo {
  cid: number;          // column index (0-based)
  name: string;
  type: string;         // declared affinity ('TEXT', 'INTEGER', etc.)
  notnull: 0 | 1;
  dflt_value: string | null;
  pk: number;           // 0 = not PK, 1+ = PK column position
}

/**
 * Return column metadata for a table.
 * Uses PRAGMA table_info — safe for use inside a D1 Worker.
 */
export async function getColumnInfo(
  db: D1Database,
  tableName: string
): Promise<ColumnInfo[]> {
  // PRAGMA cannot use bound parameters — sanitise the table name
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(tableName)) {
    throw new TypeError(`Unsafe table name: ${tableName}`);
  }

  const { results } = await db
    .prepare(`PRAGMA table_info(${tableName})`)
    .all<ColumnInfo>();

  return results;
}

/**
 * Check whether a specific column exists in a table.
 */
export async function columnExists(
  db: D1Database,
  tableName: string,
  columnName: string
): Promise<boolean> {
  const cols = await getColumnInfo(db, tableName);
  return cols.some((c) => c.name === columnName);
}

/**
 * Return column names as a string array — useful for dynamic SELECT generation.
 */
export async function columnNames(
  db: D1Database,
  tableName: string
): Promise<string[]> {
  const cols = await getColumnInfo(db, tableName);
  return cols.map((c) => c.name);
}
```

## Index Introspection with PRAGMA index_list

Discover which indexes exist and whether they are unique:

```typescript
// src/db/introspect.ts (continued)

export interface IndexEntry {
  seq: number;
  name: string;
  unique: 0 | 1;
  origin: 'c' | 'u' | 'pk'; // c=CREATE INDEX, u=UNIQUE constraint, pk=PRIMARY KEY
  partial: 0 | 1;            // 1 if the index has a WHERE clause (partial index)
}

export interface IndexColumn {
  seqno: number;
  cid: number;          // -1 for expression indexes
  name: string | null;  // null for rowid column
}

export async function getIndexList(
  db: D1Database,
  tableName: string
): Promise<IndexEntry[]> {
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(tableName)) {
    throw new TypeError(`Unsafe table name: ${tableName}`);
  }

  const { results } = await db
    .prepare(`PRAGMA index_list(${tableName})`)
    .all<IndexEntry>();

  return results;
}

export async function getIndexColumns(
  db: D1Database,
  indexName: string
): Promise<IndexColumn[]> {
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(indexName)) {
    throw new TypeError(`Unsafe index name: ${indexName}`);
  }

  const { results } = await db
    .prepare(`PRAGMA index_info(${indexName})`)
    .all<IndexColumn>();

  return results;
}

/**
 * Check whether a covering index exists for a set of columns on a table.
 */
export async function coveringIndexExists(
  db: D1Database,
  tableName: string,
  columns: string[]
): Promise<boolean> {
  const indexes = await getIndexList(db, tableName);

  for (const idx of indexes) {
    const idxCols = await getIndexColumns(db, idx.name);
    const idxColNames = idxCols
      .filter((c) => c.name !== null)
      .map((c) => c.name as string);

    // The index covers the requested columns if its prefix matches
    const matches = columns.every((col, i) => idxColNames[i] === col);
    if (matches) return true;
  }

  return false;
}
```

## Boot-Time Schema Validation

Validate required tables and columns exist when the Worker starts (useful for catching deployment errors):

```typescript
// src/startup/schema-check.ts
import { tableExists, columnExists, getIndexList } from '../db/introspect';
import type { D1Database } from '@cloudflare/workers-types';

interface RequiredColumn {
  table: string;
  column: string;
}

const REQUIRED_TABLES = ['users', 'posts', 'tenants', 'audit_events'];

const REQUIRED_COLUMNS: RequiredColumn[] = [
  { table: 'users',    column: 'tenant_id' },
  { table: 'posts',    column: 'tenant_id' },
  { table: 'posts',    column: 'deleted_at' },
  { table: 'tenants',  column: 'settings' },
];

/**
 * Run at Worker fetch() entry point before handling requests.
 * Throws on first schema mismatch so the Worker returns 500 instead
 * of a misleading SQL error on the first real query.
 */
export async function validateSchema(db: D1Database): Promise<void> {
  for (const table of REQUIRED_TABLES) {
    if (!(await tableExists(db, table))) {
      throw new Error(`Schema validation failed: table '${table}' not found`);
    }
  }

  for (const { table, column } of REQUIRED_COLUMNS) {
    if (!(await columnExists(db, table, column))) {
      throw new Error(
        `Schema validation failed: column '${table}.${column}' not found`
      );
    }
  }
}

// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Lightweight: sqlite_schema and PRAGMA queries are fast catalog reads
    await validateSchema(env.DB);
    // … route handling
    return new Response('ok');
  },
};
```

## Dynamic Column Projection

Build a SELECT statement from discovered columns, useful for export endpoints or admin tooling:

```typescript
// src/admin/export.ts

/**
 * Export all rows of a table with columns discovered at runtime.
 * Excludes columns the caller does not want to expose (e.g. internal flags).
 */
export async function exportTable(
  db: D1Database,
  tableName: string,
  excludeColumns: string[] = []
): Promise<Record<string, unknown>[]> {
  // Safe table name already validated by caller
  const allCols = await columnNames(db, tableName);
  const exportCols = allCols.filter((c) => !excludeColumns.includes(c));

  if (exportCols.length === 0) throw new Error('No columns to export');

  // Column names are derived from PRAGMA table_info — safe to interpolate
  const colList = exportCols.map((c) => `"${c}"`).join(', ');

  const { results } = await db
    .prepare(`SELECT ${colList} FROM "${tableName}" ORDER BY rowid`)
    .all<Record<string, unknown>>();

  return results;
}
```

## Anti-patterns

- Querying `sqlite_schema` by parsing the `sql` DDL string with regular expressions to find column names — use `PRAGMA table_info` instead; the DDL string format is not guaranteed to remain stable.
- Interpolating user-supplied table or index names into PRAGMA statements without a strict alphanumeric allowlist — PRAGMA does not accept bound parameters, making it the one SQLite interface that must be sanitised manually.
- Running schema introspection on every request in a hot path — cache results in the Worker module scope (a `Map` initialized once per isolate) since schema rarely changes between deploys.
- Using `sqlite_master` instead of `sqlite_schema` — both names work, but `sqlite_schema` is the canonical name since SQLite 3.33.0; `sqlite_master` is a deprecated alias.
- Assuming `PRAGMA table_info` returns columns in declaration order — it does in practice, but `cid` (column index) is the authoritative ordering field; sort by `cid` if order matters.

## Gotchas

- FTS5 creates several internal shadow tables (`_data`, `_idx`, `_content`, `_docsize`, `_config`) that appear in `sqlite_schema`. Filter them out with `name NOT LIKE '%_config'` etc., or filter by checking that `tbl_name = name` (only user tables satisfy this).
- D1's `PRAGMA table_info` includes generated (virtual) columns but marks them with a special `type` value; filter by checking `cid >= 0` and be aware generated columns cannot be written to directly.
- `PRAGMA table_info` does not expose CHECK constraint expressions — to inspect constraints, parse the `sql` DDL from `sqlite_schema` or query `PRAGMA table_info` alongside `PRAGMA table_xinfo` (extended info, available in SQLite 3.37+).
- `sqlite_schema` rows have `sql = NULL` for the implicit `sqlite_autoindex_*` indexes created by UNIQUE and PRIMARY KEY constraints — these still appear in `PRAGMA index_list` but have no DDL string.
- Schema queries inside a D1 Worker share the same read snapshot as user queries. If a migration just ran and changed the schema, the Worker isolate that ran the migration sees the new schema; other isolates see the new schema after their next isolate restart or a fresh connection.

## Verification

```typescript
// tests/introspect.test.ts
import { env } from 'cloudflare:test';
import { tableExists, columnExists, getColumnInfo, getIndexList } from '../src/db/introspect';

describe('schema introspection', () => {
  beforeAll(async () => {
    await env.DB.exec(`
      CREATE TABLE IF NOT EXISTS sample (
        id      TEXT PRIMARY KEY,
        name    TEXT NOT NULL,
        value   INTEGER
      );
      CREATE INDEX IF NOT EXISTS idx_sample_name ON sample(name);
    `);
  });

  it('detects existing table', async () => {
    expect(await tableExists(env.DB, 'sample')).toBe(true);
  });

  it('returns false for nonexistent table', async () => {
    expect(await tableExists(env.DB, 'ghost_table')).toBe(false);
  });

  it('lists columns via table_info', async () => {
    const cols = await getColumnInfo(env.DB, 'sample');
    expect(cols.map((c) => c.name)).toEqual(['id', 'name', 'value']);
  });

  it('detects existing column', async () => {
    expect(await columnExists(env.DB, 'sample', 'name')).toBe(true);
    expect(await columnExists(env.DB, 'sample', 'nonexistent')).toBe(false);
  });

  it('lists indexes via index_list', async () => {
    const indexes = await getIndexList(env.DB, 'sample');
    expect(indexes.some((i) => i.name === 'idx_sample_name')).toBe(true);
  });
});
```

```bash
# Inspect live D1 schema via wrangler
wrangler d1 execute MY_DB --command \
  "SELECT name, type FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"

wrangler d1 execute MY_DB --command "PRAGMA table_info(users)"
wrangler d1 execute MY_DB --command "PRAGMA index_list(users)"
```

## Related

- `database/d1-schema-drift-detection-validation.md` — detecting schema drift between environments
- `database/d1-schema-versioning-wrangler-migrations.md` — version-controlled migrations
- `database/d1-generated-columns-virtual-workers.md` — virtual columns visible in PRAGMA table_info
- `database/d1-expression-index-function-based-workers.md` — expression indexes in sqlite_schema
- `database/sqlite-schema-introspection-automation.md` — generic SQLite introspection patterns

## Sources

- https://www.sqlite.org/schematab.html
- https://www.sqlite.org/pragma.html#pragma_table_info
- https://www.sqlite.org/pragma.html#pragma_index_list
- https://developers.cloudflare.com/d1/worker-api/d1-database/
