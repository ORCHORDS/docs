# d1-sessions-api

**Issue:** D1 global read replication only pays off if your Worker actually queries the replica near the user — and by default it does not. Queries issued through the plain D1 database API (`env.DB.prepare(...).first()`) always hit the primary, no matter how many replicas exist, so teams enable replication and see zero latency improvement. The D1 Sessions API (`env.DB.withSession(...)`) is the required mechanism for replica routing and is also how D1 expresses interactive transactions with read-your-writes semantics. Misusing sessions (sharing one across requests, fighting the automatic pinning) causes inconsistency bugs that are invisible in single-region testing. This article covers how sessions work, how pinning behaves, and the request-scoped patterns that avoid both pitfalls.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How sessions interact with replication

1. **Plain API means primary-only.** Without the Sessions API, every D1 query executes on the primary database. Replicas sit idle; this is documented behavior, not a bug. If you enabled read replication (`location_hint`, `read_replication: true` in wrangler config), you must also switch query paths to `withSession` to benefit.
2. **A session models one user interaction.** `env.DB.withSession(async session => { ... })` wraps the queries of a single logical interaction. The session tracks D1's internal sequencing bookkeeping so that a read served by a replica reflects at least everything the session previously wrote or read — read-your-writes across an eventually consistent replication fabric.
3. **Reads start lazily at the nearest replica.** The first query in a session is routed to the closest replica (or the primary if no replica is close enough). Subsequent reads can continue on the replica as long as no write pins the session.
4. **The first write pins the session to the primary.** Once a write executes, the session pins to the primary to preserve causality, and further reads in that session go to the primary. You can inspect this with `session.getCurrentlyPinnedDatabase()`, which returns the pinned database (or `null` while unpinned) — useful for logging how often your "read-heavy" endpoint actually pins.
5. **Lagging replicas are handled for you.** If the nearby replica has not caught up to the session's sequencing point, D1 routes that query to the primary automatically. You get correctness by default and speed when replication allows it.

## Interactive transactions

1. **Sessions are the transaction boundary.** Inside `withSession`, queries execute in an implicit interactive transaction: reads see a consistent snapshot, writes commit together at the end of the callback, and conflicting writes from other sessions fail fast rather than silently overwriting.
2. **Write conflicts throw.** If two sessions write the same rows, one transaction fails with a conflict error. Catch it in the Worker and either retry the session or surface a 409 — do not assume last-write-wins like the plain batch API.
3. **Use `withCompatSession` for transaction-API parity.** Code written against the older explicit `transaction()` API can be ported with `withCompatSession`, which exposes the same begin/commit-style semantics inside the sessions model. Prefer plain `withSession` for new code.
4. **Do not nest sessions.** Opening a second session on the same binding inside an active session creates two independent consistency contexts and double-pinning risk. One session per request, full stop.

## Best practices

1. **Create the session per HTTP request.** Open `withSession` at the top of your request handler, use `session.prepare(...)`/`session.batch(...)` throughout, and let it close when the handler returns. Never cache a session in a module global — global state persists across requests in a Worker isolate and a stale session leaks pinning and bookkeeping between users.
2. **Order reads before writes.** Since the first write pins to the primary, do all read-only work (auth checks, dashboard loads, list queries) before any mutation in the request. This maximizes replica-served reads; a request that writes first forfeits replica reads for the rest of the session.
3. **Batch inside sessions too.** `session.batch([...])` amortizes round trips exactly like `env.DB.batch`, with the session's consistency guarantees attached. Sequential single statements in a loop are the slowest possible pattern.
4. **Keep OLTP shape, push OLAP out.** Sessions and replicas accelerate point queries with modest result sets. For analytics over large ranges, use D1's `prepare` with `exec` exports, Time Travel for audits, or a Warehouse pipeline — not ad hoc session queries.
5. **Instrument pin behavior.** Log `getCurrentlyPinnedDatabase()` results (or enable D1 query logging in dev) to verify that read-heavy endpoints stay unpinned after deploy. A pinned session in a hot GET path almost always means a stray write (for example, last-seen updates) snuck into the read path.

## Failure modes and diagnostics

1. **Redirect loops in local dev.** `wrangler dev` simulates sessions locally; behavior differences between local and remote (especially around pinning) should be reported against the wrangler version rather than worked around with raw SQL strings.
2. **Replica reads returning older data across different sessions.** Read-your-writes holds within a session only. If session B must see session A's write (for example, write in one request, read in the next), route that follow-up read through a session that writes or accepts primary reads — cross-session freshness is eventual, on the order of the replication lag documented for D1.
3. **Migrations and sessions do not mix.** Schema changes via wrangler migrations or the dashboard run outside sessions. Long-lived sessions across a migration deploy can hit `SQLITE_ERROR` on changed columns — drain and retry requests rather than caching prepared statements in module scope.

## References

1. **D1 Global read replication.** developers.cloudflare.com/d1/best-practices/read-replication/ — replica routing and the sessions requirement.
2. **D1 Database API — Sessions.** developers.cloudflare.com/d1/worker-api/d1-database/ — `withSession`, `withCompatSession`, `getCurrentlyPinnedDatabase`.
3. **How D1 implements global read replication.** blog.cloudflare.com/d1-read-replication-beta/ — sequencing tokens and pinning design.
