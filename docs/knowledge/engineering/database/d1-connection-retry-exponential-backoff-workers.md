# D1 Connection Retry with Exponential Backoff — Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

D1 queries intermittently throw `D1_ERROR` or `network error` exceptions during traffic spikes, cold starts, or Cloudflare infrastructure hiccups. Re-throwing immediately to the client returns a 500; ignoring the failure loses writes. A systematic retry strategy with exponential backoff and jitter absorbs transient failures without overwhelming D1.

---

## Context

D1 operates over Cloudflare's internal network between the Worker and the D1 service. Unlike a persistent database connection that reconnects transparently, each D1 call in a Worker is an independent HTTP-like RPC. Transient failures include:

- **5xx from the D1 control plane** — rare but possible during deployments
- **`Too many requests`** — D1 rate limits per-account writes
- **Timeout on heavy queries** — WAL pressure, schema lock contention
- **Cold-start latency spikes** — first request to a regional D1 replica

Retrying on these is safe only for **idempotent** operations (reads, upserts) or operations wrapped in a transaction that will roll back on failure.

Key parameters:

| Parameter | Recommended default |
|---|---|
| `maxAttempts` | 3–5 |
| `baseDelayMs` | 200 ms |
| `maxDelayMs` | 10 000 ms |
| `backoffFactor` | 2 (doubles each attempt) |
| `jitterFactor` | 0.25 (±25% random spread) |

---

## Core Retry Utility

```typescript
// src/lib/d1-retry.ts

export interface RetryOptions {
  maxAttempts?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  backoffFactor?: number;
  jitterFactor?: number;
  /** Return true to retry on this error; false to throw immediately */
  isRetryable?: (err: unknown) => boolean;
}

const DEFAULT_OPTIONS: Required<RetryOptions> = {
  maxAttempts: 4,
  baseDelayMs: 200,
  maxDelayMs: 8000,
  backoffFactor: 2,
  jitterFactor: 0.25,
  isRetryable: isTransientD1Error,
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function computeDelay(
  attempt: number,
  opts: Required<RetryOptions>
): number {
  const exponential = opts.baseDelayMs * opts.backoffFactor ** attempt;
  const capped = Math.min(exponential, opts.maxDelayMs);
  // Full jitter: random in [base, capped * (1 + jitter)]
  const jitter = capped * opts.jitterFactor * Math.random();
  return Math.round(capped + jitter);
}

export function isTransientD1Error(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  return (
    msg.includes("d1_error") ||
    msg.includes("network error") ||
    msg.includes("too many requests") ||
    msg.includes("timeout") ||
    msg.includes("service unavailable") ||
    msg.includes("connection reset")
  );
}

/**
 * Execute an async operation with exponential backoff retry.
 * Throws the last error if all attempts are exhausted.
 */
export async function withRetry<T>(
  operation: (attempt: number) => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  let lastError: unknown;

  for (let attempt = 0; attempt < opts.maxAttempts; attempt++) {
    try {
      return await operation(attempt);
    } catch (err) {
      lastError = err;

      const isLast = attempt === opts.maxAttempts - 1;
      if (isLast || !opts.isRetryable(err)) {
        throw err;
      }

      const delay = computeDelay(attempt, opts);
      console.warn(
        `[d1-retry] Attempt ${attempt + 1}/${opts.maxAttempts} failed — ` +
          `retrying in ${delay}ms. Error: ${(err as Error).message}`
      );
      await sleep(delay);
    }
  }

  throw lastError;
}
```

---

## Wrapping D1 Reads

```typescript
// src/lib/d1-query.ts
import type { D1Database } from "@cloudflare/workers-types";
import { withRetry, type RetryOptions } from "./d1-retry";

export async function queryFirst<T = Record<string, unknown>>(
  db: D1Database,
  sql: string,
  params: unknown[] = [],
  retryOptions?: RetryOptions
): Promise<T | null> {
  return withRetry(
    () => db.prepare(sql).bind(...params).first<T>(),
    retryOptions
  );
}

export async function queryAll<T = Record<string, unknown>>(
  db: D1Database,
  sql: string,
  params: unknown[] = [],
  retryOptions?: RetryOptions
): Promise<T[]> {
  return withRetry(async () => {
    const result = await db.prepare(sql).bind(...params).all<T>();
    return result.results;
  }, retryOptions);
}
```

---

## Wrapping D1 Writes (Idempotent Upserts)

Retrying non-idempotent writes (plain `INSERT`) can create duplicate rows. Use `INSERT OR IGNORE` / `ON CONFLICT DO UPDATE` to make writes safe to retry:

```typescript
// src/repositories/user-repo.ts
import type { D1Database } from "@cloudflare/workers-types";
import { withRetry } from "../lib/d1-retry";

export interface User {
  id: string;
  email: string;
  name: string;
  updatedAt: string;
}

export async function upsertUser(
  db: D1Database,
  user: User
): Promise<void> {
  await withRetry(() =>
    db
      .prepare(
        `INSERT INTO users (id, email, name, updated_at)
         VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT(id) DO UPDATE SET
           email = excluded.email,
           name  = excluded.name,
           updated_at = excluded.updated_at`
      )
      .bind(user.id, user.email, user.name, user.updatedAt)
      .run()
  );
}
```

---

## Wrapping D1 Batch Operations

```typescript
// src/lib/d1-batch-retry.ts
import type { D1Database, D1PreparedStatement } from "@cloudflare/workers-types";
import { withRetry, type RetryOptions } from "./d1-retry";

export async function batchWithRetry(
  db: D1Database,
  statements: D1PreparedStatement[],
  retryOptions?: RetryOptions
): Promise<void> {
  await withRetry(
    () => db.batch(statements),
    retryOptions
  );
}
```

---

## Per-request Retry Budget in Request Handlers

Enforce a hard time budget so retries don't cause Worker CPU-time overruns:

```typescript
// src/middleware/retry-budget.ts
import { withRetry, isTransientD1Error } from "../lib/d1-retry";

const REQUEST_RETRY_BUDGET_MS = 5000;

export function withRequestBudget<T>(
  operation: (attempt: number) => Promise<T>,
  requestStartTime: number
): Promise<T> {
  return withRetry(operation, {
    maxAttempts: 3,
    baseDelayMs: 100,
    maxDelayMs: 2000,
    isRetryable: (err) => {
      const elapsed = Date.now() - requestStartTime;
      if (elapsed > REQUEST_RETRY_BUDGET_MS) {
        console.warn("[retry-budget] Budget exhausted — aborting retry");
        return false;
      }
      return isTransientD1Error(err);
    },
  });
}
```

Usage in a fetch handler:

```typescript
// src/index.ts
import type { Env } from "./types";
import { queryFirst } from "./lib/d1-query";
import { withRequestBudget } from "./middleware/retry-budget";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);
    const id = url.searchParams.get("id");

    if (!id) {
      return new Response("Missing id", { status: 400 });
    }

    try {
      const user = await withRequestBudget(
        () => queryFirst(env.DB, "SELECT * FROM users WHERE id = ?1", [id]),
        start
      );

      if (!user) return new Response("Not found", { status: 404 });
      return Response.json(user);
    } catch (err) {
      console.error("D1 query failed after retries:", err);
      return new Response("Service temporarily unavailable", { status: 503 });
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Logging Retry Telemetry

```typescript
// src/lib/d1-retry-telemetry.ts
import { withRetry, type RetryOptions } from "./d1-retry";

interface RetryTelemetry {
  attempts: number;
  totalDelayMs: number;
  succeeded: boolean;
  finalError?: string;
}

export async function withRetryTelemetry<T>(
  operation: (attempt: number) => Promise<T>,
  options?: RetryOptions
): Promise<{ result: T; telemetry: RetryTelemetry }> {
  let attempts = 0;
  let totalDelayMs = 0;
  const opStart = Date.now();

  const wrappedOperation = async (attempt: number): Promise<T> => {
    attempts = attempt + 1;
    return operation(attempt);
  };

  try {
    const result = await withRetry(wrappedOperation, options);
    totalDelayMs = Date.now() - opStart;
    return { result, telemetry: { attempts, totalDelayMs, succeeded: true } };
  } catch (err) {
    totalDelayMs = Date.now() - opStart;
    return Promise.reject(err);
  }
}
```

---

## Anti-patterns

- **Retrying non-idempotent plain `INSERT` statements.** A transient failure after D1 commits but before the Worker receives the response will cause duplicate rows on retry. Always use `ON CONFLICT` or check existence first.
- **Retrying inside a transaction without re-opening it.** D1 transactions do not survive a transient error — the entire transaction is rolled back. You must open a new transaction on retry, not re-run only the failed statement.
- **Using fixed delays without jitter.** Multiple Workers retrying simultaneously at the same interval create thundering-herd spikes on D1. Add random jitter.
- **Unbounded `maxAttempts`.** A bug in your SQL (syntax error, constraint violation) is not transient. Always filter non-retryable errors with `isRetryable` so you don't waste 10 retries on a bug.
- **Retrying in Cron Triggers without alerting.** Silent retries in Cron can mask a persistent D1 degradation. Log each retry and surface metrics to Cloudflare Analytics Engine or an external monitor.

---

## Gotchas

- **Worker CPU time limit**: Cloudflare Workers have a 50 ms CPU time limit on the free plan and 30 s on paid plans. `await sleep(delay)` does not count against CPU time, but if the operation itself is slow, retries can blow the wall-clock limit. Use a request-time budget.
- **D1 `run()` vs `first()` vs `all()`**: All three can throw on transient errors. Wrap each at the call site or use the shared `withRetry` wrapper.
- **`ctx.waitUntil` and retries**: If you fire a write in `waitUntil`, retries may outlive the Worker's active-request window. Consider `maxAttempts: 2` and `maxDelayMs: 3000` for background tasks.
- **Cloudflare rate limits are per-account**: `429 Too Many Requests` from D1 affects all Workers sharing the account. Backing off in one Worker may not help if others are hammering D1 simultaneously — implement account-level throttling via a Durable Object counter.

---

## Verification

```typescript
// test/d1-retry.test.ts (Vitest + Miniflare)
import { describe, it, expect, vi } from "vitest";
import { withRetry, isTransientD1Error } from "../src/lib/d1-retry";

describe("withRetry", () => {
  it("returns immediately on success", async () => {
    const op = vi.fn().mockResolvedValue("ok");
    const result = await withRetry(op, { maxAttempts: 3 });
    expect(result).toBe("ok");
    expect(op).toHaveBeenCalledTimes(1);
  });

  it("retries transient errors and eventually succeeds", async () => {
    const op = vi
      .fn()
      .mockRejectedValueOnce(new Error("D1_ERROR: network error"))
      .mockResolvedValue("ok");

    const result = await withRetry(op, {
      maxAttempts: 3,
      baseDelayMs: 1, // fast for tests
    });

    expect(result).toBe("ok");
    expect(op).toHaveBeenCalledTimes(2);
  });

  it("does not retry non-transient errors", async () => {
    const op = vi
      .fn()
      .mockRejectedValue(new Error("SQLITE_CONSTRAINT: UNIQUE constraint failed"));

    await expect(withRetry(op, { maxAttempts: 3, baseDelayMs: 1 })).rejects.toThrow(
      "UNIQUE constraint"
    );
    expect(op).toHaveBeenCalledTimes(1);
  });
});
```

---

## Related

- `d1-dead-letter-queue-retry-workers.md` — Queue-based retry for async write failures
- `d1-query-timeout-abort-workers.md` — Aborting slow queries before retry
- `d1-rate-limiting-sliding-window-workers.md` — Account-level rate limiting with DO
- `d1-optimistic-locking-version-column-workers.md` — Version-column concurrency control
- `d1-durable-object-connection-multiplexing-workers.md` — Serializing D1 access through a DO

---

## Sources

- Cloudflare D1 error codes: https://developers.cloudflare.com/d1/observability/errors/
- Exponential backoff and jitter: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Cloudflare Workers CPU limits: https://developers.cloudflare.com/workers/platform/limits/
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
