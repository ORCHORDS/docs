# d1-typescript-patterns

**Issue:** D1 with TypeScript strict mode — prepared statements, result typing, null safety
**Date:** 2026-08-11
**Status:** documented

## Symptom

After enabling `@cloudflare/workers-types` strict mode, D1 usage breaks in multiple ways:
- `env.DB.prepare()` errors because `env.DB` is `D1Database | undefined`
- `result.first()` returns `unknown` instead of your expected type
- `.all()` results are `Record<string, unknown>[]` — no autocomplete
- Comparison of `null` vs `undefined` from `.first()` is ambiguous

## Patterns

### Non-null assertion for env.DB

```typescript
// env.DB is D1Database | undefined with workers-types
// Use ! to assert it's present (checked at startup):
const rows = await env.DB!.prepare(sql).bind(...params).all();
```

For production, add a startup guard on the handler entry point:

```typescript
if (!env.DB) return jsonError(503, 'database_unavailable', undefined, undefined);
```

### Typed results

```typescript
// .first<T>() → T | null
const user = await env.DB!.prepare(
  `SELECT id, email, role FROM users WHERE id = ? AND tenant_id = ?`
).bind(userId, tenantId).first<{ id: string; email: string; role: string }>();

if (!user) return jsonError(404, 'not_found', 'User not found', ctx.request_id);
// user is now { id: string; email: string; role: string } ✓

// .all<T>() → D1Result<T>
const { results } = await env.DB!.prepare(
  `SELECT id, name, status FROM controls WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?`
).bind(tenantId, 100).all<{ id: string; name: string; status: string }>();
// results is Array<{ id: string; name: string; status: string }> ✓
```

### Mixed params (strings + numbers)

```typescript
const params: (string | number)[] = [ctx.tenant.id];
if (status) { sql += ` AND status = ?`; params.push(status); }
sql += ` LIMIT ?`; params.push(limit);
const rows = await env.DB!.prepare(sql).bind(...params).all<Row>();
```

### Dynamic UPDATE with allowlist

```typescript
const PATCHABLE = ['name', 'status', 'priority'] as const;
const fields: string[] = [];
const values: unknown[] = [];
for (const col of PATCHABLE) {
  if ((body as Record<string, unknown>)[col] !== undefined) {
    fields.push(`${col} = ?`);
    values.push((body as Record<string, unknown>)[col]);
  }
}
if (!fields.length) return jsonError(400, 'no_updates', 'No fields to update', ctx.request_id);
values.push(now, id, ctx.tenant.id);  // updated_at, WHERE id, WHERE tenant_id
await env.DB!.prepare(
  `UPDATE widgets SET ${fields.join(', ')}, updated_at = ? WHERE id = ? AND tenant_id = ?`
).bind(...values).run();
```

### Run vs All vs First

| Method | Returns | Use case |
|--------|---------|----------|
| `.run()` | `D1Result` (no rows) | INSERT / UPDATE / DELETE |
| `.first<T>()` | `T \| null` | SELECT by PK — expect 0 or 1 row |
| `.all<T>()` | `D1Result<T>` (`.results` is `T[]`) | SELECT list — expect 0–N rows |
| `.raw<T>()` | `T[][]` | Rare — returns raw arrays, no column names |

### batch() — DO NOT USE in Pages Functions

D1 `batch()` is broken by the esbuild bundler in Pages Functions — it silently strips SQL.
Use sequential `.run()` calls instead:

```typescript
// Wrong — statements silently dropped in bundled output:
await env.DB!.batch([stmt1, stmt2, stmt3]);

// Correct:
for (const stmt of stmts) await stmt.run();
```

See `d1-batch-bundler-bug.md`.

### Transactions

D1 supports transactions via `BEGIN` / `COMMIT`:

```typescript
await env.DB!.exec('BEGIN');
try {
  await env.DB!.prepare(`INSERT INTO a ...`).bind(...).run();
  await env.DB!.prepare(`UPDATE b ...`).bind(...).run();
  await env.DB!.exec('COMMIT');
} catch (e) {
  await env.DB!.exec('ROLLBACK');
  throw e;
}
```

D1 uses serializable isolation. See `d1-transactions-isolation.md`.

### Pagination with cursor

```typescript
const cur = url.searchParams.get('cursor');
let cursorSql = '';
const cursorBinds: unknown[] = [];
if (cur) {
  const { ts, id } = decodeCursor(cur);
  cursorSql = ' AND (created_at, id) < (?, ?)';
  cursorBinds.push(ts, id);
}
const rows = await env.DB!.prepare(
  `SELECT * FROM items WHERE tenant_id = ? ${cursorSql} ORDER BY created_at DESC, id DESC LIMIT ?`
).bind(tenantId, ...cursorBinds, limit + 1).all<Item>();

const items = rows.results.slice(0, limit);
const nextCursor = rows.results.length > limit
  ? encodeCursor({ ts: items[items.length - 1].created_at, id: items[items.length - 1].id })
  : null;
```

## Gotchas

- **`env.DB!.prepare` vs `env.DB?.prepare`**: Use `!` (non-null assert) not `?.` (optional chain). If DB is missing, you want an error immediately, not a silent undefined.
- **`first()` returns `null`, not `undefined`**: Check `if (!row)` rather than `if (row === undefined)`.
- **Column names are lowercase**: SQLite column names returned by D1 match the schema exactly. Use lowercase in your generic type parameter.
- **Large inserts**: D1 has a 1MB row limit and a 25MB total request limit for D1 calls. Batch large inserts across multiple requests.
- **`last_insert_rowid`**: `.run()` returns `{ meta: { last_row_id: number } }` — useful for integer PKs but unnecessary when using UUID string PKs.

## Related

- `d1-best-practices.md`
- `d1-batch-bundler-bug.md`
- `d1-transactions-isolation.md`
- `d1-migration-best-practices.md`
- `workers-types-migration.md`
- `typescript-route-handler.md`
