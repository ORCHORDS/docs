# D1 Batch Query Performance Optimization

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Sequential Queries Dominate Worker CPU Time

Workers running against D1 commonly issue queries one at a time inside request handlers. Each query incurs a round-trip from the Worker to the D1 primary (or read replica), even when the queries are logically independent. For a handler that runs five unrelated SELECTs, this means five sequential round-trips, each adding 1–5 ms of network overhead in the same region and potentially 20–80 ms cross-region.

`db.batch()` collapses N independent statements into a single D1 HTTP call and returns an array of results in the same order. The reduction in wall-clock time is proportional to the number of eliminated round-trips. On a page load that requires profile data, recent orders, notification count, feature flags, and user settings, `db.batch()` can cut database query time from 30–80 ms down to 5–15 ms.

## Context

D1's `db.batch()` API sends a JSON array of prepared statements to the D1 HTTP endpoint in one request and receives an array of result sets in one response. Each statement in the batch runs inside its own implicit transaction; if one fails, subsequent statements still execute. For transactional batches (all-or-nothing), wrap statements in explicit `BEGIN`/`COMMIT` within the batch array. The optimal batch size is bounded by D1's 100-statement limit per batch and by practical payload size (very large batches approach D1's 1 MB request body limit).

Analytics Engine tracks per-query latency and batch size so you can observe round-trip savings over time.

## db.batch() vs Sequential Queries

```typescript
import { Env } from './types';

// BAD: sequential — 5 separate round-trips
async function loadUserDashboardSequential(
  db: D1Database,
  userId: string,
): Promise<DashboardData> {
  const profile      = await db.prepare('SELECT * FROM users WHERE id = ?').bind(userId).first();
  const orders       = await db.prepare('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 5').bind(userId).all();
  const notifications = await db.prepare('SELECT COUNT(*) as n FROM notifications WHERE user_id = ? AND read = 0').bind(userId).first();
  const flags        = await db.prepare('SELECT * FROM feature_flags WHERE user_id = ?').bind(userId).all();
  const settings     = await db.prepare('SELECT * FROM user_settings WHERE user_id = ?').bind(userId).first();
  return { profile, orders: orders.results, notifications, flags: flags.results, settings };
}

// GOOD: batched — 1 round-trip
async function loadUserDashboardBatched(
  db: D1Database,
  userId: string,
): Promise<DashboardData> {
  const [profileRes, ordersRes, notifRes, flagsRes, settingsRes] = await db.batch([
    db.prepare('SELECT * FROM users WHERE id = ?').bind(userId),
    db.prepare('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 5').bind(userId),
    db.prepare('SELECT COUNT(*) as n FROM notifications WHERE user_id = ? AND read = 0').bind(userId),
    db.prepare('SELECT * FROM feature_flags WHERE user_id = ?').bind(userId),
    db.prepare('SELECT * FROM user_settings WHERE user_id = ?').bind(userId),
  ]);

  return {
    profile:       profileRes.results[0] ?? null,
    orders:        ordersRes.results,
    notifications: notifRes.results[0] ?? null,
    flags:         flagsRes.results,
    settings:      settingsRes.results[0] ?? null,
  };
}
```

## Measuring Round-Trip Savings with Analytics Engine

```typescript
export interface Env {
  DB: D1Database;
  ANALYTICS: AnalyticsEngineDataset;
}

async function timedBatch(
  db: D1Database,
  statements: D1PreparedStatement[],
  label: string,
  env: Env,
): Promise<D1Result[]> {
  const t0 = Date.now();
  const results = await db.batch(statements);
  const latencyMs = Date.now() - t0;

  env.ANALYTICS.writeDataPoint({
    blobs: ['batch', label],
    doubles: [latencyMs, statements.length],
    indexes: [label],
  });

  return results;
}

// Compare: sum of individual query times vs batch time
async function benchmarkComparison(env: Env, userId: string): Promise<void> {
  const db = env.DB;
  const stmts = [
    db.prepare('SELECT id, name FROM users WHERE id = ?').bind(userId),
    db.prepare('SELECT id, total FROM orders WHERE user_id = ? LIMIT 10').bind(userId),
    db.prepare('SELECT COUNT(*) as n FROM notifications WHERE user_id = ?').bind(userId),
  ];

  // Measure sequential
  const seqStart = Date.now();
  for (const s of stmts) {
    await s.all();
  }
  const seqMs = Date.now() - seqStart;

  // Measure batch
  const batchStart = Date.now();
  await db.batch(stmts);
  const batchMs = Date.now() - batchStart;

  env.ANALYTICS.writeDataPoint({
    blobs: ['benchmark', 'comparison'],
    doubles: [seqMs, batchMs, seqMs - batchMs, stmts.length],
    indexes: ['d1-batch-benchmark'],
  });
}
```

## Optimal Batch Size Determination

```typescript
// Batch sizing heuristics
const D1_MAX_STATEMENTS_PER_BATCH = 100;
const D1_MAX_BATCH_BODY_BYTES     = 900_000; // conservative margin under 1MB limit

function chunkIntoBatches<T>(items: T[], chunkSize: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += chunkSize) {
    chunks.push(items.slice(i, i + chunkSize));
  }
  return chunks;
}

// Insert many rows efficiently — batch them to avoid exceeding limits
async function batchInsertOrders(
  db: D1Database,
  orders: Array<{ userId: string; total: number; status: string }>,
  env: Env,
): Promise<void> {
  const insertStmt = 'INSERT INTO orders (user_id, total, status, created_at) VALUES (?, ?, ?, ?)';
  const now = new Date().toISOString();

  // Empirically: ~200 bytes per bound INSERT statement; use 50 per batch for safety
  const BATCH_SIZE = 50;
  const chunks = chunkIntoBatches(orders, BATCH_SIZE);

  for (const chunk of chunks) {
    const t0 = Date.now();
    await db.batch(
      chunk.map(o => db.prepare(insertStmt).bind(o.userId, o.total, o.status, now)),
    );
    env.ANALYTICS.writeDataPoint({
      blobs: ['insert-batch'],
      doubles: [Date.now() - t0, chunk.length],
      indexes: ['d1-batch-insert'],
    });
  }
}

// Transactional batch: wrap in BEGIN/COMMIT for all-or-nothing semantics
async function transferBalance(
  db: D1Database,
  fromId: string,
  toId: string,
  amount: number,
): Promise<void> {
  await db.batch([
    db.prepare('BEGIN'),
    db.prepare('UPDATE accounts SET balance = balance - ? WHERE id = ? AND balance >= ?')
      .bind(amount, fromId, amount),
    db.prepare('UPDATE accounts SET balance = balance + ? WHERE id = ?')
      .bind(amount, toId),
    db.prepare('COMMIT'),
  ]);
}
```

## Querying Analytics Engine for Latency Tracking

```typescript
// GraphQL query to compute average batch vs sequential latency from Analytics Engine
const latencyQuery = `
  query D1BatchLatency($accountId: String!, $since: String!) {
    viewer {
      accounts(filter: { accountTag: $accountId }) {
        d1BatchMetrics: workersD1CacheAdaptiveGroups(
          limit: 500
          filter: { datetime_geq: $since }
        ) {
          avg { latencyMs: double1, batchSize: double2 }
          dimensions { queryType: blob1, label: blob2 }
        }
      }
    }
  }
`;
// blob1='batch' | 'sequential'; double1=latency; double2=statement count
// Compare avg latencyMs across query types, segmented by label
```

## Anti-patterns

- **Batching dependent queries** — `db.batch()` runs statements independently. If statement 2 needs the result of statement 1 (e.g., INSERT then SELECT last insert id), use `db.prepare().run()` sequentially or use RETURNING in the INSERT statement.
- **Batching inside a loop** — issuing `db.batch()` on each iteration of a loop defeats the purpose. Collect all statements, then call batch once.
- **Unbounded batches from untrusted input** — if batch size is derived from user-controlled data (e.g., array length from a request body), cap it at D1_MAX_STATEMENTS_PER_BATCH before calling `db.batch()`.
- **Ignoring partial failures** — `db.batch()` returns results for each statement; failed statements have a non-null `error` field. Check each result's `error` property; do not assume all succeeded because the batch promise resolved.

## Gotchas

- `db.batch([])` with an empty array returns `[]` without a D1 round-trip — safe to call unconditionally.
- D1 read replicas are used automatically for SELECT statements in batch when the Worker's `db` binding is configured with a read-replica URL. Write statements route to the primary. Mixing reads and writes in one batch will cause the batch to route to the primary entirely.
- The 100-statement limit is enforced server-side; exceeding it throws `D1_ERROR: too many statements in batch`.
- `db.batch()` results preserve input order, but each result has its own `meta` object (including `last_row_id`, `changes`, `duration`). The top-level batch call does not expose aggregate meta.

## Verification

```bash
# Use wrangler d1 execute to verify batch behavior locally
wrangler d1 execute YOUR_DB --local --command \
  "SELECT name FROM sqlite_master WHERE type='table'"

# In integration tests, measure wall time of sequential vs batched handlers:
# artillery run --target https://your-worker.example.com load-test.yml
# Compare p99 response times between /api/dashboard-sequential and /api/dashboard-batched
```

## Related

- `d1-query-performance-explain-index.md`
- `database-query-optimization.md`
- `workers-subrequest-fanout-parallelism.md`
- `analytics-engine-rum-web-vitals.md`
- `workers-queues-background-offload.md`

## Sources

- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- D1 limits: https://developers.cloudflare.com/d1/platform/limits/
- Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- D1 read replicas: https://developers.cloudflare.com/d1/configuration/read-replication/
