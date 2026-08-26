# D1 JSON Patch Partial Update Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker stores user preferences, workflow configuration, or tenant settings as a JSON column. A PATCH endpoint receives only the changed fields, but a naive implementation reads the entire document into the Worker, merges in JavaScript, then writes the whole blob back — wasting a round-trip and risking lost-update races under concurrent edits.

## Context

SQLite (and therefore D1) ships `json_patch(target, patch)` which implements RFC 7396 Merge Patch: keys in `patch` overwrite keys in `target`; setting a key to `null` removes it. For deeper surgical updates, `json_set()`, `json_insert()`, and `json_remove()` accept dotted/bracketed path strings. All of these run inside a single `UPDATE` statement — no read-modify-write round-trip required. D1 executes the JSON mutation server-side and only the scalar column value crosses the wire.

RFC 6902 (JSON Patch with `op`/`path`/`value` arrays) is not built into SQLite; the pattern below emits equivalent SQL by translating ops in the Worker before sending one parameterized statement.

## json_patch() — RFC 7396 Merge Patch

`json_patch(original, patch)` merges shallowly at the top level and recursively for nested objects. A `null` value in the patch removes the key.

```typescript
// src/db/settings.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface SettingsPatch {

}

/**
 * Merge-patch a JSON settings column in a single UPDATE.
 * No read round-trip; SQLite resolves the merge server-side.
 */
export async function patchSettings(
  db: D1Database,
  tenantId: string,
  patch: SettingsPatch
): Promise<void> {
  const patchJson = JSON.stringify(patch);

  const { success, meta } = await db
    .prepare(
      `UPDATE tenants
       SET settings = json_patch(settings, ?),
           updated_at = unixepoch()
       WHERE id = ?`
    )
    .bind(patchJson, tenantId)
    .run();

  if (!success || meta.rows_written === 0) {
    throw new Error(`Settings update failed for tenant ${tenantId}`);
  }
}
```

```sql
-- Example: remove a key by setting it to null in the patch
-- Before: {"theme":"dark","lang":"en","beta":true}
-- Patch:  {"theme":"light","beta":null}
-- After:  {"theme":"light","lang":"en"}

UPDATE tenants
SET settings = json_patch(settings, '{"theme":"light","beta":null}')
WHERE id = 'ten_abc';
```

## json_set() — Surgical Nested Path Updates

`json_set(json, path, value [, path, value …])` updates one or more paths atomically. Paths use `$` as root with dot notation (`$.notifications.email`) or bracket notation for arrays (`$.tags[0]`).

```typescript
// src/db/user-prefs.ts

/**
 * Update a single nested preference without touching sibling keys.
 * Useful when different UI panels save independent sub-trees.
 */
export async function setNestedPref(
  db: D1Database,
  userId: string,
  path: string,          // e.g. "$.notifications.email"
  value: unknown
): Promise<void> {
  // D1 bind cannot accept the path as a positional parameter inside json_set —
  // the path must be a literal. Build the statement with the sanitised path.
  const safePath = path.replace(/[^a-zA-Z0-9_.\[\]$]/g, '');
  const valueJson = JSON.stringify(value);

  await db
    .prepare(
      `UPDATE users
       SET prefs = json_set(prefs, '${safePath}', json(?)),
           updated_at = unixepoch()
       WHERE id = ?`
    )
    .bind(valueJson, userId)
    .run();
}

// Usage:
// await setNestedPref(db, userId, '$.notifications.email', false);
// await setNestedPref(db, userId, '$.display.density', 'compact');
```

```sql
-- Multi-path json_set in one statement
UPDATE users
SET prefs = json_set(
  prefs,
  '$.notifications.email', json('false'),
  '$.display.density',     'compact',
  '$.timezone',            'Europe/Berlin'
)
WHERE id = ?;
```

## Translating RFC 6902 Ops to SQLite JSON Functions

When a client sends a standard JSON Patch array, translate each op to the corresponding SQLite function in the Worker before issuing the `UPDATE`.

```typescript
// src/lib/json-patch-sql.ts

type Op =
  | { op: 'replace'; path: string; value: unknown }
  | { op: 'remove';  path: string }
  | { op: 'add';     path: string; value: unknown };

/**
 * Convert a JSON Patch (RFC 6902) array into a single SQLite expression
 * that can be embedded in an UPDATE … SET col = <expr>.
 *
 * Returns { expr, bindings } where expr is the nested json_* call
 * and bindings are the positional values to .bind() in order.
 *
 * Security: paths are allowlisted — only alphanumeric dot-bracket paths
 * accepted to prevent injection via the path string literal.
 */
export function buildJsonPatchExpr(
  columnName: string,
  ops: Op[]
): { expr: string; bindings: unknown[] } {
  const SAFE_PATH = /^\$(\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])*$/;
  const bindings: unknown[] = [];
  let expr = columnName;

  for (const op of ops) {
    if (!SAFE_PATH.test(op.path)) {
      throw new Error(`Unsafe JSON path: ${op.path}`);
    }

    if (op.op === 'replace' || op.op === 'add') {
      bindings.push(JSON.stringify(op.value));
      expr = `json_set(${expr}, '${op.path}', json(?))`;
    } else if (op.op === 'remove') {
      expr = `json_remove(${expr}, '${op.path}')`;
    }
  }

  return { expr, bindings };
}

// Worker handler
export async function handlePatch(
  db: D1Database,
  tenantId: string,
  ops: Op[]
): Promise<Response> {
  const { expr, bindings } = buildJsonPatchExpr('settings', ops);

  const stmt = db.prepare(
    `UPDATE tenants SET settings = ${expr}, updated_at = unixepoch() WHERE id = ?`
  );

  await stmt.bind(...bindings, tenantId).run();
  return new Response(null, { status: 204 });
}
```

## Atomic Read-After-Patch with RETURNING

Use `RETURNING` to get the updated document back without a second query:

```typescript
export async function patchAndReturn(
  db: D1Database,
  tenantId: string,
  patch: SettingsPatch
): Promise<Record<string, unknown>> {
  const { results } = await db
    .prepare(
      `UPDATE tenants
       SET settings   = json_patch(settings, ?),
           updated_at = unixepoch()
       WHERE id = ?
       RETURNING id, settings, updated_at`
    )
    .bind(JSON.stringify(patch), tenantId)
    .all<{ id: string; settings: string; updated_at: number }>();

  if (results.length === 0) throw new Error('Tenant not found');

  return {
    id: results[0].id,
    settings: JSON.parse(results[0].settings),
    updated_at: results[0].updated_at,
  };
}
```

## Anti-patterns

- Reading the JSON document into the Worker, merging in JavaScript, then writing the entire blob back — this creates a read-modify-write window where concurrent PATCHes overwrite each other's changes.
- Passing user-supplied JSON path strings directly as SQLite string literals without sanitization — path expressions are not bind-parameterizable in SQLite and must be sanitized with a strict allowlist regex.
- Using `json_set` with a raw JavaScript value (not `json(?)` wrapper) for object or array values — SQLite will store them as a plain string, not as a JSON sub-document; always wrap with `json(?)`.
- Applying an `op: 'add'` to an array index that doesn't exist — `json_set` silently does nothing for out-of-bound array indices in some SQLite builds; prefer appending via `json_insert(col, '$.arr[#]', value)` for array push.
- Ignoring `meta.rows_written === 0` after the UPDATE — the tenant/user row may not exist; treat zero rows written as a 404.

## Gotchas

- `json_patch` implements RFC 7396 (merge patch), not RFC 6902 (JSON Patch). Merge patch cannot express array element removal or positional array inserts; those require `json_remove`/`json_insert` with index paths.
- SQLite's `json()` function validates JSON; passing an invalid JSON string via `json(?)` causes the entire statement to fail, not just that field. Validate `JSON.stringify(value)` is well-formed before binding.
- `json_set` creates intermediate keys if they don't exist but only at the leaf path — parent objects must already exist in the document. Use `json_patch` to initialize missing sub-objects.
- D1's `RETURNING` clause is supported on `UPDATE` as of D1 GA. Verify with `wrangler d1 execute` if using an older Wrangler version.
- JSON columns in SQLite are stored as TEXT; indexing on a JSON path requires a generated column or an expression index (`CREATE INDEX … ON t(json_extract(col, '$.key'))`).

## Verification

```typescript
// tests/json-patch.test.ts
import { env } from 'cloudflare:test';

describe('json_patch partial update', () => {
  beforeEach(async () => {
    await env.DB.exec(`DELETE FROM tenants`);
    await env.DB.exec(`
      INSERT INTO tenants (id, settings, updated_at)
      VALUES ('t1', '{"theme":"dark","lang":"en","beta":true}', 0)
    `);
  });

  it('merges patch without overwriting unchanged keys', async () => {
    await env.DB.prepare(
      `UPDATE tenants SET settings = json_patch(settings, ?) WHERE id = 't1'`
    )
      .bind(JSON.stringify({ theme: 'light' }))
      .run();

    const row = await env.DB.prepare(
      `SELECT json_extract(settings, '$.lang') AS lang,
              json_extract(settings, '$.theme') AS theme
       FROM tenants WHERE id = 't1'`
    ).first<{ lang: string; theme: string }>();

    expect(row?.lang).toBe('en');   // unchanged
    expect(row?.theme).toBe('light');
  });

  it('removes key when patch sets it to null', async () => {
    await env.DB.prepare(
      `UPDATE tenants SET settings = json_patch(settings, ?) WHERE id = 't1'`
    )
      .bind(JSON.stringify({ beta: null }))
      .run();

    const row = await env.DB.prepare(
      `SELECT json_extract(settings, '$.beta') AS beta FROM tenants WHERE id = 't1'`
    ).first<{ beta: unknown }>();

    expect(row?.beta).toBeNull();
  });
});
```

```bash
# Smoke-test via wrangler
wrangler d1 execute MY_DB --command \
  "UPDATE tenants SET settings = json_patch(settings, '{\"theme\":\"light\"}') WHERE id = 'ten_1' RETURNING settings"
```

## Related

- `database/d1-json-column-patterns.md` — storing and indexing JSON in D1
- `database/d1-json-aggregation-analytics.md` — aggregating JSON data with json_each
- `database/d1-json-columns-partial-indexes.md` — partial indexes on json_extract paths
- `database/d1-upsert-conflict-resolution-workers.md` — INSERT OR REPLACE and conflict handling
- `database/d1-returning-clause-upsert-workers.md` — RETURNING for read-after-write

## Sources

- https://www.sqlite.org/json1.html
- https://datatracker.ietf.org/doc/html/rfc7396 (JSON Merge Patch)
- https://developers.cloudflare.com/d1/worker-api/d1-database/
