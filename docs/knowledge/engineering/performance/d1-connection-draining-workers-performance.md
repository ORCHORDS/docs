# D1 Connection Draining Performance in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker performs D1 writes inside a Queues consumer or a cron handler. After a deploy
or a configuration change, in-flight queries are interrupted mid-transaction, leaving rows in an
inconsistent state and producing `D1_ERROR: database connection lost` errors. Alternatively,
high-throughput batch writers see elevated `SQLITE_BUSY` errors during rolling deploys.

---

## Context

D1 runs on SQLite over a distributed storage layer proxied through Cloudflare's network. Each
Worker isolate holds a logical connection. Unlike a persistent Node.js server, Workers isolates
are evicted without a pre-drain signal. When a new deployment is pushed, the platform terminates
the previous isolate generation after in-flight requests finish — but "in-flight" means the HTTP
response, not any background `waitUntil` work. Transactions that span multiple subrequests or that
rely on `waitUntil` for commit can be torn mid-flight.

---

## Graceful Write Flush with `waitUntil`

Commit the transaction before returning the response. Never defer D1 writes to `waitUntil` when
correctness depends on the write completing before the isolate is evicted.

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Correct: commit before response.
    await env.DB.prepare(
      'INSERT INTO events (id, payload) VALUES (?, ?)',
    )
      .bind(crypto.randomUUID(), await request.text())
      .run();

    return new Response('ok');

    // WRONG pattern (do not do this):
    // ctx.waitUntil(env.DB.prepare('INSERT ...').run());
    // return new Response('ok');
  },
};
```

Reserve `waitUntil` for truly fire-and-forget analytics writes where partial loss is acceptable.

---

## Idempotent Writes for Deploy Safety

Make inserts idempotent with `INSERT OR IGNORE` or `ON CONFLICT DO NOTHING`. During rolling
deploys, the same message may be processed by both old and new isolate generations.

```typescript
async function upsertEvent(db: D1Database, id: string, payload: string): Promise<void> {
  await db
    .prepare(
      `INSERT INTO events (id, payload, created_at)
       VALUES (?, ?, unixepoch())
       ON CONFLICT(id) DO NOTHING`,
    )
    .bind(id, payload)
    .run();
}
```

Pair this with a deterministic `id` derived from the source event (e.g., a Queues message ID) so
re-delivery after an isolate eviction produces no duplicate rows.

---

## Batch Commit to Reduce Window Exposure

A transaction that commits in one subrequest is safer than one spread across multiple round-trips.
D1 `batch()` executes all statements atomically on the same logical connection.

```typescript
async function drainBatch(
  db: D1Database,
  rows: Array<{ id: string; data: string }>,
): Promise<void> {
  const stmts = rows.map((r) =>
    db
      .prepare('INSERT OR IGNORE INTO events (id, data) VALUES (?, ?)')
      .bind(r.id, r.data),
  );

  // Single round-trip, single atomic commit — no partial state if isolate evicts.
  await db.batch(stmts);
}
```

`batch()` reduces total subrequest count from N to 1, cutting the window during which an eviction
could interrupt the operation.

---

## Detecting Draining Errors and Retrying

`D1_ERROR` with a connection-lost message should be retried with exponential back-off. Distinguish
transient drain errors from schema errors (which should not be retried).

```typescript
const RETRIABLE = /connection lost|database connection|SQLITE_BUSY/i;

async function withRetry<T>(fn: () => Promise<T>, maxAttempts = 3): Promise<T> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!RETRIABLE.test(msg) || attempt === maxAttempts) throw err;
      // Simple exponential back-off; Workers allow up to 30 s wall time.
      await new Promise((r) => setTimeout(r, 50 * 2 ** attempt));
    }
  }
  throw new Error('unreachable');
}

// Usage:
await withRetry(() => env.DB.prepare('INSERT OR IGNORE INTO t VALUES (?)').bind(id).run());
```

---

## Queue-Based Write Drain Pattern

For high-throughput scenarios, funnel writes through a Queues consumer with `autoRetry` enabled.
The consumer processes batches with a single `db.batch()` call, and the Queue guarantees
at-least-once delivery across deployments.

```typescript
// queue consumer (workers_dev = false, queue binding)
export default {
  async queue(batch: MessageBatch<{ id: string; data: string }>, env: Env): Promise<void> {
    const stmts = batch.messages.map((m) =>
      env.DB.prepare('INSERT OR IGNORE INTO events (id, data) VALUES (?, ?)').bind(
        m.body.id,
        m.body.data,
      ),
    );
    await env.DB.batch(stmts);
    batch.ackAll(); // ack only after successful commit
  },
};
```

The Queue consumer itself can be evicted, but the unacked messages are redelivered automatically,
making this pattern safe across rolling deploys.

---

## Anti-patterns

- **Long multi-statement transactions split across `fetch` subrequests**: Each subrequest is a separate logical connection; you cannot hold a transaction open across them.
- **Committing in `waitUntil` for critical data**: `waitUntil` work is best-effort — the platform may terminate it immediately on new deploys.
- **Retrying schema errors**: `SQLITE_CONSTRAINT` (duplicate key without `OR IGNORE`) indicates a logic bug, not a transient failure; retrying makes it worse.
- **Unbounded retry loops**: Without a maximum attempt count, a permanent error causes infinite retries and CPU exhaustion.

---

## Gotchas

- D1 does not expose a "connection drain" lifecycle event to Workers; there is no `onDrain` hook.
- `SQLITE_BUSY` can occur not only during eviction but also during WAL checkpoints; the retry strategy above handles both.
- `batch()` has a limit of **100 statements** per call; split larger batches into 100-statement chunks.
- Errors from individual statements inside a `batch()` abort the entire batch — wrap in try/catch and inspect `results[i].error` for per-statement diagnosis.

---

## Verification

```bash
# Watch for connection-lost errors in real time:
wrangler tail --format=pretty | grep -i "connection lost\|SQLITE_BUSY"

# Check D1 metrics for error rate spikes during deploys:
# Cloudflare Dashboard → Workers & Pages → D1 → [database] → Metrics → Errors
```

Deploy with `wrangler deploy --minify` and immediately run a write-heavy load test; the retry
wrapper should absorb any `SQLITE_BUSY` spikes without surfacing errors to callers.

---

## Related

- `d1-batch-query-performance-optimization.md`
- `d1-transaction-retry-optimistic-locking.md`
- `d1-wal-mode-write-throughput.md`
- `queues-consumer-backpressure-flow-control.md`
- `workers-waituntil-background-processing.md`

---

## Sources

- Cloudflare D1 — Errors and limits: https://developers.cloudflare.com/d1/platform/errors/
- Cloudflare D1 — Batch statements: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Workers — Lifecycle (`waitUntil`): https://developers.cloudflare.com/workers/runtime-apis/context/
- Cloudflare Queues — Consumer retries: https://developers.cloudflare.com/queues/reference/consumer-concurrency/
