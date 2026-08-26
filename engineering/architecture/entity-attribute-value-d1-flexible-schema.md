# Entity Attribute Value (EAV) Pattern with D1 Flexible Schema

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to store entities whose attribute sets vary widely per tenant, per product type, or per
configuration — but you cannot know the full schema at deploy time. Classic examples in the example project
platform include: instrument metadata (a guitar has strings/scale-length, a drum has shell/head-type),
user-configurable form fields, and feature-flag overrides keyed by arbitrary dimension combinations.
A rigid relational table forces you to either add hundreds of nullable columns or run risky migrations
every time a new attribute appears. EAV trades query simplicity for schema flexibility inside D1.

## Context

Cloudflare D1 is a SQLite-compatible edge database available inside Workers. SQLite's ALTER TABLE
support is limited — adding columns is cheap, but removing them or changing their type is not. D1
also lacks JSON-schema enforcement at the storage layer. The EAV pattern stores each attribute as its
own row (`entity_id`, `attribute_key`, `attribute_value`) instead of each entity as a row with many
columns. This article covers: table design, type-safe TypeScript wrappers, index strategy, N+1
avoidance, and when to abandon EAV in favour of JSON columns.

---

## Core Table Design

```sql
-- migrations/0001_eav.sql
CREATE TABLE IF NOT EXISTS eav_entity (
  id          TEXT PRIMARY KEY,          -- nanoid / cuid2
  kind        TEXT NOT NULL,             -- "instrument" | "form_field" | ...
  tenant_id   TEXT NOT NULL,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS eav_attribute (
  entity_id   TEXT NOT NULL REFERENCES eav_entity(id) ON DELETE CASCADE,
  attr_key    TEXT NOT NULL,
  attr_value  TEXT,                      -- always stored as TEXT; cast in app layer
  attr_type   TEXT NOT NULL DEFAULT 'string',  -- "string"|"number"|"boolean"|"json"
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (entity_id, attr_key)
);

CREATE INDEX IF NOT EXISTS idx_eav_attr_tenant_key
  ON eav_attribute (attr_key, attr_value)
  WHERE attr_key IN ('status', 'category', 'plan');  -- partial index for hot keys

CREATE INDEX IF NOT EXISTS idx_eav_entity_kind_tenant
  ON eav_entity (kind, tenant_id, created_at DESC);
```

The partial index on `eav_attribute` avoids full-table scans for the handful of attributes that are
actually filtered in WHERE clauses. Everything else is fetched by entity_id.

---

## Type-Safe TypeScript Repository

```typescript
// src/repositories/eav-repository.ts
import type { D1Database } from '@cloudflare/workers-types';

export type AttrType = 'string' | 'number' | 'boolean' | 'json';

export interface EavEntity {
  id: string;
  kind: string;
  tenantId: string;
  createdAt: number;
  attributes: Record<string, unknown>;
}

interface RawAttrRow {
  entity_id: string;
  attr_key: string;
  attr_value: string | null;
  attr_type: AttrType;
}

function coerce(value: string | null, type: AttrType): unknown {
  if (value === null) return null;
  switch (type) {
    case 'number':  return Number(value);
    case 'boolean': return value === 'true';
    case 'json':    return JSON.parse(value);
    default:        return value;
  }
}

function serialize(value: unknown): { text: string; type: AttrType } {
  if (typeof value === 'number')  return { text: String(value),       type: 'number'  };
  if (typeof value === 'boolean') return { text: String(value),       type: 'boolean' };
  if (typeof value === 'object')  return { text: JSON.stringify(value), type: 'json' };
  return { text: String(value), type: 'string' };
}

export class EavRepository {
  constructor(private readonly db: D1Database) {}

  async findById(entityId: string): Promise<EavEntity | null> {
    const [entityRow, attrRows] = await Promise.all([
      this.db
        .prepare('SELECT id, kind, tenant_id, created_at FROM eav_entity WHERE id = ?')
        .bind(entityId)
        .first<{ id: string; kind: string; tenant_id: string; created_at: number }>(),
      this.db
        .prepare('SELECT entity_id, attr_key, attr_value, attr_type FROM eav_attribute WHERE entity_id = ?')
        .bind(entityId)
        .all<RawAttrRow>(),
    ]);

    if (!entityRow) return null;

    const attributes: Record<string, unknown> = {};
    for (const row of attrRows.results) {
      attributes[row.attr_key] = coerce(row.attr_value, row.attr_type);
    }

    return {
      id: entityRow.id,
      kind: entityRow.kind,
      tenantId: entityRow.tenant_id,
      createdAt: entityRow.created_at,
      attributes,
    };
  }

  async findManyByKind(
    tenantId: string,
    kind: string,
    limit = 50,
    cursor?: number,
  ): Promise<EavEntity[]> {
    const entityRows = await this.db
      .prepare(
        `SELECT id, kind, tenant_id, created_at FROM eav_entity
         WHERE kind = ? AND tenant_id = ? AND created_at < ?
         ORDER BY created_at DESC LIMIT ?`,
      )
      .bind(kind, tenantId, cursor ?? Date.now(), limit)
      .all<{ id: string; kind: string; tenant_id: string; created_at: number }>();

    if (entityRows.results.length === 0) return [];

    // Batch fetch all attributes — single round-trip, no N+1
    const ids = entityRows.results.map((r) => r.id);
    const placeholders = ids.map(() => '?').join(',');
    const attrRows = await this.db
      .prepare(
        `SELECT entity_id, attr_key, attr_value, attr_type
         FROM eav_attribute WHERE entity_id IN (${placeholders})`,
      )
      .bind(...ids)
      .all<RawAttrRow>();

    // Group by entity
    const attrsByEntity = new Map<string, Record<string, unknown>>();
    for (const row of attrRows.results) {
      const map = attrsByEntity.get(row.entity_id) ?? {};
      map[row.attr_key] = coerce(row.attr_value, row.attr_type);
      attrsByEntity.set(row.entity_id, map);
    }

    return entityRows.results.map((e) => ({
      id: e.id,
      kind: e.kind,
      tenantId: e.tenant_id,
      createdAt: e.created_at,
      attributes: attrsByEntity.get(e.id) ?? {},
    }));
  }
}
```

---

## Upsert Pattern for Attribute Sets

```typescript
// src/repositories/eav-repository.ts (continued)

export class EavRepository {
  // ... findById, findManyByKind above ...

  async upsertAttributes(
    entityId: string,
    attributes: Record<string, unknown>,
  ): Promise<void> {
    const now = Math.floor(Date.now() / 1000);
    const statements = Object.entries(attributes).map(([key, value]) => {
      const { text, type } = serialize(value);
      return this.db
        .prepare(
          `INSERT INTO eav_attribute (entity_id, attr_key, attr_value, attr_type, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (entity_id, attr_key) DO UPDATE
             SET attr_value = excluded.attr_value,
                 attr_type  = excluded.attr_type,
                 updated_at = excluded.updated_at`,
        )
        .bind(entityId, key, text, type, now);
    });

    // D1 batch executes all statements in a single HTTP request to the D1 server
    if (statements.length > 0) {
      await this.db.batch(statements);
    }
  }

  async deleteAttribute(entityId: string, key: string): Promise<void> {
    await this.db
      .prepare('DELETE FROM eav_attribute WHERE entity_id = ? AND attr_key = ?')
      .bind(entityId, key)
      .run();
  }
}
```

`db.batch()` wraps all attribute upserts in one implicit transaction, preventing partial writes when
the Worker is evicted mid-flight.

---

## Filtered Search via Pivot Join

Querying "all entities of kind X where status = 'active' AND plan = 'pro'" requires a self-join or
a pivot approach:

```typescript
// src/repositories/eav-repository.ts (continued)

async findByAttributes(
  tenantId: string,
  kind: string,
  filters: Record<string, string>,
): Promise<string[]> {
  // Build a query that requires ALL filter keys to match
  const filterEntries = Object.entries(filters);
  if (filterEntries.length === 0) return [];

  // Each filter becomes a CTE segment; intersect entity_ids
  const conditions = filterEntries
    .map((_, i) => `a${i}.attr_key = ? AND a${i}.attr_value = ?`)
    .join(' AND ');
  const joins = filterEntries
    .map((_, i) => `JOIN eav_attribute a${i} ON e.id = a${i}.entity_id`)
    .join('\n  ');
  const params = filterEntries.flatMap(([k, v]) => [k, v]);

  const sql = `
    SELECT e.id
    FROM eav_entity e
    ${joins}
    WHERE e.kind = ? AND e.tenant_id = ?
      AND ${conditions}
    LIMIT 200`;

  const rows = await this.db
    .prepare(sql)
    .bind(...params, kind, tenantId)
    .all<{ id: string }>();

  return rows.results.map((r) => r.id);
}
```

Keep the filter set small (≤ 3 keys) and always include the partial index columns in the filter to
avoid cross-product scans.

---

## JSON Column Hybrid — When to Prefer It

For entities where the attribute set is known and bounded, prefer a JSON column over EAV:

```sql
-- Better for known-shape payloads
CREATE TABLE instrument_metadata (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  kind        TEXT NOT NULL,
  attrs       TEXT NOT NULL DEFAULT '{}',   -- JSON blob
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);
```

```typescript
// D1 supports JSON extraction in WHERE clauses via SQLite's json_extract
const rows = await db
  .prepare(
    `SELECT id, attrs FROM instrument_metadata
     WHERE tenant_id = ? AND json_extract(attrs, '$.status') = ?`,
  )
  .bind(tenantId, 'active')
  .all<{ id: string; attrs: string }>();
```

Use EAV when: attribute count is unbounded, attributes vary >50% across entities, or attributes need
individual audit trails. Use JSON column when: ≤30 attributes, shape is mostly stable, atomic
updates are rare.

---

## Anti-patterns

- **Full-table EAV scan**: Never `SELECT * FROM eav_attribute WHERE attr_key = 'status'` without a
  supporting index. Always scope by `entity_id` first, or use a partial index for hot lookup keys.
- **Storing typed data as untyped text without the `attr_type` column**: You will lose the ability
  to round-trip numbers, booleans, and JSON without silent coercion bugs.
- **One D1 statement per attribute**: Use `db.batch()` for upserts; individual prepare+run calls per
  attribute multiply latency by the attribute count.
- **EAV for everything**: EAV breaks ORDER BY on attribute values, makes aggregation painful, and
  defeats D1's query planner. Reserve it for genuinely schema-free domains.
- **No cascade delete**: Forgetting `ON DELETE CASCADE` on `eav_attribute.entity_id` leaves orphan
  attribute rows that accumulate indefinitely and inflate scan times.

---

## Gotchas

- D1 `batch()` is limited to 100 statements per call. Split large attribute sets across multiple
  batch calls when an entity can have >100 attributes.
- SQLite `json_extract` on a TEXT column that stores non-JSON data throws at runtime, not at parse
  time. Guard with `json_valid(attrs)` in a CHECK constraint.
- D1 `IN (...)` clauses with dynamic bind parameters require constructing the placeholder string at
  runtime. There is no array bind syntax.
- Partial indexes (`WHERE attr_key IN (...)`) are only used when the query's WHERE clause exactly
  matches the index condition. D1/SQLite will silently fall back to a full scan otherwise — use
  `EXPLAIN QUERY PLAN` to verify.
- `unixepoch()` in D1 returns seconds, not milliseconds. Mixing second-epoch and millisecond-epoch
  comparisons in cursor pagination will corrupt sort order.

---

## Verification

```typescript
// test/eav-repository.test.ts (Vitest + D1 local binding)
import { describe, it, expect, beforeEach } from 'vitest';
import { EavRepository } from '../src/repositories/eav-repository';

describe('EavRepository', () => {
  let repo: EavRepository;

  beforeEach(async () => {
    // Use wrangler's local D1 binding in test environment
    repo = new EavRepository(env.DB);
    await env.DB.exec(`DELETE FROM eav_entity; DELETE FROM eav_attribute;`);
  });

  it('round-trips typed attributes', async () => {
    const id = 'ent_01';
    await env.DB.prepare(
      `INSERT INTO eav_entity (id, kind, tenant_id) VALUES (?, ?, ?)`,
    ).bind(id, 'instrument', 'tenant_a').run();

    await repo.upsertAttributes(id, {
      strings:  42,
      active:   true,
      meta:     { color: 'red' },
      name:     'Les Paul',
    });

    const entity = await repo.findById(id);
    expect(entity?.attributes.strings).toBe(42);
    expect(entity?.attributes.active).toBe(true);
    expect(entity?.attributes.meta).toEqual({ color: 'red' });
  });
});
```

Run locally with `wrangler dev --local` and `vitest run`. Confirm `EXPLAIN QUERY PLAN` for the
pivot join returns `SEARCH eav_attribute USING INDEX idx_eav_attr_tenant_key`.

---

## Related

- `/documentation/categories/architecture/d1-batch-operations-query-optimisation.md`
- `/documentation/categories/architecture/soft-delete-temporal-patterns-d1.md`
- `/documentation/categories/architecture/polyglot-persistence-cloudflare-workers.md`
- `/documentation/categories/architecture/specification-pattern-workers-d1-query-building.md`
- `/documentation/categories/architecture/multi-tenancy-isolation-patterns.md`

---

## Sources

- SQLite EAV schema design: https://www.sqlite.org/eav.html
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- D1 JSON functions: https://developers.cloudflare.com/d1/sql-api/sql-sqlite-compatibility/
- SQLite partial indexes: https://www.sqlite.org/partialindex.html
- Martin Fowler — "Patterns of Enterprise Application Architecture" (EAV chapter)
