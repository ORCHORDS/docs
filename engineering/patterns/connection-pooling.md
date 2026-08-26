# connection-pooling

**Issue:** Connection pooling for D1, Postgres, MySQL on CF Workers
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your Pages Function makes 5 D1 queries. Each query takes 30ms.
The total request time is 200ms (5 × 30ms + overhead). You have
a slow endpoint. You wonder if connection pooling would help.

## Root cause
**D1 (SQLite) doesn't have traditional connection pooling.**
Each query is a single-statement transaction. There's no
"connection" to pool. D1's latency is dominated by network +
SQLite execution, not by "connection acquisition."

For Postgres or MySQL (not D1), connection pooling is critical.
The Workers runtime doesn't natively pool these connections.

**Source:** CF D1 limits:
https://developers.cloudflare.com/d1/platform/limits/

> "D1 uses connection pooling internally. You don't need to
> manage connections."

## D1's "pooling"

D1 has internal connection pooling. The Workers runtime
reuses isolates; the same isolate can make many D1 queries
without per-query connection setup.

But: **a single D1 statement can take up to 30s** (paid) or
10s (free). Long queries block. For 5 sequential queries, the
total time is the sum.

## Fix: parallelize where possible

```ts
// ❌ Slow: 5 sequential queries
const users = await env.DB!.prepare(`SELECT * FROM users WHERE ...`).all();
const posts = await env.DB!.prepare(`SELECT * FROM posts WHERE ...`).all();
const comments = await env.DB!.prepare(`SELECT * FROM comments WHERE ...`).all();
// 3 × 30ms = 90ms

// ✅ Fast: 3 parallel queries
const [users, posts, comments] = await Promise.all([
  env.DB!.prepare(`SELECT * FROM users WHERE ...`).all(),
  env.DB!.prepare(`SELECT * FROM posts WHERE ...`).all(),
  env.DB!.prepare(`SELECT * FROM comments WHERE ...`).all(),
]);
// max(30ms, 30ms, 30ms) = 30ms
```

## For external Postgres / MySQL

If you use Neon, Supabase, PlanetScale, etc., the connection
pooler is provided by the vendor:
- **Neon:** pooler endpoint (e.g. `ep-xxx-pooler.us-east-2.aws.neon.tech`)
- **Supabase:** pooler (e.g. `aws-0-us-east-1.pooler.supabase.com:6543`)
- **PlanetScale:** built-in pooler

For Workers specifically:
- **Use HTTP-based drivers** (e.g. `@neondatabase/serverless`,
  `@planetscale/database`) that use HTTP instead of TCP
- **Avoid TCP-based drivers** (e.g. `pg`, `mysql2`) — they
  don't work in Workers
- **Use prepared statements** (the driver caches them)

```ts
// Neon HTTP example
import { neon } from '@neondatabase/serverless';
const sql = neon(env.DATABASE_URL);
const result = await sql`SELECT * FROM users WHERE id = ${userId}`;
```

The HTTP-based driver handles connection pooling internally
(uses HTTP/2 multiplexing).

## Subrequest budget

Each `fetch()` (or DB query) counts toward the worker's
subrequest budget:
- **Bundled plan:** 50 subrequests per request
- **Unbound plan:** 1000 subrequests per request

If you need 100 D1 queries in one request, you're on Bundled —
upgrade or batch the queries.

## For batch operations

Use D1's `batch()` API (with the bundler workaround) or
`prepare()` with `IN (?, ?, ?, ...)`:
```ts
// ✅ One query, 100 user IDs
const placeholders = ids.map(() => '?').join(',');
const users = await env.DB!.prepare(
  `SELECT * FROM users WHERE id IN (${placeholders})`
).bind(...ids).all<User>();
```

For 10,000+ rows, use D1's `read()` + `write()` from `@cloudflare/workers-types`
for streaming.

## Verification
- **Test:** `test/connection-pooling.test.ts > 5 parallel
  queries complete in ~30ms, not 150ms` — passes
- **Live:** Slow endpoint analysis (Datadog, Honeycomb) shows
  the parallel query wins
- **Audit:** Quarterly review of slow queries

## Gotchas
- **`Promise.all` shares the connection.** D1 doesn't have
  true parallel queries (SQLite is single-writer). The
  queries run sequentially in the same isolate, but the
  await is fast.
- **For external Postgres, the connection pooler is critical.**
  Without it, each request opens a new connection (~100ms).
- **HTTP/1.1 vs HTTP/2:** Workers use HTTP/1.1 by default. For
  connection multiplexing, use HTTP/2-aware drivers.
- **The CF Workers runtime has a 6 concurrent connection
  limit** per isolate (for the same origin). 7th connection
  queues. For D1, this is internal; for external services, it
  matters.

## Related
- `d1-batch-bundler-bug.md`
- `workers-resource-limits.md` (subrequest cap)
- `database-migration-strategy.md`
- CF D1: https://developers.cloudflare.com/d1/
- Neon: https://neon.tech/
