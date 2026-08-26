# D1 Schema Introspection: Generating TypeScript Types from D1 Schema at Build Time

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You write SQL migrations for a D1 database and separately write TypeScript interfaces that
mirror the table structure. Whenever a column is added, renamed, or its type changes in
a migration, the TypeScript types drift silently — the build passes, the types are wrong,
and bugs surface at runtime. You want a single source of truth: the migration files drive
both the D1 schema and the generated TypeScript types, enforced at build time.

---

## Context

D1 is SQLite. SQLite exposes its schema through the `sqlite_master` table (also accessible
as `sqlite_schema`). The `PRAGMA table_info(table_name)` command returns column metadata:
name, type, nullability, and default value. These two mechanisms let a build-time script
introspect any D1 database — either a local SQLite file produced by running migrations
via `wrangler d1 migrations apply --local`, or the D1 REST API — and emit `.d.ts` or
`.ts` files with typed row interfaces and a complete schema map.

This article covers:

1. Running migrations against a local SQLite file during CI
2. Introspecting the schema with `better-sqlite3`
3. Emitting TypeScript interfaces
4. Integrating into the Wrangler build pipeline
5. Generating Zod validation schemas from the same introspection

---

## 1. Local SQLite Fixture for Build Introspection

The introspection script needs a SQLite file that has all migrations applied. Use
`wrangler d1 migrations apply` in local mode to produce it, or run migrations directly
against a temp SQLite file using `better-sqlite3`.

```bash
# scripts/build-types.sh
#!/usr/bin/env bash
set -euo pipefail

DB_FILE=".wrangler/state/v3/d1/miniflare-D1DatabaseObject/local-dev.sqlite"

# Apply all pending migrations to the local SQLite file
npx wrangler d1 migrations apply DB --local 2>/dev/null || true

# Run the type-generation script against the local SQLite file
node --import tsx/esm scripts/generate-d1-types.ts "$DB_FILE"
```

If you prefer not to invoke Wrangler during CI, apply migrations directly:

```typescript
// scripts/apply-migrations-local.ts
import Database from 'better-sqlite3';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const DB_PATH = '/tmp/d1-schema-check.sqlite';

const db = new Database(DB_PATH);

// Track applied migrations
db.exec(`
  CREATE TABLE IF NOT EXISTS _migrations (
    name TEXT PRIMARY KEY,
    applied_at INTEGER DEFAULT (unixepoch())
  )
`);

const migrationsDir = 'migrations';
const files = readdirSync(migrationsDir)
  .filter(f => f.endsWith('.sql'))
  .sort();

for (const file of files) {
  const applied = db
    .prepare(`SELECT name FROM _migrations WHERE name = ?`)
    .get(file);
  if (applied) continue;

  const sql = readFileSync(join(migrationsDir, file), 'utf8');
  db.exec(sql);
  db.prepare(`INSERT INTO _migrations (name) VALUES (?)`).run(file);
  console.log(`Applied: ${file}`);
}

db.close();
export { DB_PATH };
```

---

## 2. Schema Introspection Logic

```typescript
// scripts/introspect-schema.ts
import Database from 'better-sqlite3';

export interface ColumnInfo {
  cid: number;
  name: string;
  type: string;          // SQLite type affinity: TEXT, INTEGER, REAL, BLOB, NUMERIC
  notnull: 0 | 1;
  dflt_value: string | null;
  pk: 0 | 1;
}

export interface TableSchema {
  tableName: string;
  columns: ColumnInfo[];
}

export function introspectSchema(dbPath: string): TableSchema[] {
  const db = new Database(dbPath, { readonly: true });

  // Get all user tables (exclude SQLite internals and Wrangler migration tables)
  const tables = db
    .prepare(
      `SELECT name FROM sqlite_master
       WHERE type = 'table'
         AND name NOT LIKE 'sqlite_%'
         AND name NOT LIKE '_cf_%'
         AND name != 'd1_migrations'
         AND name != '_migrations'
       ORDER BY name`
    )
    .all() as Array<{ name: string }>;

  const schemas: TableSchema[] = [];

  for (const { name } of tables) {
    const columns = db
      .prepare(`PRAGMA table_info(${JSON.stringify(name)})`)
      .all() as ColumnInfo[];

    schemas.push({ tableName: name, columns });
  }

  db.close();
  return schemas;
}
```

---

## 3. TypeScript Interface Emitter

Map SQLite type affinities to TypeScript types. Handle nullability, primary keys, and
optional generated columns.

```typescript
// scripts/emit-typescript.ts
import { TableSchema, ColumnInfo } from './introspect-schema';

/** Map SQLite type affinity to TypeScript type */
function sqliteTypeToTs(sqliteType: string, nullable: boolean): string {
  const base = sqliteType.toUpperCase();

  let tsType: string;
  if (base.includes('INT')) {
    tsType = 'number';
  } else if (
    base.includes('CHAR') ||
    base.includes('CLOB') ||
    base.includes('TEXT') ||
    base === ''
  ) {
    tsType = 'string';
  } else if (base.includes('BLOB')) {
    tsType = 'ArrayBuffer';
  } else if (
    base.includes('REAL') ||
    base.includes('FLOA') ||
    base.includes('DOUB')
  ) {
    tsType = 'number';
  } else if (base === 'NUMERIC' || base === 'DECIMAL') {
    tsType = 'number';
  } else if (base === 'BOOLEAN') {
    tsType = '0 | 1';    // SQLite stores booleans as integers
  } else {
    tsType = 'string';   // fallback
  }

  return nullable ? `${tsType} | null` : tsType;
}

function toPascalCase(snake: string): string {
  return snake
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join('');
}

export function emitTypeScript(schemas: TableSchema[]): string {
  const lines: string[] = [
    `// AUTO-GENERATED — do not edit by hand`,
    `// Generated from D1 schema at build time by scripts/generate-d1-types.ts`,
    `// Run \`npm run generate:types\` to regenerate`,
    ``,
    `// ─── Row interfaces ───────────────────────────────────────────────────────────`,
    ``,
  ];

  for (const { tableName, columns } of schemas) {
    const interfaceName = toPascalCase(tableName) + 'Row';
    lines.push(`export interface ${interfaceName} {`);
    for (const col of columns) {
      const nullable = col.notnull === 0 && col.pk === 0;
      const tsType = sqliteTypeToTs(col.type, nullable);
      const optional = nullable ? '?' : '';
      lines.push(`  ${col.name}${optional}: ${tsType};`);
    }
    lines.push(`}`);
    lines.push(``);
  }

  // Emit a schema map type for typed table lookups
  lines.push(`// ─── Schema map ───────────────────────────────────────────────────────────────`);
  lines.push(``);
  lines.push(`export interface D1SchemaMap {`);
  for (const { tableName } of schemas) {
    const interfaceName = toPascalCase(tableName) + 'Row';
    lines.push(`  ${tableName}: ${interfaceName};`);
  }
  lines.push(`}`);
  lines.push(``);

  return lines.join('\n');
}
```

---

## 4. Zod Schema Emitter (Optional but Recommended)

```typescript
// scripts/emit-zod.ts
import { TableSchema, ColumnInfo } from './introspect-schema';
import { toPascalCase } from './emit-typescript';

function sqliteTypeToZod(col: ColumnInfo): string {
  const base = col.type.toUpperCase();
  const nullable = col.notnull === 0 && col.pk === 0;

  let zodType: string;
  if (base.includes('INT') || base.includes('REAL') || base.includes('FLOA') || base.includes('DOUB') || base === 'NUMERIC') {
    zodType = 'z.number()';
  } else if (base.includes('BLOB')) {
    zodType = 'z.instanceof(ArrayBuffer)';
  } else if (base === 'BOOLEAN') {
    zodType = 'z.union([z.literal(0), z.literal(1)])';
  } else {
    zodType = 'z.string()';
  }

  if (nullable) {
    zodType += '.nullable().optional()';
  }

  return zodType;
}

export function emitZod(schemas: TableSchema[]): string {
  const lines: string[] = [
    `// AUTO-GENERATED — do not edit by hand`,
    `import { z } from 'zod';`,
    ``,
  ];

  for (const { tableName, columns } of schemas) {
    const schemaName = toPascalCase(tableName) + 'Schema';
    lines.push(`export const ${schemaName} = z.object({`);
    for (const col of columns) {
      lines.push(`  ${col.name}: ${sqliteTypeToZod(col)},`);
    }
    lines.push(`});`);
    lines.push(``);
    lines.push(`export type ${toPascalCase(tableName)} = z.infer<typeof ${schemaName}>;`);
    lines.push(``);
  }

  return lines.join('\n');
}
```

---

## 5. Main Generator Script

```typescript
// scripts/generate-d1-types.ts
import { writeFileSync } from 'node:fs';
import { introspectSchema } from './introspect-schema';
import { emitTypeScript } from './emit-typescript';
import { emitZod } from './emit-zod';

const dbPath = process.argv[2] ?? '.wrangler/state/v3/d1/miniflare-D1DatabaseObject/local-dev.sqlite';

console.log(`Introspecting schema from: ${dbPath}`);
const schemas = introspectSchema(dbPath);
console.log(`Found tables: ${schemas.map(s => s.tableName).join(', ')}`);

// Emit TypeScript interfaces
const tsOutput = emitTypeScript(schemas);
writeFileSync('src/generated/d1-types.ts', tsOutput, 'utf8');
console.log('Written: src/generated/d1-types.ts');

// Emit Zod schemas
const zodOutput = emitZod(schemas);
writeFileSync('src/generated/d1-schemas.ts', zodOutput, 'utf8');
console.log('Written: src/generated/d1-schemas.ts');
```

---

## 6. package.json Integration

```json
{
  "scripts": {
    "generate:types": "tsx scripts/generate-d1-types.ts",
    "prebuild": "npm run generate:types",
    "build": "wrangler deploy --dry-run"
  },
  "devDependencies": {
    "better-sqlite3": "^9.4.0",
    "@types/better-sqlite3": "^7.6.8",
    "tsx": "^4.7.0",
    "zod": "^3.22.0"
  }
}
```

CI should run `npm run generate:types` and then verify no generated files differ from
what is committed (use `git diff --exit-code src/generated/`). This catches any migration
that was applied without regenerating types.

```yaml
# .github/workflows/type-check.yml (excerpt)
- name: Generate D1 types
  run: npm run generate:types

- name: Check generated types are up to date
  run: |
    if ! git diff --exit-code src/generated/; then
      echo "ERROR: D1 types are out of date. Run 'npm run generate:types' and commit."
      exit 1
    fi
```

---

## Sample Generated Output

Given the `projects` table from earlier articles, the generator emits:

```typescript
// src/generated/d1-types.ts (excerpt — AUTO-GENERATED)

export interface ProjectsRow {
  id: string;
  tenant_id: string;
  name: string;
  status: string;
  created_at: number;
  updated_at: number;
  deleted_at?: number | null;
}

export interface D1SchemaMap {
  projects: ProjectsRow;
  tasks: TasksRow;
  audit_events: AuditEventsRow;
  tenants: TenantsRow;
}
```

```typescript
// src/generated/d1-schemas.ts (excerpt — AUTO-GENERATED)
import { z } from 'zod';

export const ProjectsSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  name: z.string(),
  status: z.string(),
  created_at: z.number(),
  updated_at: z.number(),
  deleted_at: z.number().nullable().optional(),
});

export type Projects = z.infer<typeof ProjectsSchema>;
```

---

## Anti-Patterns

- **Checking in hand-written types alongside generated ones**: Pick one. Generated types
  should replace hand-written interfaces, not coexist with them.
- **Introspecting the live D1 database from CI**: The D1 REST API has rate limits and
  latency. Use a local SQLite file built from migrations instead.
- **Not regenerating after migration**: Any migration that adds a column will cause a
  TypeScript error at runtime (column exists in DB, missing in type). Enforce regen in CI.
- **Generating `any` for unknown types**: Always fall back to `string` (SQLite's type
  affinity fallback) rather than `any`, which defeats the purpose of type generation.
- **Using `PRAGMA table_info` on views**: Views appear in `sqlite_master` with type `view`,
  not `table`. Filter them explicitly or handle them separately if you want typed views.

---

## Gotchas

- **Generated columns**: `PRAGMA table_info` returns generated columns (VIRTUAL/STORED)
  with their declared type but `notnull = 0`. The generated column may be non-null in
  practice. Check `sqlite_master` source SQL if you need to distinguish generated columns.
- **JSON columns typed as TEXT**: A column declared `TEXT` that stores JSON is typed as
  `string` in the output. Add a post-processing pass to annotate columns named `*_json`
  or `metadata` as `string /* JSON */` or use a branded type.
- **`better-sqlite3` is Node-only**: It cannot run inside a Worker. This script is purely
  a build-time tool; never import it into your Worker bundle.
- **SQLite type affinity vs. declared type**: `INTEGER` and `INT` have the same affinity
  but `TINYINT`, `SMALLINT`, and `MEDIUMINT` are all stored as `INTEGER`. The generator
  maps them all to `number`, which is correct.
- **Primary key columns are always NOT NULL**: SQLite enforces this. The generator should
  check `pk > 0` to mark PK columns as required even when `notnull === 0`.

---

## Verification

```typescript
// tests/type-generation.test.ts
import { introspectSchema } from '../scripts/introspect-schema';
import { emitTypeScript } from '../scripts/emit-typescript';

const DB_PATH = '/tmp/d1-schema-check.sqlite';

describe('type generation', () => {
  it('generates interface for projects table', () => {
    const schemas = introspectSchema(DB_PATH);
    const projectSchema = schemas.find(s => s.tableName === 'projects');
    expect(projectSchema).toBeDefined();
    expect(projectSchema!.columns.map(c => c.name)).toContain('tenant_id');
    expect(projectSchema!.columns.map(c => c.name)).toContain('deleted_at');
  });

  it('emitted TypeScript compiles', () => {
    const schemas = introspectSchema(DB_PATH);
    const ts = emitTypeScript(schemas);
    expect(ts).toContain('export interface ProjectsRow');
    expect(ts).toContain('tenant_id: string');
    expect(ts).toContain('deleted_at?: number | null');
  });

  it('no unknown columns emit "any" type', () => {
    const schemas = introspectSchema(DB_PATH);
    const ts = emitTypeScript(schemas);
    expect(ts).not.toContain(': any');
  });
});
```

---

## Related

- `sqlite-schema-introspection-automation.md` — SQLite PRAGMA-based introspection techniques
- `d1-migrations-wrangler-ci-cd.md` — running migrations that feed this generator
- `drizzle-orm-patterns.md` — Drizzle as an alternative (schema-first ORM that also generates types)
- `schema-as-code-drizzle-atlas.md` — Atlas and Drizzle for schema-driven development
- `d1-row-level-security-tenant-id.md` — the tables whose types are generated here

---

## Sources

- SQLite `sqlite_master` table — https://www.sqlite.org/schematab.html
- SQLite `PRAGMA table_info` — https://www.sqlite.org/pragma.html#pragma_table_info
- Cloudflare D1 local development — https://developers.cloudflare.com/d1/build-with-d1/local-development/
- better-sqlite3 — https://github.com/WiseLibs/better-sqlite3
- Zod documentation — https://zod.dev/
