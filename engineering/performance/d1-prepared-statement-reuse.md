# D1 Prepared Statement Reuse Optimization

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

D1 queries that run on every request show higher CPU time than expected. Profiling reveals that
statement parsing and planning account for 10–30 % of total query duration, and the same SQL
templates are compiled repeatedly across Worker invocations handling identical query shapes.

## Context

Cloudflare D1 is an SQLite-compatible edge database accessed via the Workers binding API. Each
call to `db.prepare(sql)` sends the SQL string to D1 for parsing and compilation. While D1 caches
prepared statements server-side within a session, Worker isolates may not reuse the same
connection across invocations unless the isolate is kept warm. Caching the `D1PreparedStatement`
object at module scope lets a warm isolate skip re-parsing on subsequent requests.

---

## 1. Module-scope Prepared Statement Cache

Define statements at the top level of the Worker module. Warm isolates reuse the compiled object
without re-parsing.

```typescript
import type { D1Database, D1PreparedStatement } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
}

// Lazily initialised per-isolate cache – avoids binding access at import time
const stmtCache = new Map<string, D1PreparedStatement>();

function getStmt(db: D1Database, sql: string): D1PreparedStatement {
  let stmt = stmtCache.get(sql);
  if (!stmt) {
    stmt = db.prepare(sql);
    stmtCache.set(sql, stmt);
  }
  return stmt;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const userId = new URL(request.url).searchParams.get('userId');
    const stmt = getStmt(
      env.DB,
      'SELECT id, name, email FROM users WHERE id = ?1 LIMIT 1',
    );
    const row = await stmt.bind(userId).first();
    return Response.json(row ?? null);
  },
};
```

## 2. Named Statement Registry for Multi-query Workers

For Workers with many query shapes, maintain a typed registry to avoid SQL string literals
scattered across the codebase.

```typescript
const SQL = {
  GET_USER:     'SELECT id, name FROM users WHERE id = ?1',
  LIST_POSTS:   'SELECT id, title FROM posts WHERE user_id = ?1 ORDER BY created_at DESC LIMIT ?2',
  INSERT_EVENT: 'INSERT INTO events (user_id, type, ts) VALUES (?1, ?2, ?3)',
} as const;

type SqlKey = keyof typeof SQL;

const registry = new Map<SqlKey, D1PreparedStatement>();

function stmt(db: D1Database, key: SqlKey): D1PreparedStatement {
  let s = registry.get(key);
  if (!s) {
    s = db.prepare(SQL[key]);
    registry.set(key, s);
  }
  return s;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === '/user') {
      const id = new URL(request.url).searchParams.get('id');
      const user = await stmt(env.DB, 'GET_USER').bind(id).first();
      return Response.json(user);
    }

    if (pathname === '/posts') {
      const userId = new URL(request.url).searchParams.get('userId');
      const posts = await stmt(env.DB, 'LIST_POSTS').bind(userId, 20).all();
      return Response.json(posts.results);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## 3. Batch Execution with Prepared Statements

`db.batch()` groups multiple prepared statement calls into a single round-trip, combining the
benefits of statement reuse and network efficiency.

```typescript
async function recordUserActivity(
  userId: string,
  events: Array<{ type: string; ts: number }>,
  env: Env,
): Promise<void> {
  const insertStmt = getStmt(
    env.DB,
    'INSERT INTO events (user_id, type, ts) VALUES (?1, ?2, ?3)',
  );

  // Build bound instances – the base PreparedStatement is reused
  const bound = events.map((e) =>
    insertStmt.bind(userId, e.type, e.ts),
  );

  await env.DB.batch(bound);
}
```

## 4. First-request Warm-up Pattern

Pre-build all statements during the first request to ensure subsequent calls never pay the
compile cost, even if the isolate rotates.

```typescript
let warmedUp = false;

async function warmStatements(db: D1Database) {
  if (warmedUp) return;
  for (const sql of Object.values(SQL)) {
    getStmt(db, sql); // populate registry
  }
  warmedUp = true;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    await warmStatements(env.DB);
    // ... handler logic
    return new Response('ok');
  },
};
```

---

## Anti-patterns

- **`db.prepare()` inside a loop** – compiling the same SQL on every iteration pays the parse
  cost N times; hoist to module scope or use `db.batch()`.
- **Dynamic SQL string concatenation** – concatenating user values into the SQL string defeats
  caching (each unique string is a distinct cache key) and opens SQL injection risk; always use
  `?1` positional parameters.
- **Assuming statements are worker-global** – the cache is per-isolate, not per-account. Cold
  starts will miss the cache; design p99 budgets to tolerate occasional first-compile latency.
- **Storing stale prepared statements after schema migration** – a schema change (ALTER TABLE,
  new index) can make a cached statement reference obsolete columns; deploy code reloads clear
  the isolate cache naturally.

## Gotchas

- D1 prepared statements are tied to the `D1Database` binding instance. Storing a statement
  derived from one binding and using it with a different binding in tests will throw.
- `stmt.bind()` returns a new `D1PreparedStatement` (bound copy); the original is immutable and
  safe to reuse across requests.
- D1 is in SQLite compatibility mode; `RETURNING` clause is supported in recent D1 versions but
  may not be available in all regions on older builds.
- The module-scope map persists for the lifetime of the isolate, which is typically minutes.
  Do not store user-specific data in it.

## Verification

Use the D1 `meta` object returned by `.run()` to measure per-statement CPU:

```typescript
const result = await stmt(env.DB, 'GET_USER').bind(userId).run();
console.log(
  `rows: ${result.results.length}, duration: ${result.meta.duration} ms`,
);
```

Compare `.meta.duration` for a cold prepare vs. a warm reuse. Expect ≥ 20 % reduction on
warm isolates for simple OLTP queries.

## Related

- `d1-batch-query-performance-optimization.md`
- `d1-query-performance-explain-index.md`
- `workers-cpu-time-optimization.md`

## Sources

- https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://developers.cloudflare.com/d1/observability/metrics-and-analytics/
