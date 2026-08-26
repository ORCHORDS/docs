# AI Gateway Prompt/Response Logging to D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You use Cloudflare AI Gateway to proxy LLM calls and want to retain every prompt/response pair for cost analysis, quality auditing, or compliance. The Gateway UI shows logs ephemerally; you need them persisted and queryable.

## Context

AI Gateway sits between your Workers and upstream model providers (OpenAI, Workers AI, etc.). It supports log retention with the **Log Retention** feature, which stores request/response metadata for up to 7 days via the Gateway API. A scheduled Worker can page through those logs and write them into a D1 table for indefinite retention and SQL-based cost analytics.

---

## Section 1 — Enable Log Retention in AI Gateway

In the Cloudflare Dashboard → AI Gateway → your gateway → Settings, enable **Log Requests**. Or via API:

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/ai-gateway/gateways/${GATEWAY_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-gateway",
    "collect_logs": true,
    "cache_invalidate_on_update": false,
    "cache_ttl": 0,
    "rate_limiting_interval": 0,
    "rate_limiting_limit": 0,
    "rate_limiting_technique": "fixed"
  }'
```

The `collect_logs: true` flag is all that is required. Logs appear under the `/logs` sub-resource of the gateway.

---

## Section 2 — D1 Schema

Create a D1 database and run this migration once:

```sql
-- migrations/0001_ai_gateway_logs.sql
CREATE TABLE IF NOT EXISTS gateway_logs (
  id            TEXT PRIMARY KEY,
  gateway_id    TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  provider      TEXT NOT NULL,
  model         TEXT NOT NULL,
  status        INTEGER NOT NULL,
  duration_ms   INTEGER NOT NULL,
  prompt_tokens INTEGER NOT NULL,
  completion_tokens INTEGER NOT NULL,
  total_tokens  INTEGER NOT NULL,
  cost_usd      REAL NOT NULL DEFAULT 0,
  prompt        TEXT,
  response      TEXT,
  cached        INTEGER NOT NULL DEFAULT 0,
  INDEX idx_gateway_created (gateway_id, created_at),
  INDEX idx_provider_model  (provider, model)
);
```

Apply with:

```bash
wrangler d1 migrations apply ai-gateway-logs-db --remote
```

---

## Section 3 — Scheduled Worker: Fetch Logs and Write to D1

```toml
# wrangler.toml
name = "ai-gateway-log-sync"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "ai-gateway-logs-db"
database_id = "<your-d1-database-id>"

[triggers]
crons = ["*/10 * * * *"]  # every 10 minutes

[vars]
ACCOUNT_ID = "<your-account-id>"
GATEWAY_ID = "my-gateway"
```

```typescript
// src/index.ts
import type { D1Database, ScheduledEvent, ExecutionContext } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  ACCOUNT_ID: string;
  GATEWAY_ID: string;
  CF_API_TOKEN: string; // set via `wrangler secret put CF_API_TOKEN`
}

interface GatewayLogEntry {
  id: string;
  created_at: string;
  provider: string;
  model: string;
  status: number;
  duration: number; // milliseconds
  tokens_in: number;
  tokens_out: number;
  cost: number;
  request?: { messages?: { role: string; content: string }[] };
  response?: { choices?: { message: { content: string } }[] };
  cached: boolean;
}

interface GatewayLogsResponse {
  result: GatewayLogEntry[];
  result_info: { page: number; per_page: number; total_count: number; count: number };
  success: boolean;
}

async function fetchGatewayLogs(
  accountId: string,
  gatewayId: string,
  apiToken: string,
  page: number,
  since: string
): Promise<GatewayLogsResponse> {
  const url = new URL(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai-gateway/gateways/${gatewayId}/logs`
  );
  url.searchParams.set('page', String(page));
  url.searchParams.set('per_page', '100');
  url.searchParams.set('start_date', since);
  url.searchParams.set('order_by', 'created_at');
  url.searchParams.set('direction', 'asc');

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${apiToken}`,
      'Content-Type': 'application/json',
    },
  });

  if (!res.ok) {
    throw new Error(`AI Gateway logs API ${res.status}: ${await res.text()}`);
  }

  return res.json() as Promise<GatewayLogsResponse>;
}

async function getLastSyncTime(db: D1Database, gatewayId: string): Promise<string> {
  const row = await db
    .prepare('SELECT MAX(created_at) as last FROM gateway_logs WHERE gateway_id = ?')
    .bind(gatewayId)
    .first<{ last: string | null }>();

  // Default to 10 minutes ago if table is empty
  if (!row?.last) {
    return new Date(Date.now() - 10 * 60 * 1000).toISOString();
  }
  return row.last;
}

async function upsertLogs(db: D1Database, gatewayId: string, logs: GatewayLogEntry[]): Promise<void> {
  if (logs.length === 0) return;

  const stmt = db.prepare(`
    INSERT OR IGNORE INTO gateway_logs
      (id, gateway_id, created_at, provider, model, status, duration_ms,
       prompt_tokens, completion_tokens, total_tokens, cost_usd, prompt, response, cached)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  const batch = logs.map((log) => {
    const prompt = log.request?.messages?.map((m) => `${m.role}: ${m.content}`).join('\n') ?? null;
    const response = log.response?.choices?.[0]?.message?.content ?? null;
    return stmt.bind(
      log.id,
      gatewayId,
      log.created_at,
      log.provider,
      log.model,
      log.status,
      log.duration,
      log.tokens_in,
      log.tokens_out,
      log.tokens_in + log.tokens_out,
      log.cost,
      prompt,
      response,
      log.cached ? 1 : 0
    );
  });

  await db.batch(batch);
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const since = await getLastSyncTime(env.DB, env.GATEWAY_ID);
    let page = 1;
    let totalInserted = 0;

    while (true) {
      const data = await fetchGatewayLogs(
        env.ACCOUNT_ID,
        env.GATEWAY_ID,
        env.CF_API_TOKEN,
        page,
        since
      );

      await upsertLogs(env.DB, env.GATEWAY_ID, data.result);
      totalInserted += data.result.length;

      const { total_count, per_page } = data.result_info;
      if (page * per_page >= total_count) break;
      page++;
    }

    console.log(`[ai-gateway-log-sync] inserted ${totalInserted} rows since ${since}`);
  },
};
```

---

## Section 4 — Cost Analysis Queries

```sql
-- Daily spend by model
SELECT
  date(created_at) AS day,
  provider,
  model,
  COUNT(*)          AS requests,
  SUM(total_tokens) AS tokens,
  ROUND(SUM(cost_usd), 4) AS cost_usd
FROM gateway_logs
GROUP BY day, provider, model
ORDER BY day DESC, cost_usd DESC;

-- Cache hit rate (cached calls save tokens)
SELECT
  date(created_at) AS day,
  SUM(cached) AS cache_hits,
  COUNT(*)    AS total,
  ROUND(100.0 * SUM(cached) / COUNT(*), 1) AS hit_pct
FROM gateway_logs
GROUP BY day
ORDER BY day DESC;

-- p95 latency by provider
SELECT
  provider,
  model,
  ROUND(AVG(duration_ms))   AS avg_ms,
  MAX(duration_ms)          AS max_ms
FROM gateway_logs
WHERE date(created_at) = date('now')
GROUP BY provider, model;
```

---

## Anti-patterns

- **Pulling all-time logs on every cron run** — use `MAX(created_at)` as a cursor; the API supports `start_date` filtering.
- **Storing full prompt/response in D1 unconditionally** — large responses inflate DB size fast. Consider truncating to 4 KB or storing to R2 and keeping only a key in D1.
- **Using `INSERT` instead of `INSERT OR IGNORE`** — retries after partial failures will fail on duplicate primary keys.

## Gotchas

- AI Gateway log retention is 7 days maximum on the API side. If the sync Worker fails silently for more than 7 days, you will lose data permanently.
- The `cost` field in the API response is Cloudflare's best-effort estimate; for billing-critical work, derive cost from token counts and provider pricing tables yourself.
- `collect_logs: true` does not log streaming chunks individually — it logs the aggregated request/response after the stream completes.
- API tokens need the **AI Gateway: Read** permission scoped to the correct account.

## Verification

```bash
# Trigger the scheduled worker manually
wrangler dev --test-scheduled
# Then in another terminal:
curl "http://localhost:8787/__scheduled?cron=*%2F10+*+*+*+*"

# Check row count in D1
wrangler d1 execute ai-gateway-logs-db --remote \
  --command "SELECT COUNT(*) FROM gateway_logs;"
```

## Related

- `workers-analytics-engine-sql-api.md` — for high-volume metric aggregation without D1 write limits
- `cloudflare-r2-lifecycle-auto-delete.md` — archiving large prompt/response blobs to R2

## Sources

- https://developers.cloudflare.com/ai-gateway/observability/logging/
- https://developers.cloudflare.com/ai-gateway/reference/api/
- https://developers.cloudflare.com/d1/
