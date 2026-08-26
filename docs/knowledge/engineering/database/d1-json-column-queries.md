# JSON Column Storage and Querying in D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to store semi-structured or variable-shape data alongside fixed columns — user preferences, event metadata, feature flags per row — without altering the schema every time a new key is added. D1 inherits SQLite's JSON1 extension, giving you a full set of `json_*` functions to store, query, index, and aggregate JSON inside TEXT columns.

## Context

SQLite stores JSON as plain TEXT. The JSON1 extension (compiled in by default, available in D1) provides functions to parse, extract, and construct JSON values inline in SQL. D1 also supports expression indexes, so you can index a specific JSON path and get index-backed equality lookups on JSON fields without a schema change.

JSON functions operate on valid JSON strings. Passing malformed JSON returns NULL (not an error in most functions).

## Solution

### 1. Schema design

```sql
CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  type        TEXT    NOT NULL,
  tenant_id   TEXT    NOT NULL,
  payload     TEXT    NOT NULL DEFAULT '{}',  -- JSON column
  metadata    TEXT    NOT NULL DEFAULT '{}',  -- JSON column
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Expression index on a JSON field for fast equality lookups
CREATE INDEX IF NOT EXISTS idx_events_payload_user_id
  ON events (json_extract(payload, '$.user_id'));

CREATE INDEX IF NOT EXISTS idx_events_metadata_source
  ON events (json_extract(metadata, '$.source'));
```

### 2. Inserting JSON

```typescript
// src/services/events.ts
export interface EventPayload {
  user_id: string;
  action: string;
  resource_id?: string;
  tags?: string[];
}

export async function insertEvent(
  db: D1Database,
  tenantId: string,
  type: string,
  payload: EventPayload,
  metadata: Record<string, unknown> = {}
): Promise<number> {
  const result = await db
    .prepare(`
      INSERT INTO events (type, tenant_id, payload, metadata)
      VALUES (?, ?, json(?), json(?))
    `)
    .bind(type, tenantId, JSON.stringify(payload), JSON.stringify(metadata))
    .run();

  return result.meta.last_row_id as number;
}
```

### 3. json_extract() — reading fields

```typescript
// Read a specific JSON field in SELECT
export async function getEventsByUser(
  db: D1Database,
  tenantId: string,
  userId: string
): Promise<{ id: number; type: string; action: string; created_at: string }[]> {
  const rows = await db
    .prepare(`
      SELECT
        id,
        type,
        json_extract(payload, '$.action')    AS action,
        json_extract(payload, '$.resource_id') AS resource_id,
        created_at
      FROM events
      WHERE tenant_id = ?
        AND json_extract(payload, '$.user_id') = ?
      ORDER BY created_at DESC
      LIMIT 100
    `)
    .bind(tenantId, userId)
    .all<{ id: number; type: string; action: string; resource_id: string | null; created_at: string }>();

  return rows.results;
}
```

### 4. json_object() and json_array() — construction

```typescript
// Build JSON inline in SQL (useful for aggregation or computed columns)
export async function getEventSummary(
  db: D1Database,
  tenantId: string
): Promise<string> {
  const row = await db
    .prepare(`
      SELECT json_object(
        'tenant_id',   ?,
        'total',       COUNT(*),
        'types',       json_group_array(DISTINCT type),
        'date_range',  json_object(
          'min', MIN(created_at),
          'max', MAX(created_at)
        )
      ) AS summary
      FROM events
      WHERE tenant_id = ?
    `)
    .bind(tenantId, tenantId)
    .first<{ summary: string }>();

  return row?.summary ?? '{}';
}

// json_array() — build an array literal in SQL
export async function getDistinctActions(
  db: D1Database,
  tenantId: string
): Promise<string[]> {
  const row = await db
    .prepare(`
      SELECT json_group_array(DISTINCT json_extract(payload, '$.action')) AS actions
      FROM events
      WHERE tenant_id = ?
        AND json_extract(payload, '$.action') IS NOT NULL
    `)
    .bind(tenantId)
    .first<{ actions: string }>();

  if (!row?.actions) return [];
  return JSON.parse(row.actions) as string[];
}
```

### 5. JSON patch updates (json_patch)

```typescript
// Merge new keys into an existing JSON column without overwriting unrelated fields
export async function patchEventMetadata(
  db: D1Database,
  eventId: number,
  patch: Record<string, unknown>
): Promise<void> {
  await db
    .prepare(`
      UPDATE events
      SET metadata = json_patch(metadata, json(?))
      WHERE id = ?
    `)
    .bind(JSON.stringify(patch), eventId)
    .run();
}

// json_set() — set specific paths without full patch
export async function setEventTag(
  db: D1Database,
  eventId: number,
  key: string,
  value: string
): Promise<void> {
  // json_set(json, path, value) — adds or replaces a single path
  await db
    .prepare(`
      UPDATE events
      SET payload = json_set(payload, ?, ?)
      WHERE id = ?
    `)
    .bind(`$.${key}`, value, eventId)
    .run();
}

// json_remove() — delete a key
export async function removeEventField(
  db: D1Database,
  eventId: number,
  field: string
): Promise<void> {
  await db
    .prepare(`
      UPDATE events
      SET payload = json_remove(payload, ?)
      WHERE id = ?
    `)
    .bind(`$.${field}`, eventId)
    .run();
}
```

### 6. JSON aggregation

```typescript
// json_group_array + json_group_object for aggregating rows into JSON
export async function getEventsByTypeAsJson(
  db: D1Database,
  tenantId: string
): Promise<Record<string, unknown[]>> {
  // Returns one row per type, with all payloads as a JSON array
  const rows = await db
    .prepare(`
      SELECT
        type,
        json_group_array(json(payload)) AS payloads
      FROM events
      WHERE tenant_id = ?
      GROUP BY type
    `)
    .bind(tenantId)
    .all<{ type: string; payloads: string }>();

  const result: Record<string, unknown[]> = {};
  for (const row of rows.results) {
    result[row.type] = JSON.parse(row.payloads);
  }
  return result;
}
```

### 7. Worker handler integrating JSON queries

```typescript
// src/handlers/events.ts
import { insertEvent, getEventsByUser, patchEventMetadata } from '../services/events';

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const tenantId = request.headers.get('x-tenant-id') ?? '';

    if (!tenantId) {
      return Response.json({ error: 'Missing x-tenant-id header' }, { status: 401 });
    }

    if (url.pathname === '/events' && request.method === 'POST') {
      const body = await request.json<{ type: string; payload: Record<string, unknown> }>();
      const id = await insertEvent(env.DB, tenantId, body.type, body.payload as any);
      return Response.json({ id }, { status: 201 });
    }

    if (url.pathname.startsWith('/events/user/') && request.method === 'GET') {
      const userId = url.pathname.split('/').pop() ?? '';
      const events = await getEventsByUser(env.DB, tenantId, userId);
      return Response.json({ events });
    }

    if (url.pathname.startsWith('/events/') && request.method === 'PATCH') {
      const eventId = parseInt(url.pathname.split('/').pop() ?? '0', 10);
      const patch = await request.json<Record<string, unknown>>();
      await patchEventMetadata(env.DB, eventId, patch);
      return Response.json({ ok: true });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Implementation Details

- `json_extract(col, '$.path')` returns a SQLite value typed by the JSON value: TEXT for strings, REAL/INTEGER for numbers, NULL for missing keys. Nested paths use dot notation (`$.user.id`) and array indexes (`$.tags[0]`).
- `json_patch()` implements RFC 7396 JSON Merge Patch — it merges keys, overwrites scalars, and deletes keys set to `null` in the patch. It does NOT support JSON Patch (RFC 6902) operations like `add`/`remove`/`replace` with explicit paths.
- Expression indexes (`CREATE INDEX ON t (json_extract(col, '$.x'))`) are used automatically by the query planner when the WHERE clause contains the identical expression. The expression in the index definition and in the query must match exactly.
- `json_group_array` produces a JSON array from an aggregate group. Pair with `GROUP BY` to get per-group arrays.
- `json()` validates and normalizes a JSON string. Wrap user-supplied JSON in `json(?)` to reject malformed input at insert time.

## Anti-patterns

- **Storing arrays of foreign keys as JSON** — `payload = '["id1","id2"]'` is tempting but kills join performance. Use a junction table instead.
- **Deep JSON nesting** — Queries on `$.a.b.c.d` are not indexable and require full table scans. Flatten frequently-queried fields to top-level columns.
- **Concatenating JSON strings** — Never build JSON by string concatenation. Use `json_object()` or serialize in TypeScript and bind as a parameter.
- **Missing expression index** — Filtering on `json_extract(payload, '$.user_id') = ?` without the matching expression index is a full table scan on large tables.
- **Assuming JSON type coercion** — `json_extract` returns a TEXT for string values. Comparing with an integer literal (`= 123`) may or may not work depending on SQLite affinity. Cast explicitly: `CAST(json_extract(payload, '$.count') AS INTEGER)`.

## Gotchas

- D1 does not have a native JSON column type — it is always TEXT. The `json()` function validates at query time, not at storage time (no CHECK constraint equivalent out of the box). Add a CHECK if you need it: `CHECK(json_valid(payload))`.
- `json_group_array` returns a JSON string, not a SQLite array. Parse it in TypeScript before use.
- Expression indexes are NOT used when you wrap the expression in a function: `WHERE LOWER(json_extract(payload, '$.action')) = 'click'` does not use an index on `json_extract(payload, '$.action')`.
- `json_patch` with a `null` value DELETES the key (RFC 7396 semantics). If you need to set a field to JSON null, use `json_set` instead.
- D1 batch statements share a connection but are independent transactions. If one statement in a batch fails, earlier statements are NOT automatically rolled back.

## Verification

```bash
# Insert a test event
npx wrangler d1 execute example project-db --command "
  INSERT INTO events (type, tenant_id, payload, metadata)
  VALUES ('click', 'tenant-1', json('{\"user_id\":\"u1\",\"action\":\"buy\"}'), json('{\"source\":\"web\"}'));
"

# Verify json_extract and expression index
npx wrangler d1 execute example project-db --command "
  EXPLAIN QUERY PLAN
  SELECT id FROM events WHERE json_extract(payload, '$.user_id') = 'u1';
"
# Should show 'SEARCH events USING INDEX idx_events_payload_user_id'

# Verify json_patch
npx wrangler d1 execute example project-db --command "
  UPDATE events SET metadata = json_patch(metadata, '{\"env\":\"prod\"}') WHERE id = 1;
  SELECT metadata FROM events WHERE id = 1;
"
# Expected: {\"source\":\"web\",\"env\":\"prod\"}
```

## Related

- `documentation/docs/policies/database/d1-full-text-search-fts5.md` — FTS5 over TEXT columns including JSON-derived values
- `documentation/docs/policies/database/d1-schema-version-tracking.md` — adding expression indexes via migrations
- `documentation/docs/policies/database/d1-row-level-security-pattern.md` — combining JSON column filters with tenant_id RLS

## Sources

- https://www.sqlite.org/json1.html
- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/expridx.html
