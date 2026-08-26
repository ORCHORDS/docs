# D1 WAL Mode and Read Performance in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project / example.com sees read latency spikes when concurrent Worker invocations hit the same
D1 database simultaneously — a write operation blocks reads because the default SQLite DELETE
journal mode takes an exclusive lock. Switching to WAL (Write-Ahead Logging) mode allows readers
and a single writer to proceed concurrently without blocking each other, reducing p99 read latency
under mixed workloads.

## Context

Cloudflare D1 provisions each database as a SQLite file that runs in WAL mode by default for new
databases created after mid-2023. For databases created earlier, or when validating current
configuration, WAL mode should be explicitly verified. D1's read replica infrastructure (available
in paid plans) additionally distributes read traffic across regional replicas, complementing WAL's
concurrency benefits. Workers can query D1 with the Sessions API to route reads to the nearest
replica while ensuring read-your-writes consistency after mutations.

## WAL Mode Internals Relevant to D1

In WAL mode, writes append to a separate WAL file instead of overwriting pages in the main
database file. Readers see a consistent snapshot of the database as of the last committed
checkpoint without waiting for writers to finish. Key properties:

- Multiple simultaneous readers are always permitted
- One writer at a time (SQLite is not a multi-writer engine)
- Readers do not block writers and writers do not block readers
- The WAL file is checkpointed (folded back into the main DB) automatically

D1 manages checkpointing internally; Workers cannot and should not call `PRAGMA wal_checkpoint`
manually — D1's infrastructure handles this transparently.

## Verifying WAL Mode on a D1 Database

```typescript
export interface Env {
  DB: D1Database;
}

export async function checkJournalMode(env: Env): Promise<string> {
  const row = await env.DB.prepare(`PRAGMA journal_mode`)
    .first<{ journal_mode: string }>();
  // Expected: 'wal'
  console.log('journal_mode:', row?.journal_mode);
  return row?.journal_mode ?? 'unknown';
}
```

```bash
# Via Wrangler CLI
npx wrangler d1 execute example project-prod --command "PRAGMA journal_mode"
```

If the result is `delete` rather than `wal`, enable WAL mode with:

```bash
npx wrangler d1 execute example project-prod --command "PRAGMA journal_mode = WAL"
```

Note: D1 does not persist pragma changes across connections the same way a local SQLite file
does. For D1, WAL mode is set at the infrastructure level. Verify with Cloudflare support if
`PRAGMA journal_mode` returns `delete` on a new database.

## Read-Your-Writes with D1 Sessions API

D1 read replicas serve reads from the replica closest to the Worker, which may lag slightly
behind the primary after a write. The Sessions API pins reads to a consistency token so a
Worker that just wrote sees its own writes on subsequent reads.

```typescript
interface Env {
  DB: D1Database;
}

export async function writeAndReadConsistently(
  env: Env,
  authorId: number,
  body: string
): Promise<{ id: number; body: string }> {
  // Open a D1 session for read-your-writes guarantee
  const session = env.DB.withSession('first-unconstrained');

  // Write on the primary
  const inserted = await session
    .prepare(`INSERT INTO posts(author_id, body, created_at) VALUES(?1, ?2, unixepoch()) RETURNING id`)
    .bind(authorId, body)
    .first<{ id: number }>();

  if (!inserted) throw new Error('Insert failed');

  // Subsequent reads within the same session see the write
  const post = await session
    .prepare(`SELECT id, body FROM posts WHERE id = ?1`)
    .bind(inserted.id)
    .first<{ id: number; body: string }>();

  return post!;
}
```

Pass the session bookmark across HTTP requests to maintain consistency across Worker invocations:

```typescript
// Worker A: write and return bookmark
export async function handleWrite(request: Request, env: Env): Promise<Response> {
  const session = env.DB.withSession('first-unconstrained');
  await session.prepare(`INSERT INTO posts(author_id, body) VALUES(1, 'hello')`).run();
  const bookmark = session.getBookmark();
  return Response.json({ bookmark });
}

// Worker B: read with consistency from bookmark
export async function handleRead(
  request: Request,
  env: Env,
  bookmark: string
): Promise<Response> {
  const session = env.DB.withSession(bookmark);
  const { results } = await session.prepare(`SELECT * FROM posts ORDER BY created_at DESC LIMIT 10`).all();
  return Response.json(results);
}
```

## Optimizing Read Throughput Under Concurrent Workers

WAL allows concurrent reads but all writes still serialize. Structure the application to batch
writes and keep write transactions short:

```typescript
// GOOD: batch multiple writes into one transaction
export async function batchInsertReactions(
  env: Env,
  reactions: Array<{ postId: number; userId: number; emoji: string }>
): Promise<void> {
  const stmts = reactions.map((r) =>
    env.DB.prepare(`
      INSERT OR IGNORE INTO reactions(post_id, user_id, emoji, created_at)
      VALUES(?1, ?2, ?3, unixepoch())
    `).bind(r.postId, r.userId, r.emoji)
  );
  await env.DB.batch(stmts);
}

// GOOD: read-only queries need no transaction overhead
export async function getReactionCounts(
  env: Env,
  postId: number
): Promise<Array<{ emoji: string; count: number }>> {
  const { results } = await env.DB.prepare(`
    SELECT emoji, COUNT(*) AS count
    FROM   reactions
    WHERE  post_id = ?1
    GROUP  BY emoji
    ORDER  BY count DESC
  `)
    .bind(postId)
    .all<{ emoji: string; count: number }>();
  return results;
}
```

## WAL Checkpoint Behavior and Storage

D1 checkpoints its WAL file automatically. The WAL file grows with uncommitted or un-checkpointed
writes and is folded back when the checkpoint threshold is reached. Workers should not assume any
specific WAL file size limit; D1's managed SQLite handles this transparently.

```sql
-- Inspect WAL-related page info (informational only, cannot change checkpoint policy)
PRAGMA page_size;
PRAGMA page_count;
PRAGMA freelist_count;
```

## Anti-patterns

- Calling `PRAGMA journal_mode = DELETE` inside a Worker to revert to delete mode — D1 manages journal mode at the infrastructure level; this may fail or have no effect
- Opening explicit `BEGIN EXCLUSIVE` transactions for read-only operations — this blocks all other readers even in WAL mode
- Relying on `PRAGMA wal_checkpoint(TRUNCATE)` in a Worker — D1 does not expose checkpoint control to application code
- Holding long-running transactions open across multiple `await` calls — each `await` yields the event loop; keep transactions in a single `env.DB.batch()` call

## Gotchas

- D1's `withSession()` is not available in local development with `wrangler dev --local` — test session-based consistency against `--remote` or in a staging environment
- `first-unconstrained` is the weakest consistency level; use a stored bookmark for strict read-your-writes after cross-request hops
- WAL mode does not eliminate write contention — if a Worker holds a write transaction open, all other writers queue; keep write transactions short
- D1 read replicas are a paid feature; free-tier databases route all reads to the primary, making WAL's concurrency benefit local to a single connection

## Verification

```typescript
// Verify WAL mode and measure concurrent read latency
export async function benchmarkConcurrentReads(env: Env, n = 10) {
  const start = Date.now();
  const queries = Array.from({ length: n }, () =>
    env.DB.prepare(`SELECT COUNT(*) AS c FROM posts`).first<{ c: number }>()
  );
  const results = await Promise.all(queries);
  const elapsed = Date.now() - start;
  console.log(`${n} concurrent reads in ${elapsed}ms`, results.map((r) => r?.c));
}
```

```bash
# Confirm WAL mode via CLI
npx wrangler d1 execute example project-prod --command "PRAGMA journal_mode"
# Expected output: wal
```

## Related

- `/documentation/categories/database/sqlite-wal-mode.md`
- `/documentation/categories/database/sqlite-production-wal-litestream-edge.md`
- `/documentation/categories/database/d1-sessions-api-read-your-writes-workers.md`
- `/documentation/categories/database/d1-read-replicas-mobile-latency.md`
- `/documentation/categories/database/d1-batch-operations-performance.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/d1/build-with-d1/read-replicas/
- https://developers.cloudflare.com/d1/reference/d1-session-api/
- https://www.sqlite.org/wal.html
- https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/
