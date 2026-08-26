# D1 Retry on Transient Errors with Exponential Backoff

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare D1 occasionally returns transient `D1_ERROR` responses — network hiccups between the Worker and D1's SQLite replica, or brief leader-election gaps. Without a retry layer, a single transient error surfaces as a 500 to the end user. A structured retry wrapper with exponential backoff and a circuit breaker prevents cascading failures.

## Context

- Runtime: Cloudflare Workers (ESM, TypeScript)
- Database: Cloudflare D1
- Error surface: `D1DatabaseError` thrown by `db.prepare().run()` / `.first()` / `.all()`
- Goal: transparent retry for transient errors, fast fail for permanent ones, open circuit after N consecutive failures

---

## Section 1: Identify Retryable D1 Error Codes

```typescript
// src/db/retry.ts

/**
 * D1 error codes that indicate a transient condition safe to retry.
 * Permanent errors (constraint violations, syntax errors) must NOT be retried.
 */
const RETRYABLE_D1_MESSAGES: readonly string[] = [
  'D1_ERROR',          // generic transient
  'network error',     // Worker <-> D1 connectivity
  'timeout',           // query execution timeout
  'SQLITE_BUSY',       // WAL checkpoint contention
  'SQLITE_LOCKED',     // short write lock contention
];

/** Returns true if the error is a known transient D1 condition */
export function isRetryable(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  return RETRYABLE_D1_MESSAGES.some((code) =>
    msg.includes(code.toLowerCase()),
  );
}
```

---

## Section 2: Exponential Backoff Retry Wrapper

The wrapper retries up to `maxAttempts` times with jittered exponential backoff. Workers `await new Promise(resolve => setTimeout(resolve, ms))` works inside the runtime.

```typescript
// src/db/retry.ts (continued)

export interface RetryOptions {
  /** Maximum total attempts (including the first) */
  maxAttempts?: number;
  /** Base delay in milliseconds for the first retry */
  baseDelayMs?: number;
  /** Maximum delay cap in milliseconds */
  maxDelayMs?: number;
  /** Jitter factor 0-1 (0 = no jitter, 1 = full jitter) */
  jitter?: number;
}

const DEFAULT_RETRY_OPTIONS: Required<RetryOptions> = {
  maxAttempts: 4,
  baseDelayMs: 50,
  maxDelayMs: 2000,
  jitter: 0.3,
};

/**
 * Run an async operation with exponential backoff retry on transient D1 errors.
 *
 * @example
 * const row = await withRetry(() => db.prepare('SELECT 1').first());
 */
export async function withRetry<T>(
  operation: () => Promise<T>,
  options: RetryOptions = {},
): Promise<T> {
  const opts = { ...DEFAULT_RETRY_OPTIONS, ...options };
  let lastError: Error | undefined;

  for (let attempt = 1; attempt <= opts.maxAttempts; attempt++) {
    try {
      return await operation();
    } catch (err) {
      if (!isRetryable(err)) {
        // Non-retryable: rethrow immediately
        throw err;
      }

      lastError = err instanceof Error ? err : new Error(String(err));

      if (attempt === opts.maxAttempts) break;

      // Exponential backoff with optional jitter
      const baseDelay = Math.min(
        opts.baseDelayMs * 2 ** (attempt - 1),
        opts.maxDelayMs,
      );
      const jitterRange = baseDelay * opts.jitter;
      const delay = baseDelay - jitterRange / 2 + Math.random() * jitterRange;

      console.warn(
        `D1 transient error (attempt ${attempt}/${opts.maxAttempts}), ` +
          `retrying in ${Math.round(delay)}ms: ${lastError.message}`,
      );

      await new Promise<void>((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError ?? new Error('withRetry: exhausted attempts with no error captured');
}
```

---

## Section 3: Circuit Breaker

After `failureThreshold` consecutive failures, the circuit opens and all calls fail immediately for `cooldownMs`. This protects downstream systems when D1 is experiencing a broader outage.

```typescript
// src/db/circuit-breaker.ts

export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN';

export class CircuitBreaker {
  private failures = 0;
  private lastFailureAt = 0;
  private state: CircuitState = 'CLOSED';

  constructor(
    private readonly failureThreshold: number = 5,
    private readonly cooldownMs: number = 30_000,
  ) {}

  get currentState(): CircuitState {
    if (this.state === 'OPEN') {
      const elapsed = Date.now() - this.lastFailureAt;
      if (elapsed >= this.cooldownMs) {
        this.state = 'HALF_OPEN';
      }
    }
    return this.state;
  }

  async call<T>(operation: () => Promise<T>): Promise<T> {
    const state = this.currentState;

    if (state === 'OPEN') {
      throw new Error(
        `CircuitBreaker OPEN: D1 calls suspended for ${this.cooldownMs}ms after ${this.failures} failures.`,
      );
    }

    try {
      const result = await operation();
      this.onSuccess();
      return result;
    } catch (err) {
      this.onFailure();
      throw err;
    }
  }

  private onSuccess(): void {
    this.failures = 0;
    this.state = 'CLOSED';
  }

  private onFailure(): void {
    this.failures += 1;
    this.lastFailureAt = Date.now();
    if (this.failures >= this.failureThreshold) {
      this.state = 'OPEN';
      console.error(
        `CircuitBreaker: opened after ${this.failures} consecutive D1 failures.`,
      );
    }
  }

  reset(): void {
    this.failures = 0;
    this.lastFailureAt = 0;
    this.state = 'CLOSED';
  }
}
```

---

## Section 4: Composing Retry + Circuit Breaker in a Workers Handler

Instantiate the `CircuitBreaker` outside the fetch handler so it persists across requests within the same isolate lifetime.

```typescript
// src/index.ts
import type { D1Database } from '@cloudflare/workers-types';
import { withRetry } from './db/retry';
import { CircuitBreaker } from './db/circuit-breaker';

interface Env {
  DB: D1Database;
}

// Shared across requests within the same Worker isolate
const breaker = new CircuitBreaker(5, 30_000);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const row = await breaker.call(() =>
        withRetry(
          () =>
            env.DB.prepare('SELECT id, name FROM users WHERE id = ?')
              .bind('user-123')
              .first<{ id: string; name: string }>(),
          { maxAttempts: 3, baseDelayMs: 100 },
        ),
      );

      if (!row) return new Response('Not Found', { status: 404 });
      return Response.json(row);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';

      if (message.startsWith('CircuitBreaker OPEN')) {
        return new Response('Service Temporarily Unavailable', { status: 503 });
      }

      console.error('D1 error:', err);
      return new Response('Internal Server Error', { status: 500 });
    }
  },
};
```

---

## Section 5: Observability — Logging Retry Metrics

```typescript
// src/db/retry-metrics.ts

export interface RetryMetric {
  operation: string;
  attempt: number;
  delayMs: number;
  errorMessage: string;
  timestamp: string;
}

export function logRetryMetric(
  ctx: ExecutionContext,
  metric: RetryMetric,
): void {
  // Use waitUntil so the log does not block the response
  ctx.waitUntil(
    Promise.resolve().then(() => {
      console.log('[D1_RETRY]', JSON.stringify(metric));
    }),
  );
}
```

---

## Anti-patterns

- Retrying on constraint violations (`SQLITE_CONSTRAINT`) — these will never succeed and amplify DB load.
- Using a global retry count that is not reset between requests — leads to silent degradation across unrelated requests.
- Sleeping for fixed intervals without jitter — causes thundering-herd when multiple Worker instances retry simultaneously.
- Placing the `CircuitBreaker` instance inside the fetch handler — it resets every request and never opens.
- Not logging retry attempts — silent retries hide systemic D1 issues that need escalation.

## Gotchas

- Worker isolate lifetime is not guaranteed; the circuit breaker state is lost on isolate eviction. For persistent circuit state, use Durable Objects or KV.
- `setTimeout` inside a Worker is subject to the 30-second CPU time limit on the total request; keep total backoff time well under that ceiling.
- D1 errors are sometimes wrapped in a `cause` property; check `(err as any).cause?.message` if `err.message` does not contain the D1 error code.
- `SQLITE_BUSY` indicates WAL checkpoint contention and is safe to retry; `SQLITE_LOCKED` is similar but rarer in D1's serverless model.
- The `breaker.call()` wrapping `withRetry()` means each attempt counted by `withRetry` can itself trigger a circuit failure; tune thresholds accordingly.

## Verification

```bash
# Simulate a transient error by intentionally running a syntax-error query
# (non-retryable — should NOT retry)
wrangler d1 execute YOUR_DB_NAME \
  --command "SLECT 1;" \
  --remote
# Expected: immediate error, no retry log lines

# Check Worker logs for retry events during a test run
wrangler tail YOUR_WORKER_NAME --format=pretty | grep D1_RETRY
```

```typescript
// Unit test for isRetryable
import { isRetryable } from './src/db/retry';

console.assert(isRetryable(new Error('D1_ERROR: network error')) === true);
console.assert(isRetryable(new Error('SQLITE_CONSTRAINT: UNIQUE')) === false);
console.assert(isRetryable(new Error('SQLITE_BUSY')) === true);
console.assert(isRetryable('not an error') === false);
console.log('isRetryable tests passed');
```

## Related

- `documentation/categories/database/d1-time-travel-point-in-time-restore.md`
- `documentation/categories/database/d1-trigger-audit-log-application-layer.md`
- `documentation/categories/database/d1-multi-tenant-row-isolation-pattern.md`

## Sources

- https://developers.cloudflare.com/d1/observability/debug-d1/
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://www.sqlite.org/rescode.html
- https://developers.cloudflare.com/workers/runtime-apis/handlers/fetch/
