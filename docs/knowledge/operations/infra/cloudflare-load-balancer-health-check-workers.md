# Cloudflare Load Balancer — Custom Health Check Worker

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Cloudflare Load Balancer's built-in health checks only support HTTP/HTTPS endpoints returning 2xx. Your origins expose a more nuanced health contract (partial degradation, dependency checks) that requires custom logic. You need a Worker to probe the origin, persist pass/fail state to D1, and expose a synthetic health endpoint that the load balancer pool monitors.

---

## Context
The pattern splits responsibility into two Workers: a **probe Worker** (scheduled cron) that tests each origin and writes results to D1, and a **monitor Worker** (HTTP) that the load balancer polls. The load balancer sees a simple 200/503 response while the actual probe logic can be arbitrarily complex. D1 provides durable, queryable state across the two Workers without requiring an external database. Configurable timeout ensures the probe never blocks longer than the load balancer's own health check interval.

---

## D1 Schema
```sql
CREATE TABLE IF NOT EXISTS health_checks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  origin_id    TEXT    NOT NULL,
  origin_url   TEXT    NOT NULL,
  status       TEXT    NOT NULL, -- 'pass' | 'fail' | 'degraded'
  http_status  INTEGER,
  latency_ms   INTEGER,
  detail       TEXT,
  checked_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_hc_origin ON health_checks (origin_id, checked_at DESC);

-- Materialized latest-state view (SQLite compatible)
CREATE VIEW IF NOT EXISTS health_latest AS
  SELECT h.*
  FROM health_checks h
  INNER JOIN (
    SELECT origin_id, MAX(checked_at) AS latest
    FROM health_checks
    GROUP BY origin_id
  ) m ON h.origin_id = m.origin_id AND h.checked_at = m.latest;
```

## Probe Worker (scheduled)
```typescript
// src/probe-worker.ts
export interface Env {
  DB: D1Database;
  ORIGINS: string; // JSON: [{id, url, timeout_ms?, expected_body?}]
}

interface OriginConfig {
  id: string;
  url: string;
  timeout_ms?: number;
  expected_body?: string;
}

interface ProbeResult {
  status: 'pass' | 'fail' | 'degraded';
  http_status: number | null;
  latency_ms: number;
  detail: string;
}

async function probeOrigin(origin: OriginConfig): Promise<ProbeResult> {
  const timeoutMs = origin.timeout_ms ?? 5000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const start = Date.now();

  try {
    const resp = await fetch(origin.url, {
      method: 'GET',
      signal: controller.signal,
      headers: { 'User-Agent': 'CF-HealthProbe/1.0' },
    });
    const latency_ms = Date.now() - start;
    const body = await resp.text();

    if (!resp.ok) {
      return { status: 'fail', http_status: resp.status, latency_ms, detail: `HTTP ${resp.status}` };
    }

    if (origin.expected_body && !body.includes(origin.expected_body)) {
      return {
        status: 'degraded',
        http_status: resp.status,
        latency_ms,
        detail: `Body missing expected string: "${origin.expected_body}"`,
      };
    }

    // Warn on high latency but don't fail
    const status = latency_ms > timeoutMs * 0.8 ? 'degraded' : 'pass';
    return { status, http_status: resp.status, latency_ms, detail: 'ok' };
  } catch (err) {
    return {
      status: 'fail',
      http_status: null,
      latency_ms: Date.now() - start,
      detail: err instanceof Error ? err.message : 'unknown error',
    };
  } finally {
    clearTimeout(timer);
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const origins: OriginConfig[] = JSON.parse(env.ORIGINS);

    await Promise.all(
      origins.map(async (origin) => {
        const result = await probeOrigin(origin);
        await env.DB
          .prepare(
            `INSERT INTO health_checks (origin_id, origin_url, status, http_status, latency_ms, detail)
             VALUES (?, ?, ?, ?, ?, ?)`
          )
          .bind(
            origin.id,
            origin.url,
            result.status,
            result.http_status,
            result.latency_ms,
            result.detail
          )
          .run();
      })
    );
  },
};
```

## Monitor Worker (HTTP — polled by Load Balancer)
```typescript
// src/monitor-worker.ts
export interface Env {
  DB: D1Database;
  POOL_ORIGIN_ID: string; // origin to surface for this pool endpoint
}

interface HealthRow {
  origin_id: string;
  origin_url: string;
  status: string;
  http_status: number | null;
  latency_ms: number;
  detail: string;
  checked_at: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // /health/:origin_id or use POOL_ORIGIN_ID binding
    const originId = url.pathname.split('/')[2] ?? env.POOL_ORIGIN_ID;

    const row = await env.DB
      .prepare(
        'SELECT * FROM health_latest WHERE origin_id = ? LIMIT 1'
      )
      .bind(originId)
      .first<HealthRow>();

    if (!row) {
      return Response.json(
        { error: 'No health data', origin_id: originId },
        { status: 503 }
      );
    }

    const isHealthy = row.status === 'pass';
    const isDegraded = row.status === 'degraded';

    // Cloudflare Load Balancer expects 2xx for healthy, non-2xx for unhealthy
    const httpStatus = isHealthy || isDegraded ? 200 : 503;

    return Response.json(
      {
        origin_id: row.origin_id,
        status: row.status,
        latency_ms: row.latency_ms,
        detail: row.detail,
        checked_at: row.checked_at,
      },
      {
        status: httpStatus,
        headers: {
          'Cache-Control': 'no-store',
          'X-Health-Status': row.status,
        },
      }
    );
  },
};
```

## `wrangler.toml` (probe worker)
```toml
name = "health-probe"
main = "src/probe-worker.ts"
compatibility_date = "2024-09-23"

[triggers]
crons = ["* * * * *"]  # every minute

[[d1_databases]]
binding = "DB"
database_name = "health-state"
database_id = "<your-d1-id>"

[vars]
ORIGINS = '[{"id":"api-1","url":"https://api1.example.com/health","timeout_ms":4000,"expected_body":"\"status\":\"ok\""},{"id":"api-2","url":"https://api2.example.com/health","timeout_ms":4000}]'
```

---

## Anti-patterns
- **Using the probe Worker as the Load Balancer health endpoint directly** — a scheduled Worker has no HTTP interface; the monitor Worker is the correct HTTP facade.
- **Storing only the latest health row** — keep history in `health_checks` for trend analysis and on-call debugging; the `health_latest` view handles the fast-path read.
- **Setting the cron interval longer than the Load Balancer health check interval** — if the LB checks every 30 s and your probe runs every 5 min, the LB will see stale data; match or exceed the LB frequency.

---

## Gotchas
- The `health_latest` view uses a correlated subquery which is efficient for small origin counts but may degrade on thousands of rows; add a `checked_at` partial index or use an `upsert` pattern for scale.
- Cloudflare Load Balancer pools require the health check URL to return within the configured check interval; if the monitor Worker itself times out (>30 s default), the pool marks the origin down regardless of actual health.
- D1 is not designed for sub-second write frequency; if your cron runs every 10 s across many origins, batch inserts with a single `prepare()` call using `db.batch()`.

---

## Verification
```bash
# Deploy probe Worker
wrangler deploy --config wrangler.probe.toml

# Deploy monitor Worker
wrangler deploy --config wrangler.monitor.toml

# Trigger probe cron manually via REST API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/health-probe/schedules" \
  -H "Authorization: Bearer $CF_API_TOKEN"

# Query latest health state
wrangler d1 execute health-state --command \
  "SELECT * FROM health_latest;"

# Hit the monitor Worker endpoint
curl -i https://health-monitor.<sub>.workers.dev/health/api-1
```

---

## Related
- `cloudflare-tunnel-private-network-workers.md`
- `cloudflare-spectrum-tcp-proxy-workers.md`

---

## Sources
- Cloudflare Load Balancer health checks — https://developers.cloudflare.com/load-balancing/understand-basics/health-details/
- Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- D1 Workers binding — https://developers.cloudflare.com/d1/worker-api/
