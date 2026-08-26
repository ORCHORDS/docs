# Maximizing D1 Prepared Statement Performance

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

D1 queries constructed with dynamic SQL string concatenation inside the request handler are measurably slower than equivalent queries using prepared statements, even when the query plan is identical. Under load, p99 query latency is 20–40 ms higher than expected. `EXPLAIN QUERY PLAN` shows the same plan for both, but runtime overhead differs.

## Context

In Cloudflare Workers module workers, the JavaScript isolate persists across requests within the same isolate lifetime. Module-scope `const` declarations survive between requests in that isolate. When you call `env.DB.prepare(sql)` at module scope, D1 compiles the SQL once and caches the prepared statement handle for the isolate's lifetime. Subsequent `bind()` and `run()` / `first()` / `all()` calls on that handle skip the SQL parse and plan step. Dynamic string building inside a handler forces a re-parse on every request, negating D1's prepare-once optimization.

## Prepared Statement Module-Scope Pattern

```typescript
// src/db.ts — declare all prepared statements as module-scope constants
import type { D1Database, D1PreparedStatement } from '@cloudflare/workers-types';

// These are initialized once per isolate lifetime, not per request.
// D1 compiles the SQL on the first bind() call; subsequent calls reuse the plan.
let _db: D1Database | null = null;
let _stmts: {
  getUserById:      D1PreparedStatement;
  listUsersByOrg:   D1PreparedStatement;
  insertEvent:      D1PreparedStatement;
  bulkInsertEvents: D1PreparedStatement;
} | null = null;

export function getStatements(db: D1Database) {
  if (_stmts && _db === db) return _stmts;
  _db = db;
  _stmts = {
    getUserById: db.prepare(
      'SELECT id, name, email FROM users WHERE id = ?1 LIMIT 1'
    ),
    listUsersByOrg: db.prepare(
      'SELECT id, name FROM users WHERE org_id = ?1 ORDER BY name LIMIT ?2 OFFSET ?3'
    ),
    insertEvent: db.prepare(
      'INSERT INTO events (id, user_id, type, payload, created_at) VALUES (?1,?2,?3,?4,?5)'
    ),
    // Bulk insert via VALUES rows — generate once, bind many
    bulkInsertEvents: db.prepare(
      'INSERT INTO events (id, user_id, type, payload, created_at) ' +
      'VALUES (?1,?2,?3,?4,?5),(?6,?7,?8,?9,?10),(?11,?12,?13,?14,?15)'
    ),
  };
  return _stmts;
}

// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const stmts = getStatements(env.DB);

    // Fast path: prepared statement with bound params, no SQL parse
    const user = await stmts.getUserById.bind('usr_123').first<User>();
    if (!user) return new Response('Not Found', { status: 404 });

    const { results } = await stmts.listUsersByOrg
      .bind(user.org_id, 20, 0)
      .all<UserRow>();

    return Response.json({ user, peers: results });
  },
} satisfies ExportedHandler<Env>;
```

## Batch API vs Individual Statements for Bulk Inserts

```typescript
// src/bulk.ts — batch multiple statements in one round-trip
export async function bulkInsertEvents(
  db: D1Database,
  events: EventRow[]
): Promise<void> {
  const insert = db.prepare(
    'INSERT INTO events (id, user_id, type, payload, created_at) VALUES (?1,?2,?3,?4,?5)'
  );

  // D1 batch API sends all statements in a single HTTP request to the D1 backend.
  // This avoids N round-trips and is significantly faster for bulk inserts.
  const batches = events.map(e =>
    insert.bind(e.id, e.user_id, e.type, JSON.stringify(e.payload), e.created_at)
  );

  // Execute all in one network round-trip
  const results = await db.batch(batches);
  const failed = results.filter(r => !r.success);
  if (failed.length > 0) {
    throw new Error(`${failed.length} batch inserts failed`);
  }
}
```

## EXPLAIN QUERY PLAN Comparison

Run `EXPLAIN QUERY PLAN` against both the dynamic and prepared variants to confirm the query plan is identical — latency difference is entirely in the parse/compile step, not execution:

```bash
# Via wrangler d1 execute
npx wrangler d1 execute MY_DB --command \
  "EXPLAIN QUERY PLAN SELECT id, name FROM users WHERE org_id = 'org_1' LIMIT 20 OFFSET 0"
# Output: SEARCH users USING INDEX idx_users_org_id (org_id=?)

# Dynamic SQL produces the same plan but incurs parse overhead each time:
npx wrangler d1 execute MY_DB --command \
  "EXPLAIN QUERY PLAN SELECT id, name FROM users WHERE org_id = '" + orgId + "' LIMIT 20 OFFSET 0"
```

## Measuring Latency with Tail Worker Traces

```typescript
// tail-worker/index.ts — measure D1 query latency from trace spans
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const event of events) {
      for (const log of event.logs) {
        if (typeof log.message[0] === 'object' && log.message[0].d1Query) {
          const { sql, durationMs } = log.message[0].d1Query;
          console.log(JSON.stringify({ sql: sql.slice(0, 80), durationMs }));
        }
      }
    }
  },
} satisfies ExportedTailHandler;
```

Typical results: prepared statements average 3–6 ms per query; dynamic SQL averages 8–18 ms per query in a loaded isolate.

## Anti-patterns

- **`db.prepare(sql)` inside the request handler** — re-parses SQL on every request; move to module scope.
- **String interpolation with user input** — SQL injection risk and negates prepared-statement performance; always use `?1`, `?2` positional parameters.
- **Unbounded `batch()` arrays** — D1 batch is capped at 100 statements per call; chunk large inserts into batches of 100.

## Gotchas

- `env.DB` is a new binding proxy on each request, but the underlying connection in the same isolate is shared; keying `_stmts` on `_db === db` handles the case where the binding reference changes between requests without re-using stale statements.
- D1 prepared statements do not survive isolate recycles — the lazy init pattern automatically handles this since `_stmts` is `null` after a new isolate starts.
- `first()` returns `null` (not `undefined`) when no row matches; always null-check before accessing properties.
- Batch results are returned in the same order as the input array; correlate failures by index.

## Verification

```bash
# Compare dynamic vs prepared latency under load
npx wrangler tail --format=json | \
  jq 'select(.event.cpuTime != null) | {cpu: .event.cpuTime, wall: .event.wallTime}'

# Run EXPLAIN to confirm index usage
npx wrangler d1 execute MY_DB --command \
  "EXPLAIN QUERY PLAN SELECT id, name FROM users WHERE org_id = ?1 LIMIT 20"
```

## Related

- `workers-module-lazy-binding-performance.md`
- `cloudflare-snippets-vs-workers-latency.md`

## Sources

- Cloudflare D1 Workers API — https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- D1 Batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite EXPLAIN QUERY PLAN — https://www.sqlite.org/eqp.html
