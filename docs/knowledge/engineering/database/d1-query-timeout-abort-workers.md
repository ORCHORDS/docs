# D1 Query Timeout and Abort Patterns in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Workers request hits a slow D1 query — a missing index, an unexpectedly large result set,
or a lock wait — and the Worker keeps running until Cloudflare terminates it at the 30-second
CPU-time wall. The client receives a 504 or an abrupt disconnect. Meanwhile the slow query
continues consuming D1 resources and blocks other requests.

You need to:
1. Bound the time any single query (or batch of queries) is allowed to run.
2. Return a graceful error to the caller before the Worker wall clock expires.
3. Avoid cascading slowdowns when a query backlog builds up.

## Context

Cloudflare Workers has two time limits relevant here:

- **CPU time limit**: 30 ms (free plan) or 30 s (paid/Enterprise) of *active* CPU time.
- **Wall-clock limit**: Workers can stay alive for up to 30 seconds (paid) but I/O
  (including D1 network round-trips) does not count against CPU time.

D1 itself does not expose a per-query timeout parameter. You must implement timeouts in the
Worker using JavaScript's `Promise.race()` or `AbortController`-style patterns combined with
the Workers `waitUntil` and fetch cancellation APIs.

Because D1 queries are network calls to the D1 HTTP endpoint (from the Worker's perspective),
a cancelled `fetch` on the Worker side will cause D1 to stop streaming results — but the
underlying SQLite statement may still run to completion on the D1 service side if it started
executing before cancellation. Design your timeout strategy accordingly.

## Implementing a Query Timeout Wrapper

```typescript
// lib/d1-timeout.ts

export class QueryTimeoutError extends Error {
  constructor(
    public readonly timeoutMs: number,
    public readonly query: string,
  ) {
    super(`D1 query timed out after ${timeoutMs}ms: ${query.slice(0, 120)}`);
    this.name = "QueryTimeoutError";
  }
}

/**
 * Race a D1 prepared-statement execution against a timeout.
 * Throws QueryTimeoutError if the query does not resolve within `timeoutMs`.
 */
export async function withQueryTimeout<T>(
  stmt: D1PreparedStatement,
  method: "first" | "all" | "run",
  timeoutMs: number,
): Promise<T> {
  const query = (stmt as unknown as { _query?: { sql?: string } })._query?.sql ?? "<unknown>";

  const timeout = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new QueryTimeoutError(timeoutMs, query)), timeoutMs)
  );

  let queryPromise: Promise<unknown>;
  switch (method) {
    case "first": queryPromise = stmt.first(); break;
    case "all":   queryPromise = stmt.all();   break;
    case "run":   queryPromise = stmt.run();   break;
  }

  return Promise.race([queryPromise, timeout]) as Promise<T>;
}
```

```typescript
// workers/search.ts
import { withQueryTimeout, QueryTimeoutError } from "../lib/d1-timeout";

const QUERY_TIMEOUT_MS = 5_000; // 5 seconds — well inside the 30s Worker wall clock

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const q = new URL(request.url).searchParams.get("q") ?? "";

    try {
      const result = await withQueryTimeout<D1Result<{ id: string; title: string }>>(
        env.DB.prepare(
          `SELECT id, title
           FROM   articles
           WHERE  title LIKE '%' || ? || '%'
           LIMIT  50`
        ).bind(q),
        "all",
        QUERY_TIMEOUT_MS,
      );

      return Response.json(result.results);
    } catch (err) {
      if (err instanceof QueryTimeoutError) {
        return Response.json(
          { error: "search is taking too long, try a more specific query" },
          { status: 503, headers: { "Retry-After": "5" } }
        );
      }
      throw err;
    }
  },
};
```

## Batch Timeout with AbortController

For multi-statement batches, wrap the entire `db.batch()` call:

```typescript
// lib/d1-batch-timeout.ts

export async function batchWithTimeout(
  db: D1Database,
  stmts: D1PreparedStatement[],
  timeoutMs: number,
): Promise<D1Result[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    // Workers fetch() respects AbortSignal on the underlying HTTP call.
    // D1's batch() does not currently accept a signal directly, so we
    // race against a rejection promise instead.
    const timeoutPromise = new Promise<never>((_, reject) => {
      controller.signal.addEventListener("abort", () =>
        reject(new Error(`D1 batch timed out after ${timeoutMs}ms`))
      );
    });

    return await Promise.race([db.batch(stmts), timeoutPromise]);
  } finally {
    clearTimeout(timer);
  }
}
```

## Per-Request Budget Pattern

Allocate a fixed time budget at the request entry point and pass remaining time into each
sub-operation. This prevents a slow first query from stealing time from subsequent queries.

```typescript
// lib/request-budget.ts
export class RequestBudget {
  private readonly deadline: number;

  constructor(totalMs: number) {
    this.deadline = Date.now() + totalMs;
  }

  remaining(): number {
    return Math.max(0, this.deadline - Date.now());
  }

  isExpired(): boolean {
    return this.remaining() === 0;
  }

  /** Throw if we're already over budget. */
  assertNotExpired(label: string): void {
    if (this.isExpired()) {
      throw new Error(`Request budget exhausted before: ${label}`);
    }
  }
}
```

```typescript
// workers/product-page.ts
import { RequestBudget } from "../lib/request-budget";
import { withQueryTimeout } from "../lib/d1-timeout";

const REQUEST_BUDGET_MS = 8_000;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const budget = new RequestBudget(REQUEST_BUDGET_MS);
    const productId = new URL(request.url).pathname.split("/").pop()!;

    // Query 1: product details (fast, index on primary key)
    budget.assertNotExpired("product fetch");
    const product = await withQueryTimeout<{ id: string; name: string; price: number } | null>(
      env.DB.prepare("SELECT id, name, price FROM products WHERE id = ?").bind(productId),
      "first",
      Math.min(2_000, budget.remaining()),
    );

    if (!product) return new Response("Not found", { status: 404 });

    // Query 2: related products (potentially slow without index)
    budget.assertNotExpired("related products fetch");
    let related: { id: string; name: string }[] = [];
    try {
      const result = await withQueryTimeout<D1Result<{ id: string; name: string }>>(
        env.DB.prepare(
          `SELECT id, name FROM products
           WHERE category_id = (SELECT category_id FROM products WHERE id = ?)
             AND id != ?
           LIMIT 6`
        ).bind(productId, productId),
        "all",
        Math.min(3_000, budget.remaining()),
      );
      related = result.results;
    } catch {
      // Non-fatal: degrade gracefully if related products are slow
      related = [];
    }

    return Response.json({ product, related, budgetRemainingMs: budget.remaining() });
  },
};
```

## Slow Query Logging via waitUntil

Use `ctx.waitUntil` to log slow queries to an analytics store without blocking the response:

```typescript
// lib/slow-query-logger.ts

const SLOW_QUERY_THRESHOLD_MS = 500;

export async function timedQuery<T>(
  ctx: ExecutionContext,
  env: { ANALYTICS: AnalyticsEngineDataset },
  label: string,
  fn: () => Promise<T>,
): Promise<T> {
  const start = Date.now();
  try {
    const result = await fn();
    const elapsed = Date.now() - start;

    if (elapsed >= SLOW_QUERY_THRESHOLD_MS) {
      ctx.waitUntil(
        Promise.resolve(
          env.ANALYTICS.writeDataPoint({
            indexes: [label],
            doubles: [elapsed],
            blobs: [new Date().toISOString()],
          })
        )
      );
    }

    return result;
  } catch (err) {
    const elapsed = Date.now() - start;
    ctx.waitUntil(
      Promise.resolve(
        env.ANALYTICS.writeDataPoint({
          indexes: [`${label}:error`],
          doubles: [elapsed],
          blobs: [String(err)],
        })
      )
    );
    throw err;
  }
}
```

```typescript
// workers/api.ts
import { timedQuery } from "../lib/slow-query-logger";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const rows = await timedQuery(ctx, env, "list_orders", () =>
      env.DB.prepare("SELECT id, total FROM orders ORDER BY created_at DESC LIMIT 20")
        .all<{ id: string; total: number }>()
        .then((r) => r.results)
    );

    return Response.json(rows);
  },
};
```

## Circuit Breaker for D1 Under Load

A simple in-memory circuit breaker prevents hammering D1 when it is already slow. Note that
Workers do not share memory across isolates, so each isolate has its own circuit state — this
pattern is most useful within a single Worker invocation chain.

```typescript
// lib/d1-circuit-breaker.ts

type CircuitState = "closed" | "open" | "half-open";

export class D1CircuitBreaker {
  private state: CircuitState = "closed";
  private failures = 0;
  private lastFailureAt = 0;

  constructor(
    private readonly failureThreshold = 5,
    private readonly resetAfterMs = 10_000,
  ) {}

  isOpen(): boolean {
    if (this.state === "open") {
      if (Date.now() - this.lastFailureAt >= this.resetAfterMs) {
        this.state = "half-open";
        return false;
      }
      return true;
    }
    return false;
  }

  recordSuccess(): void {
    this.failures = 0;
    this.state = "closed";
  }

  recordFailure(): void {
    this.failures++;
    this.lastFailureAt = Date.now();
    if (this.failures >= this.failureThreshold) {
      this.state = "open";
    }
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.isOpen()) {
      throw new Error("Circuit breaker open — D1 queries temporarily suspended");
    }
    try {
      const result = await fn();
      this.recordSuccess();
      return result;
    } catch (err) {
      this.recordFailure();
      throw err;
    }
  }
}

// Singleton per isolate — reset on cold start
export const dbBreaker = new D1CircuitBreaker(5, 10_000);
```

## Anti-patterns

**Setting a very short timeout (e.g. 100ms) on write operations.** Writes on D1 route to the
primary and may have higher latency than reads. Use separate timeout budgets for reads and
writes. A timed-out write may have already committed on D1 by the time the Worker rejects it.

**Relying on D1 to cancel the underlying SQLite statement.** Cancelling the Worker-side
`Promise` does not guarantee the SQLite query stops immediately. The D1 service may finish
executing the statement. Design around idempotency (UPSERT, RETURNING) rather than
assuming cancelled writes are always rolled back.

**Using `setTimeout(0)` polling loops to implement timeouts.** In Workers, `setTimeout`
callbacks run only between microtask boundaries. Use `Promise.race` with a single deferred
rejection instead.

**Logging every slow query synchronously.** Synchronous analytics writes add to the
critical-path latency. Always use `ctx.waitUntil` for non-blocking observability calls.

**Returning 500 on timeout.** Use `503 Service Unavailable` with a `Retry-After` header.
This signals downstream caches and clients to back off rather than retry immediately.

## Gotchas

- **D1 has its own internal statement timeout** (currently ~30 seconds on the service side).
  Your Worker timeout should be considerably shorter to leave room for response serialisation
  and other in-request work.

- **`Promise.race` leaks the losing promise.** The slow query promise does not get garbage
  collected immediately when the timeout wins. It will eventually resolve and be discarded,
  but it can hold memory for the duration of the Worker invocation. For long-lived isolates
  this is a minor concern; for high-throughput Workers monitor heap usage.

- **`Date.now()` is not monotonic in Workers.** In practice this is rarely an issue, but for
  high-precision timing consider `performance.now()` which is monotonic.

- **Batch statements in `db.batch()` execute in a single network round-trip.** The timeout
  for a batch should account for the total execution time of all statements in the batch, not
  just the first one.

- **Workers CPU time limit vs. wall-clock.** I/O await time (including D1 queries) does not
  count against CPU time. A query that takes 25 seconds still gives you your 30 ms of CPU.
  But wall-clock caps at 30 s total — budget accordingly.

## Verification

```typescript
// Verify that the timeout wrapper fires before the Worker wall clock
async function testQueryTimeout(env: Env): Promise<void> {
  const start = Date.now();

  try {
    // Simulate a slow query with a very short timeout
    await withQueryTimeout(
      // This query will not actually be slow in test, so mock by inserting a sleep pragma
      env.DB.prepare("SELECT unixepoch() FROM (WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM cnt WHERE x<1000000) SELECT x FROM cnt)"),
      "first",
      50, // 50ms timeout — should trigger on a large recursive query
    );
    console.error("FAIL: expected QueryTimeoutError");
  } catch (err) {
    const elapsed = Date.now() - start;
    console.assert(
      err instanceof Error && err.message.includes("timed out"),
      `Expected timeout error, got: ${err}`
    );
    console.assert(elapsed < 5_000, `Timeout fired too late: ${elapsed}ms`);
    console.log("query timeout: OK", { elapsed });
  }
}
```

## Related

- `d1-analyze-query-planner-workers.md` — identify slow queries before they time out
- `d1-sqlite-query-optimization.md` — index-level fixes for slow queries
- `d1-batch-operations-performance.md` — batching to reduce round-trips
- `d1-advisory-lock-pattern-workers.md` — avoiding lock wait timeouts
- `d1-sessions-api-read-your-writes-workers.md` — session-based query routing

## Sources

- Cloudflare Workers CPU and duration limits: https://developers.cloudflare.com/workers/platform/limits/
- D1 API reference: https://developers.cloudflare.com/d1/worker-api/d1-database/
- MDN AbortController: https://developer.mozilla.org/en-US/docs/Web/API/AbortController
- Promise.race semantics: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/race
