# D1 Batch Size Limit Exceeded Postmortem

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A nightly data sync Worker attempted to upsert 12,000 rows into a D1 database using a
single `db.batch()` call. The Worker threw `Error: Too many statements in batch` and
terminated without committing any rows. The failure was silent for three days because the
Worker's error was swallowed in a fire-and-forget `ctx.waitUntil` block with no alerting.
When the missing data was discovered, the ops team had no insight into how many nights of
syncs had failed.

## Context

Cloudflare D1's `db.batch()` API executes a list of prepared statements atomically inside
a single SQLite transaction. As of mid-2026 the platform enforces a hard limit of
**100 statements per batch call**. There is no pagination or continuation token; the entire
batch is either accepted or rejected. D1 also imposes a maximum row size of 1 MB and a
single-query result set cap of 10,000 rows. Applications that were built while D1 was in
beta often inherited batch patterns that worked during low-traffic testing but broke at
production data volumes.

## Chunk the Batch Into Pages of at Most 100 Statements

Split large arrays of upserts into slices that stay within the statement limit and issue
them as sequential batch calls within the same Worker invocation.

```typescript
// src/lib/d1-batch-chunked.ts
export async function batchInChunks(
  db: D1Database,
  statements: D1PreparedStatement[],
  chunkSize = 90, // stay under the 100-statement limit with a safety margin
): Promise<D1Result[]> {
  const results: D1Result[] = [];
  for (let i = 0; i < statements.length; i += chunkSize) {
    const chunk = statements.slice(i, i + chunkSize);
    const chunkResults = await db.batch(chunk);
    results.push(...chunkResults);
  }
  return results;
}
```

## Build Statements Lazily to Avoid Memory Spikes

Constructing 12,000 prepared statement objects up front before chunking holds all bound
parameters in memory simultaneously. Use a generator to build and flush each chunk.

```typescript
// src/lib/d1-upsert-generator.ts
export async function* upsertChunks(
  db: D1Database,
  rows: ReadonlyArray<{ id: string; payload: string }>,
  chunkSize = 90,
): AsyncGenerator<D1Result[]> {
  const stmt = db.prepare(
    'INSERT INTO events (id, payload) VALUES (?1, ?2) ON CONFLICT(id) DO UPDATE SET payload = ?2',
  );
  let chunk: D1PreparedStatement[] = [];
  for (const row of rows) {
    chunk.push(stmt.bind(row.id, row.payload));
    if (chunk.length === chunkSize) {
      yield await db.batch(chunk);
      chunk = [];
    }
  }
  if (chunk.length > 0) yield await db.batch(chunk);
}
```

## Structured Error Handling in waitUntil Blocks

Errors thrown inside `ctx.waitUntil` are not surfaced to the client and are easily missed.
Wrap any sync operation with explicit error capture and alerting.

```typescript
// src/sync-worker.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(
      runSync(env).catch((err) => {
        console.error('[sync] fatal error', { message: (err as Error).message });
        // forward to an alerting endpoint so ops is paged, not surprised
        return fetch(env.ALERT_WEBHOOK, {
          method: 'POST',
          body: JSON.stringify({ error: (err as Error).message, ts: Date.now() }),
        });
      }),
    );
  },
} satisfies ExportedHandler<Env>;

async function runSync(env: Env): Promise<void> {
  const rows = await fetchRowsFromUpstream(env);
  for await (const results of upsertChunks(env.DB, rows)) {
    const failed = results.filter((r) => !r.success);
    if (failed.length > 0) throw new Error(`${failed.length} chunk statements failed`);
  }
}
```

## Checkpoint Progress for Long Syncs

Workers have a 30-second CPU time limit (Paid plan) and a 15-minute wall-clock limit on
Cron Triggers. For datasets larger than a single Worker invocation can handle, persist a
cursor in D1 itself so the next Cron invocation resumes where the previous one left off.

```typescript
// src/lib/sync-cursor.ts
export async function readCursor(db: D1Database): Promise<string | null> {
  const row = await db
    .prepare('SELECT value FROM sync_meta WHERE key = ?1')
    .bind('cursor')
    .first<{ value: string }>();
  return row?.value ?? null;
}

export async function writeCursor(db: D1Database, cursor: string): Promise<void> {
  await db
    .prepare(
      'INSERT INTO sync_meta (key, value) VALUES (?1, ?2) ON CONFLICT(key) DO UPDATE SET value = ?2',
    )
    .bind('cursor', cursor)
    .run();
}
```

## Row-Count Assertion After Batch

After each chunked batch, assert that the number of rows changed matches the expected
count. A mismatch indicates a constraint violation or silent skip that `d1.batch()` may
return as a non-error result.

```typescript
// src/lib/assert-rows-changed.ts
export function assertRowsChanged(
  results: D1Result[],
  expectedTotal: number,
): void {
  const changed = results.reduce((sum, r) => sum + (r.meta.changes ?? 0), 0);
  if (changed !== expectedTotal) {
    throw new Error(
      `Expected ${expectedTotal} row changes but got ${changed}; check for constraint violations`,
    );
  }
}
```

## Anti-patterns

- Calling `db.batch()` with an unbounded array built from user-supplied or upstream data
  — always validate or cap length before passing to `batch()`.
- Ignoring `D1Result.success` per statement — batch resolves even when individual
  statements fail if the error is non-fatal at the SQLite level.
- Assuming batch atomicity across chunks — each `db.batch(chunk)` call is its own
  transaction; a failure in chunk 3 leaves chunks 1 and 2 committed.
- Using `db.exec()` with a multi-statement SQL string as a workaround — this bypasses
  prepared statement safety and is not atomic.

## Gotchas

- The 100-statement limit applies per `batch()` call, not per Worker invocation; you can
  call `batch()` many times in one Worker.
- `D1Result.meta.changes` counts rows modified, not rows in the statement; an upsert that
  hits the `DO NOTHING` conflict path counts as 0 changes.
- D1 in beta had higher or undocumented batch limits; code written then may silently exceed
  the GA limit when production data grows.
- Cross-chunk failures leave a partial write. Design your schema so partially applied syncs
  are detectable (e.g., a `sync_batch_id` column) and re-runnable idempotently.

## Verification

1. Unit-test `batchInChunks` with an array of 101 mock statements and assert it calls
   `db.batch` twice with lengths 90 and 11.
2. In a staging D1 database, attempt a raw `db.batch()` with 101 statements and confirm
   the platform throws the expected error.
3. Run the sync Worker against a staging database containing 10,000 rows and verify all
   rows are present after completion without errors.
4. Kill the Worker mid-sync (via a thrown error after chunk 2) and confirm the next run
   resumes correctly from the saved cursor.

## Related

- `d1-migration-rollback-failed-production-lesson.md`
- `d1-write-contention-viral-event-postmortem.md`
- `silent-data-loss-partial-writes.md`
- `queue-consumers-must-be-idempotent.md`

## Sources

- Cloudflare D1 documentation — limits and known issues (2026)
- Cloudflare Community: "D1 batch statement limit" discussion thread
- Internal postmortem: example.com nightly sync failure, Q2 2026
- SQLite documentation — transaction semantics
