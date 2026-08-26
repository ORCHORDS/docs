# D1 Rate Limiting with Sliding Window Algorithm in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your Cloudflare Worker API is being hammered by abusive clients or runaway bots and you need per-user rate limiting without an external Redis dependency. D1 can serve as the backing store for a sliding-window counter at the edge.

## Context
SQLite's atomic `INSERT OR REPLACE` and `DELETE` semantics make it suitable for lightweight rate-limit accounting inside Workers. The sliding-window approach stores individual request timestamps in a small table and counts only those within the current window, giving accurate limits without the over-counting that fixed windows produce. D1's per-request latency (~1–5 ms at the edge) is acceptable for rate-limit checks when the check is batched with the actual business query.

## Schema Design

```sql
-- migrations/0010_rate_limit_log.sql
CREATE TABLE IF NOT EXISTS rate_limit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  client_key  TEXT    NOT NULL,           -- e.g. "ip:203.0.113.7" or "user:uuid"
  bucket      TEXT    NOT NULL,           -- e.g. "api:search" or "api:write"
  ts          INTEGER NOT NULL,           -- Unix epoch seconds
  INDEX idx_rll_key_bucket_ts (client_key, bucket, ts)
);

-- Prune rows older than the longest window on each check
-- (done in the same batch to avoid separate round-trips)
```

## Core Rate-Limit Helper

```typescript
// src/lib/rate-limit.ts
export interface RateLimitConfig {
  windowSecs: number;   // e.g. 60
  maxRequests: number;  // e.g. 100
}

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetAt: number;      // Unix epoch seconds
}

export async function checkRateLimit(
  db: D1Database,
  clientKey: string,
  bucket: string,
  config: RateLimitConfig,
): Promise<RateLimitResult> {
  const now = Math.floor(Date.now() / 1000);
  const windowStart = now - config.windowSecs;
  const resetAt = now + config.windowSecs;

  // Batch: prune expired rows + insert current request + count window
  const [, , countResult] = await db.batch([
    db.prepare(
      `DELETE FROM rate_limit_log
       WHERE client_key = ? AND bucket = ? AND ts < ?`
    ).bind(clientKey, bucket, windowStart),

    db.prepare(
      `INSERT INTO rate_limit_log (client_key, bucket, ts) VALUES (?, ?, ?)`
    ).bind(clientKey, bucket, now),

    db.prepare(
      `SELECT COUNT(*) AS cnt
       FROM rate_limit_log
       WHERE client_key = ? AND bucket = ? AND ts >= ?`
    ).bind(clientKey, bucket, windowStart),
  ]);

  const count = (countResult.results[0] as { cnt: number }).cnt;
  const allowed = count <= config.maxRequests;
  const remaining = Math.max(0, config.maxRequests - count);

  return { allowed, remaining, resetAt };
}
```

## Worker Middleware Integration

```typescript
// src/middleware/rate-limit-middleware.ts
import { checkRateLimit, RateLimitConfig } from '../lib/rate-limit';

const LIMITS: Record<string, RateLimitConfig> = {
  'api:search': { windowSecs: 60,  maxRequests: 30  },
  'api:write':  { windowSecs: 60,  maxRequests: 10  },
  'api:export': { windowSecs: 3600, maxRequests: 5  },
};

export async function rateLimitMiddleware(
  request: Request,
  env: { DB: D1Database },
  bucket: string,
): Promise<Response | null> {
  const config = LIMITS[bucket];
  if (!config) return null; // no limit configured → pass through

  // Prefer authenticated user ID; fall back to IP
  const clientKey = request.headers.get('cf-connecting-ip') ?? 'unknown';

  const result = await checkRateLimit(env.DB, `ip:${clientKey}`, bucket, config);

  const headers = {
    'X-RateLimit-Limit':     String(config.maxRequests),
    'X-RateLimit-Remaining': String(result.remaining),
    'X-RateLimit-Reset':     String(result.resetAt),
  };

  if (!result.allowed) {
    return new Response(JSON.stringify({ error: 'rate_limit_exceeded' }), {
      status: 429,
      headers: { 'Content-Type': 'application/json', ...headers },
    });
  }

  return null; // allowed — continue to handler
}
```

## Periodic Cleanup with Cron Trigger

Without pruning, `rate_limit_log` grows unboundedly. The batch `DELETE` above handles the hot path, but a scheduled cleanup removes orphaned rows for inactive clients.

```typescript
// src/scheduled.ts
export async function handleScheduled(
  _event: ScheduledEvent,
  env: { DB: D1Database },
): Promise<void> {
  const maxWindowSecs = 3600; // longest window in use
  const cutoff = Math.floor(Date.now() / 1000) - maxWindowSecs;

  const { meta } = await env.DB.prepare(
    `DELETE FROM rate_limit_log WHERE ts < ?`
  ).bind(cutoff).run();

  console.log(`rate_limit_log pruned: ${meta.changes} rows removed`);
}
```

```toml
# wrangler.toml
[[triggers.crons]]
crons = ["*/15 * * * *"]
```

## Distributed Key Patterns

Single-key rate limiting covers the common case. For more complex policies:

```typescript
// Composite key: user + endpoint + tenant
const clientKey = `user:${userId}|tenant:${tenantId}`;

// Tiered limits: check both per-user and global bucket
async function checkTieredLimits(
  db: D1Database,
  userId: string,
  bucket: string,
): Promise<RateLimitResult> {
  const [userResult, globalResult] = await Promise.all([
    checkRateLimit(db, `user:${userId}`, bucket, { windowSecs: 60, maxRequests: 20 }),
    checkRateLimit(db, `global`, bucket,          { windowSecs: 60, maxRequests: 500 }),
  ]);

  // The more restrictive limit wins
  return userResult.remaining <= globalResult.remaining ? userResult : globalResult;
}
```

## Anti-patterns
- Using `SELECT COUNT(*)` without first inserting — you get a count of N-1 since the current request hasn't been recorded yet
- Storing rate-limit state in KV with TTLs — KV has no atomic increment; race conditions under burst traffic cause under-counting
- Running prune and insert as separate Worker fetch calls instead of a single `db.batch()` — doubles the D1 round-trips
- Using wall-clock window start without a server-side `NOW()` equivalent; always pass the timestamp from the Worker to avoid clock skew

## Gotchas
- D1's `batch()` executes statements sequentially in a single transaction — the count will always include the current insert
- `ts` column stores seconds not milliseconds; sub-second precision is rarely needed and bloats row counts
- Very high cardinality keys (one per unique IP per endpoint) can produce large index scans — add a partial index or a TTL-based hard cap on rows per key
- `meta.changes` is available on write statements but not on `SELECT`; cast results from `results[0]` carefully

## Verification

```bash
# Seed test data and verify counting logic
wrangler d1 execute MY_DB --local --command \
  "INSERT INTO rate_limit_log (client_key, bucket, ts) \
   SELECT 'ip:1.2.3.4', 'api:search', unixepoch() - x \
   FROM generate_series(0, 29);"

wrangler d1 execute MY_DB --local --command \
  "SELECT COUNT(*) FROM rate_limit_log \
   WHERE client_key='ip:1.2.3.4' AND bucket='api:search' \
   AND ts >= unixepoch() - 60;"
# Expect: 30 — hitting limit exactly

# Integration test with Vitest + miniflare
# test/rate-limit.test.ts: fire 31 requests, assert 30 return 200 and 31st returns 429
```

## Related
- [d1-batch-operations-performance.md](d1-batch-operations-performance.md)
- [d1-advisory-lock-pattern-workers.md](d1-advisory-lock-pattern-workers.md)
- [d1-time-series-partitioning.md](d1-time-series-partitioning.md)

## Sources
- Cloudflare D1 Batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite `unixepoch()` function: https://www.sqlite.org/lang_datefunc.html
- Sliding window rate limiting: https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
