# Deployment Cost Attribution Per Service: D1 Billing Ledger with Analytics Engine

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: No Visibility Into Per-Service Cloudflare Spend

Platform teams running dozens of Workers services on Cloudflare face a shared-billing blind spot. The Cloudflare dashboard shows aggregate account spend, but not which service, team, or deployment event is responsible for a spike. Without attribution, engineers can't answer basic FinOps questions: which service regressed to O(n) invocations, which team's cron job is driving D1 reads, or whether a canary deploy doubled compute costs before it was promoted.

This article describes a system that instruments every deploy event with its Worker name, team label, and a cost snapshot drawn from the Cloudflare Billing API, stores a running ledger in D1, and surfaces per-service cost trends through a read API served by another Worker.

The architecture uses three moving parts: a deploy-event Worker that runs after `wrangler deploy`, a scheduled aggregator Worker that pulls billing API data nightly, and a D1 database acting as the single source of truth for cost attribution records.

## Context

- Cloudflare Workers with Wrangler v3+
- D1 (SQLite) for the cost ledger
- Workers Analytics Engine for high-frequency deploy event recording
- Cloudflare Billing API (v4) for actual invoice line items
- GitHub Actions CI/CD calling `wrangler deploy` per service

## D1 Schema and Cost Ledger

The ledger has two tables: `deploy_events` records each deployment with metadata, and `cost_snapshots` holds billing API data pulled on a schedule.

```ts
// schema.sql — run via `wrangler d1 execute cost-ledger --file=schema.sql`
// (executed once at database bootstrap)

const SCHEMA = `
CREATE TABLE IF NOT EXISTS deploy_events (
  id          TEXT PRIMARY KEY,
  service     TEXT NOT NULL,
  team        TEXT NOT NULL,
  environment TEXT NOT NULL,
  version_id  TEXT NOT NULL,
  deployed_at INTEGER NOT NULL,   -- Unix ms
  duration_ms INTEGER,
  triggered_by TEXT              -- github actor or "scheduled"
);

CREATE TABLE IF NOT EXISTS cost_snapshots (
  id            TEXT PRIMARY KEY,
  service       TEXT NOT NULL,
  period_start  TEXT NOT NULL,   -- YYYY-MM-DD
  period_end    TEXT NOT NULL,
  requests      INTEGER,
  cpu_ms        INTEGER,
  d1_reads      INTEGER,
  d1_writes     INTEGER,
  usd_estimated REAL,
  recorded_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deploy_service ON deploy_events(service, deployed_at);
CREATE INDEX IF NOT EXISTS idx_snap_service   ON cost_snapshots(service, period_start);
`;
```

## Deploy-Event Recording Worker

This Worker is invoked by the CI pipeline immediately after `wrangler deploy` succeeds. It writes to both D1 and Analytics Engine — D1 for queryable history, Analytics Engine for real-time dashboards.

```ts
// src/deploy-recorder.ts
import { WorkerEntrypoint } from 'cloudflare:workers';

interface Env {
  DB: D1Database;
  AE: AnalyticsEngineDataset;
  DEPLOY_SECRET: string;
}

interface DeployPayload {
  service: string;
  team: string;
  environment: string;
  version_id: string;
  duration_ms: number;
  triggered_by: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.headers.get('X-Deploy-Secret') !== env.DEPLOY_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }

    const body = await req.json<DeployPayload>();
    const id = crypto.randomUUID();
    const now = Date.now();

    await env.DB.prepare(`
      INSERT INTO deploy_events
        (id, service, team, environment, version_id, deployed_at, duration_ms, triggered_by)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(id, body.service, body.team, body.environment,
             body.version_id, now, body.duration_ms, body.triggered_by).run();

    // Analytics Engine — blobs are labels, doubles are metrics
    env.AE.writeDataPoint({
      blobs:   [body.service, body.team, body.environment],
      doubles: [body.duration_ms, 1],
      indexes: [body.service],
    });

    return Response.json({ id, recorded_at: now });
  },
} satisfies ExportedHandler<Env>;
```

## Scheduled Aggregator: Billing API Pull

A nightly cron Worker calls the Cloudflare Billing API, joins usage stats to known services by Worker name prefix, and writes cost snapshots to D1.

```ts
// src/billing-aggregator.ts
interface Env {
  DB: D1Database;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;   // needs Billing:Read + Analytics:Read
}

async function fetchWorkerUsage(env: Env, date: string) {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}`
    + `/workers/scripts/usage?date=${date}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
  });
  return (await res.json<any>()).result ?? [];
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const today = new Date().toISOString().slice(0, 10);
    const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);

    const usageRecords: any[] = await fetchWorkerUsage(env, yesterday);

    const stmts = usageRecords.map((r: any) => {
      const id = `${r.script_name}::${yesterday}`;
      return env.DB.prepare(`
        INSERT OR REPLACE INTO cost_snapshots
          (id, service, period_start, period_end, requests, cpu_ms, d1_reads, d1_writes, usd_estimated, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(id, r.script_name, yesterday, today,
               r.requests ?? 0, r.cpu_ms ?? 0,
               r.d1_rows_read ?? 0, r.d1_rows_written ?? 0,
               r.estimated_cost_usd ?? 0, Date.now());
    });

    await env.DB.batch(stmts);
    console.log(`Wrote ${stmts.length} cost snapshots for ${yesterday}`);
  },
} satisfies ExportedHandler<Env>;
```

## Cost Attribution API

A read-only Worker exposes aggregated cost-per-service and cost-per-team endpoints used by internal dashboards.

```ts
// src/cost-api.ts
interface Env { DB: D1Database; }

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === '/by-team') {
      const rows = await env.DB.prepare(`
        SELECT team, SUM(usd_estimated) AS total_usd,
               COUNT(*) AS deploy_count
        FROM cost_snapshots cs
        JOIN deploy_events de ON de.service = cs.service
        WHERE cs.period_start >= date('now','-30 days')
        GROUP BY team ORDER BY total_usd DESC
      `).all();
      return Response.json(rows.results);
    }
    if (url.pathname === '/by-service') {
      const rows = await env.DB.prepare(`
        SELECT service, SUM(usd_estimated) AS total_usd,
               SUM(requests) AS total_requests,
               SUM(cpu_ms) AS total_cpu_ms
        FROM cost_snapshots
        WHERE period_start >= date('now','-30 days')
        GROUP BY service ORDER BY total_usd DESC LIMIT 50
      `).all();
      return Response.json(rows.results);
    }
    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Relying on Cloudflare dashboard exports instead of API — manual CSV exports don't integrate with CI or alerting
- Using KV for the cost ledger — KV has no SQL aggregation; D1 lets you GROUP BY team/service directly
- Pulling billing data at deploy time — the billing API lags ~24h; pull on a schedule, not inline
- Not labeling Analytics Engine blobs — unlabeled datapoints can't be filtered by service in Grafana or the CF dashboard

## Gotchas

- The Cloudflare Workers usage API is undocumented for per-script granularity in some plan tiers; validate that `script_name` is present in responses for your account
- D1 `batch()` is limited to 100 statements per call; chunk large usage record sets
- Analytics Engine datapoints are eventually consistent with a ~5 min lag
- The CF API token needs both `Workers Analytics:Read` and `Account:Read` scopes for the billing endpoint

## Verification

```ts
// Quick sanity check: confirm at least one deploy event was recorded
const result = await env.DB.prepare(
  `SELECT COUNT(*) AS cnt FROM deploy_events WHERE deployed_at > ?`
).bind(Date.now() - 86_400_000).first<{ cnt: number }>();
console.assert((result?.cnt ?? 0) > 0, 'No deploy events in last 24h');
```

## Related

- [cost-per-deployment.md](cost-per-deployment.md)
- [finops-cost-optimization.md](finops-cost-optimization.md)
- [infrastructure-cost-tagging.md](infrastructure-cost-tagging.md)
- [deployment-metrics-tracking.md](deployment-metrics-tracking.md)
- wrangler-deploy-pipeline.md

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/d1/
- https://api.cloudflare.com/#accounts-billing-profile-properties
- https://developers.cloudflare.com/workers/observability/
