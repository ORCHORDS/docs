# Cloudflare Workers Deployment Frequency DORA Metrics

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

An engineering team adopting DORA metrics for a Cloudflare Workers-based platform lacks a pipeline to capture deployment frequency and change failure rate from Wrangler deploys. Unlike Kubernetes or Lambda, Workers deployments do not emit native CloudWatch/Datadog events; deployment telemetry must be captured from the Cloudflare API audit log and the CI pipeline. Without this data, the team cannot benchmark against the Elite/High performer thresholds or track improvement over time.

## Context

The four DORA metrics — deployment frequency, lead time for changes, mean time to restore (MTTR), and change failure rate — require event-level deployment records as their raw input. Cloudflare's Audit Log API records every `workers.script.update` event with timestamp, actor (API token identity), script name, and environment. By polling this API on a schedule, correlating with GitHub commit metadata, and persisting records in D1, teams can compute all four DORA metrics without third-party DORA tools. A Tail Worker captures runtime error rate per deployment version to derive change failure rate automatically.

## Capturing Deployment Events from the Cloudflare Audit Log

A scheduled Cloudflare Worker polls the Audit Log API every 15 minutes, deduplicates events via D1, and stores normalised deployment records.

```typescript
// workers/dora-collector/src/index.ts
export interface Env {
  DB: D1Database;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
}

interface AuditLogEvent {
  id: string;
  action: { type: string; result: string };
  actor: { type: string; email: string; id: string };
  resource: { type: string; id: string };
  metadata: Record<string, string>;
  when: string; // ISO8601
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(collectDeployments(env));
  },
} satisfies ExportedHandler<Env>;

async function collectDeployments(env: Env): Promise<void> {
  const since = await getLastCollectedTimestamp(env.DB);
  const url = new URL(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/audit_logs`
  );
  url.searchParams.set("action.type", "workers.script.update");
  url.searchParams.set("since", since);
  url.searchParams.set("per_page", "100");

  const resp = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
  });

  if (!resp.ok) {
    throw new Error(`Audit log fetch failed: ${resp.status}`);
  }

  const data = (await resp.json()) as { result: AuditLogEvent[]; success: boolean };

  const events = data.result.filter(
    (e) => e.action.result === "success" && e.resource.type === "workers_script"
  );

  if (events.length === 0) return;

  const stmt = env.DB.prepare(
    `INSERT OR IGNORE INTO deployments
       (id, script_name, actor_email, deployed_at, environment)
     VALUES (?, ?, ?, ?, ?)`
  );

  const batch = events.map((e) =>
    stmt.bind(
      e.id,
      e.resource.id,
      e.actor.email,
      e.when,
      e.metadata?.environment ?? "production"
    )
  );

  await env.DB.batch(batch);
  await updateLastCollectedTimestamp(env.DB, events[0].when);
}

async function getLastCollectedTimestamp(db: D1Database): Promise<string> {
  const row = await db
    .prepare("SELECT value FROM kv_store WHERE key = 'last_audit_ts'")
    .first<{ value: string }>();
  return row?.value ?? new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
}

async function updateLastCollectedTimestamp(
  db: D1Database,
  ts: string
): Promise<void> {
  await db
    .prepare(
      "INSERT OR REPLACE INTO kv_store (key, value) VALUES ('last_audit_ts', ?)"
    )
    .bind(ts)
    .run();
}
```

## D1 Schema and DORA Metric Queries

```bash
# migrations/001_dora_schema.sql
```

```sql
-- migrations/001_dora_schema.sql
CREATE TABLE IF NOT EXISTS deployments (
  id            TEXT PRIMARY KEY,
  script_name   TEXT NOT NULL,
  actor_email   TEXT NOT NULL,
  deployed_at   TEXT NOT NULL,  -- ISO8601
  environment   TEXT NOT NULL DEFAULT 'production',
  failed        INTEGER NOT NULL DEFAULT 0  -- set to 1 by change-failure detector
);

CREATE TABLE IF NOT EXISTS kv_store (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deployments_script_env_ts
  ON deployments (script_name, environment, deployed_at);

-- DORA: Deployment frequency — deployments per day over rolling 30 days
-- (run via Workers Analytics API endpoint)
SELECT
  script_name,
  environment,
  COUNT(*) AS total_deploys,
  ROUND(COUNT(*) * 1.0 / 30, 2) AS deploys_per_day,
  CASE
    WHEN COUNT(*) * 1.0 / 30 >= 1   THEN 'Elite'
    WHEN COUNT(*) * 1.0 / 30 >= 0.14 THEN 'High'
    WHEN COUNT(*) * 1.0 / 30 >= 0.03 THEN 'Medium'
    ELSE 'Low'
  END AS dora_band
FROM deployments
WHERE environment = 'production'
  AND deployed_at >= datetime('now', '-30 days')
GROUP BY script_name, environment
ORDER BY deploys_per_day DESC;

-- DORA: Change failure rate — fraction of deployments that triggered a rollback
SELECT
  script_name,
  ROUND(SUM(failed) * 100.0 / COUNT(*), 1) AS change_failure_rate_pct
FROM deployments
WHERE environment = 'production'
  AND deployed_at >= datetime('now', '-30 days')
GROUP BY script_name;
```

## Exposing DORA Metrics via a Worker API

```typescript
// workers/dora-api/src/index.ts — serve DORA metrics as JSON
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === "/metrics/dora") {
      const [freqResult, cfrResult] = await Promise.all([
        env.DB.prepare(`
          SELECT script_name, environment,
                 COUNT(*) AS total_deploys,
                 ROUND(COUNT(*) * 1.0 / 30, 2) AS deploys_per_day
          FROM deployments
          WHERE environment = 'production'
            AND deployed_at >= datetime('now', '-30 days')
          GROUP BY script_name, environment
        `).all(),
        env.DB.prepare(`
          SELECT script_name,
                 ROUND(SUM(failed) * 100.0 / COUNT(*), 1) AS cfr_pct
          FROM deployments
          WHERE environment = 'production'
            AND deployed_at >= datetime('now', '-30 days')
          GROUP BY script_name
        `).all(),
      ]);

      return Response.json({
        window: "30d",
        generated_at: new Date().toISOString(),
        deployment_frequency: freqResult.results,
        change_failure_rate: cfrResult.results,
      });
    }

    return new Response("Not Found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Deriving deployment frequency solely from GitHub Actions workflow runs — CI runs do not guarantee a Cloudflare deploy succeeded; only Audit Log events confirm an actual script update at the edge.
- Using `wrangler tail` event counts as a change failure proxy — tail events show runtime errors for ALL requests, not per-deployment-version error rates.
- Storing DORA data in Workers KV instead of D1 — KV has no query capability; aggregate SQL queries like lead time histograms are impossible without scanning every key.
- Computing DORA metrics in a single long-lived cron Worker without a continuation token — if the audit log returns more than 100 events in one window, pagination is silently dropped.

## Gotchas

- The Cloudflare Audit Log API retains events for only 6 months; if collection lapses for more than that window, historical data is permanently lost and must be reconstructed from CI logs.
- `workers.script.update` events are emitted for both `wrangler deploy` and `wrangler rollback`; rollback events should be flagged as `failed = 1` on the preceding deployment, not treated as a new positive deployment.
- The actor identity in audit logs reflects the API token's associated email, not the GitHub actor; teams must maintain a token→team-member mapping to attribute deployments to individuals for lead time calculation.

## Verification

```bash
# Query DORA metrics endpoint
curl -s https://dora-api.my-team.workers.dev/metrics/dora \
  | jq '.deployment_frequency[] | select(.script_name == "my-api-worker")'

# Confirm D1 is receiving records from the collector
wrangler d1 execute dora-db \
  --command "SELECT COUNT(*), MAX(deployed_at) FROM deployments WHERE environment='production';"
```

## Related

- `infra/wrangler-deploys.md`
- `infra/wrangler-toml-multi-environment-config.md`
- `infra/terraform-cloudflare-provider-workers-d1.md`
- `infra/sre-error-budget-policy.md`

## Sources

- https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance
- https://developers.cloudflare.com/fundamentals/account-and-billing/account-security/review-audit-logs/
- https://developers.cloudflare.com/d1/
