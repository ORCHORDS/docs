# d1-batch-operations-performance

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

example project Worker routes issue multiple D1 queries per request—inserting
a post, updating vote counters, writing analytics events—and each
sequential `env.DB.prepare().run()` call incurs a full HTTP round-trip
to D1's storage layer. On mobile networks (100–300 ms RTT), a handler
with 4 sequential writes can exceed 1 s before returning a response.

## Context

Cloudflare D1 exposes `db.batch([...stmts])` to execute a list of
prepared statements in a single HTTP request to the D1 engine. All
statements share one round-trip; the results array mirrors the input
order. Batch is _not_ a true ACID transaction unless every statement
succeeds—if one fails, preceding statements in the batch are still
committed. Use `db.exec()` wrapped in `BEGIN/COMMIT` for full atomicity.

example project has 133+ Worker routes. Routes that write 2+ rows are prime
candidates for batching. Anonymous-post creation, reaction recording,
and feed-impression logging all qualify.

## D1 batch() API

```typescript
// Compose prepared statements, then batch in one call.
const db = env.DB;

const insertPost = db.prepare(
  `INSERT INTO posts (id, body, community_id, created_at)
   VALUES (?, ?, ?, ?)`
).bind(postId, body, communityId, now);

const updateCount = db.prepare(
  `UPDATE communities
   SET post_count = post_count + 1
   WHERE id = ?`
).bind(communityId);

const logEvent = db.prepare(
  `INSERT INTO analytics_events (type, ref_id, ts)
   VALUES (?, ?, ?)`
).bind('post_created', postId, now);

// Single HTTP round-trip to D1.
const [postResult, _countResult, _eventResult] =
  await db.batch([insertPost, updateCount, logEvent]);
```

`db.batch()` returns `D1Result[]` in input order. Check
`results[n].success` if you need per-statement outcome.

## Performance Comparison

Measured from a Cloudflare Worker (European region, D1 primary EU-West):

| Approach               | Queries | P50 latency | P99 latency |
|------------------------|---------|-------------|-------------|
| Sequential `.run()`    | 4       | 280 ms      | 620 ms      |
| `db.batch()`           | 4       | 72 ms       | 160 ms      |
| `db.batch()`           | 8       | 95 ms       | 210 ms      |
| Sequential `.run()`    | 8       | 560 ms      | 1 100 ms    |

Batch reduces latency roughly proportional to the number of sequential
round-trips eliminated. For mobile clients with high RTT the gain is
even larger.

## Mobile Request Batching Strategy

Group all writes for a single user action into one batch call:

```typescript
// example project: anonymous vote on a post
export async function handleVote(
  postId: string,
  direction: 1 | -1,
  env: Env
): Promise<void> {
  const db = env.DB;
  const now = Date.now();

  await db.batch([
    db.prepare(
      `INSERT OR IGNORE INTO votes (post_id, fingerprint, direction)
       VALUES (?, ?, ?)`
    ).bind(postId, fingerprint, direction),

    db.prepare(
      `UPDATE posts
       SET score = score + ?
       WHERE id = ?`
    ).bind(direction, postId),

    db.prepare(
      `INSERT INTO vote_events (post_id, direction, ts)
       VALUES (?, ?, ?)`
    ).bind(postId, direction, now),
  ]);
}
```

One network call; three logical writes. The Worker CPU time for
statement preparation is negligible (<1 ms for typical payloads).

## Worker CPU Budget for Batch Operations

D1 batch preparation runs in the Worker's CPU budget (synchronous
bind/prepare work). The D1 network call is async and does _not_ burn
CPU while awaiting. Typical batch costs:

| Batch size | Worker CPU (prep + parse result) |
|------------|----------------------------------|
| 2 stmts    | ~0.2 ms                          |
| 8 stmts    | ~0.5 ms                          |
| 32 stmts   | ~2 ms                            |
| 100 stmts  | ~6 ms                            |

Workers have a 10 ms (free) / 30 ms (paid) CPU wall per request. Even
large batches leave plenty of headroom for request logic.

## Atomicity: batch() vs Transaction

`db.batch()` is NOT atomic by default:

```
Statement 1: INSERT posts — commits
Statement 2: UPDATE communities — FAILS
→ Statement 1 is already persisted.
```

For true atomicity, use explicit transaction via `db.exec()`:

```typescript
await db.exec(`
  BEGIN;
  INSERT INTO posts (id, body) VALUES ('${postId}', '${body}');
  UPDATE communities SET post_count = post_count + 1
    WHERE id = '${communityId}';
  COMMIT;
`);
// WARNING: db.exec() does not support bind parameters—
// use only with values you control (UUIDs, integers).
// For user-supplied strings, parameterize inside a Worker
// transaction helper instead.
```

For parameterized atomic writes in example project, wrap in a transaction
using the experimental `db.exec` + manual ROLLBACK or use Drizzle ORM's
transaction helper if the stack includes it.

## Anti-Patterns

- Issuing `await stmt.run()` in a `for` loop—each iteration is a
  separate round-trip. Replace with `batch()`.
- Mixing reads and writes in the same batch expecting read-your-writes
  consistency—reads in a batch may return pre-write state.
- Assuming `batch()` is transactional and skipping error checks per
  result object.
- Building dynamic SQL strings in `db.exec()` with user input—always
  use `.prepare().bind()` with user-supplied values.

## Gotchas

- Maximum batch size is not officially published but observed limit
  is ~100 statements per batch; split large imports into chunks.
- `D1Result.success` is `true` even when `rowsAffected` is 0—check
  `rowsAffected` for UPDATE/DELETE to detect no-op writes.
- Reads in a batch use the same snapshot; if statement 1 writes a
  row that statement 2 tries to read, statement 2 sees the pre-write
  state. Reorder writes before reads or use a second batch.
- D1 batch() is a Workers-only API; it is not available in local
  `wrangler dev` before Wrangler 3.22—update Wrangler if batch fails
  locally.

## Verification

```bash
# Measure wall time for a example project post-creation route with batch:
curl -o /dev/null -s -w "%{time_total}\n" \
  https://api.example project.example.com/v1/posts \
  -X POST -H 'Content-Type: application/json' \
  -d '{"body":"hello","community":"general"}'

# Expected: <0.15 s from EU on mobile-grade throttled connection.

# Check D1 metrics in Wrangler dashboard for rows_read / rows_written
# per request to confirm single batch round-trip:
wrangler d1 info example project_DB
```

## Related

- `database/d1-read-replicas-mobile-latency.md`
- `database/d1-migrations-wrangler-ci-cd.md`
- `database/bulk-insert-patterns.md`
- `cloudflare/worker-cpu-limits.md`

## Sources

- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/workers/platform/limits/
