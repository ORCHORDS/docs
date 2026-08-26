# Usage-Based Billing Metering with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

SaaS products that charge per API call, per GB stored, or per active seat need a metering layer that can ingest thousands of usage events per second, aggregate them into billing-period totals, calculate overages against plan limits, and expose a usage report API — all without a dedicated metering microservice.

## Context

Workers sits at the edge and can accept high-throughput event streams with sub-millisecond latency. D1 (Cloudflare's edge SQLite) holds the usage ledger and plan configuration. The billing cycle is typically monthly; overages are computed at invoice time or proactively in real time.

## Solution

### 1. D1 schema

```sql
-- migrations/001_usage_metering.sql

CREATE TABLE IF NOT EXISTS accounts (
  id          TEXT PRIMARY KEY,
  plan_id     TEXT NOT NULL,
  cycle_start TEXT NOT NULL  -- ISO-8601 date of current billing period start
);

CREATE TABLE IF NOT EXISTS plan_limits (
  plan_id         TEXT PRIMARY KEY,
  monthly_api_calls  INTEGER NOT NULL,
  monthly_storage_gb REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (
  id          TEXT PRIMARY KEY,          -- idempotency key from caller
  account_id  TEXT NOT NULL,
  metric      TEXT NOT NULL,             -- 'api_calls' | 'storage_gb'
  quantity    REAL NOT NULL,
  recorded_at TEXT NOT NULL,             -- ISO-8601 UTC
  FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_usage_account_metric
  ON usage_events (account_id, metric, recorded_at);

CREATE TABLE IF NOT EXISTS usage_resets (
  account_id  TEXT NOT NULL,
  metric      TEXT NOT NULL,
  reset_at    TEXT NOT NULL,
  PRIMARY KEY (account_id, metric)
);
```

### 2. Usage event ingestion endpoint

```typescript
// src/metering/ingest.ts
export interface Env {
  DB: D1Database;
  METERING_API_KEY: string;
}

interface UsageEvent {
  id: string;        // caller-supplied idempotency key
  account_id: string;
  metric: 'api_calls' | 'storage_gb';
  quantity: number;
  recorded_at?: string; // optional; defaults to now
}

export async function handleIngest(request: Request, env: Env): Promise<Response> {
  // Lightweight API key auth for internal services
  const authHeader = request.headers.get('Authorization');
  if (authHeader !== `Bearer ${env.METERING_API_KEY}`) {
    return new Response('Unauthorized', { status: 401 });
  }

  let events: UsageEvent[];
  try {
    events = await request.json();
    if (!Array.isArray(events) || events.length === 0) throw new Error();
  } catch {
    return new Response('Expected non-empty JSON array', { status: 400 });
  }

  if (events.length > 500) {
    return new Response('Batch size exceeds 500', { status: 413 });
  }

  const now = new Date().toISOString();

  // D1 batch API — single round-trip for all inserts
  const stmts = events.map((e) =>
    env.DB.prepare(
      `INSERT INTO usage_events (id, account_id, metric, quantity, recorded_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(id) DO NOTHING`
    ).bind(e.id, e.account_id, e.metric, e.quantity, e.recorded_at ?? now)
  );

  const results = await env.DB.batch(stmts);
  const inserted = results.filter((r) => r.meta.rows_written > 0).length;

  return new Response(JSON.stringify({ accepted: events.length, inserted }), {
    status: 207,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

### 3. Billing period aggregation

```typescript
// src/metering/aggregate.ts
export interface PeriodUsage {
  account_id: string;
  metric: string;
  period_start: string;
  total: number;
  limit: number;
  overage: number;
  overage_pct: number;
}

export async function getAccountUsage(
  accountId: string,
  env: Env
): Promise<PeriodUsage[]> {
  const account = await env.DB.prepare(
    'SELECT plan_id, cycle_start FROM accounts WHERE id = ?'
  )
    .bind(accountId)
    .first<{ plan_id: string; cycle_start: string }>();

  if (!account) throw new Error(`Account not found: ${accountId}`);

  const metrics: Array<{ metric: string; total: number }> = await env.DB.prepare(
    `SELECT metric, COALESCE(SUM(quantity), 0) AS total
     FROM usage_events
     WHERE account_id = ?
       AND recorded_at >= ?
     GROUP BY metric`
  )
    .bind(accountId, account.cycle_start)
    .all<{ metric: string; total: number }>()
    .then((r) => r.results);

  const limits = await env.DB.prepare(
    `SELECT monthly_api_calls, monthly_storage_gb
     FROM plan_limits WHERE plan_id = ?`
  )
    .bind(account.plan_id)
    .first<{ monthly_api_calls: number; monthly_storage_gb: number }>();

  const limitMap: Record<string, number> = {
    api_calls: limits?.monthly_api_calls ?? 0,
    storage_gb: limits?.monthly_storage_gb ?? 0,
  };

  return metrics.map(({ metric, total }) => {
    const limit = limitMap[metric] ?? 0;
    const overage = Math.max(0, total - limit);
    return {
      account_id: accountId,
      metric,
      period_start: account.cycle_start,
      total,
      limit,
      overage,
      overage_pct: limit > 0 ? Math.round((overage / limit) * 100) : 0,
    };
  });
}
```

### 4. Usage report API endpoint

```typescript
// src/metering/report.ts
export async function handleUsageReport(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const accountId = url.searchParams.get('account_id');

  if (!accountId) {
    return new Response('Missing account_id', { status: 400 });
  }

  try {
    const usage = await getAccountUsage(accountId, env);
    return new Response(JSON.stringify({ account_id: accountId, usage }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return new Response(JSON.stringify({ error: message }), { status: 404 });
  }
}
```

### 5. Billing cycle reset

```typescript
// src/metering/reset.ts
/**
 * Called by a Cron Trigger on the 1st of each month at 00:05 UTC.
 * Rolls cycle_start forward for each account whose billing day matches today.
 */
export async function handleBillingReset(env: Env): Promise<void> {
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD

  // Move cycle_start to today for accounts whose billing day is today
  const result = await env.DB.prepare(
    `UPDATE accounts
     SET cycle_start = ?
     WHERE strftime('%d', cycle_start) = strftime('%d', ?)`
  )
    .bind(today, today)
    .run();

  console.log(`Billing reset: updated ${result.meta.rows_written} accounts`);

  // Record reset events for audit
  const affected = await env.DB.prepare(
    `SELECT id FROM accounts WHERE cycle_start = ?`
  )
    .bind(today)
    .all<{ id: string }>();

  const now = new Date().toISOString();
  const resets = affected.results.flatMap(({ id }) =>
    ['api_calls', 'storage_gb'].map((metric) =>
      env.DB.prepare(
        `INSERT INTO usage_resets (account_id, metric, reset_at)
         VALUES (?, ?, ?)
         ON CONFLICT(account_id, metric) DO UPDATE SET reset_at = excluded.reset_at`
      ).bind(id, metric, now)
    )
  );

  if (resets.length > 0) await env.DB.batch(resets);
}
```

### 6. wrangler.toml

```toml
[[d1_databases]]
binding = "DB"
database_name = "billing"
database_id = "<your-d1-id>"

[triggers]
crons = ["5 0 1 * *"]  # 00:05 UTC on the 1st of each month
```

## Implementation Details

- `ON CONFLICT(id) DO NOTHING` makes ingestion idempotent — callers can safely retry batches.
- D1 `batch()` uses a single HTTP round-trip, reducing latency for large event bursts.
- `cycle_start` is stored per account, enabling mid-month sign-ups to have prorated billing periods.
- Overage is computed in-query — no application-layer loops over rows.
- The Cron Trigger runs monthly reset logic server-side without an external scheduler.

## Anti-patterns

- **Aggregating in application code over unbounded row sets** — always use `SUM` in SQL.
- **Deleting usage events on reset** — retain them for audit; advance `cycle_start` instead.
- **Storing plan limits in Workers environment variables** — they change frequently; keep them in D1 `plan_limits`.
- **No idempotency key on ingestion** — network retries cause double-counting.

## Gotchas

- D1 is eventually consistent in read replicas; use primary reads for billing-critical overage checks.
- `strftime('%d', ...)` in SQLite returns `'01'`–`'31'` zero-padded strings; ensure your comparison is string-based.
- The batch size limit for D1 is 1 000 statements per `batch()` call; split larger batches.
- Workers Cron Triggers have a minimum interval of 1 minute; they cannot run sub-minute.

## Verification

```bash
# Ingest test events
curl -X POST https://<worker>/ingest \
  -H "Authorization: Bearer $METERING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '[{"id":"evt-001","account_id":"acct_1","metric":"api_calls","quantity":100}]'

# Fetch usage report
curl "https://<worker>/usage?account_id=acct_1"

# Verify D1 directly
wrangler d1 execute billing --command \
  "SELECT metric, SUM(quantity) FROM usage_events WHERE account_id='acct_1' GROUP BY metric"
```

## Related

- `documentation/docs/policies/payments/workers-revenue-recognition-d1.md`
- `documentation/docs/policies/payments/workers-subscription-dunning-workflow.md`
- `documentation/docs/policies/payments/workers-promo-code-validation-d1.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://stripe.com/docs/billing/subscriptions/usage-based
