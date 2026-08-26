# GitHub Copilot Metrics API: D1 Time-Series Storage and Analytics Dashboards

- Date: 2026-08-22
- Author: example.com
- Status: production

## Tracking Engineering Productivity Trends with Copilot Usage Data

GitHub's Copilot Metrics API exposes daily aggregated usage statistics for an organisation or enterprise: code suggestion acceptance rates, active seat counts, language breakdowns, IDE distribution, and code review metrics. These numbers are valuable for engineering leaders who need to demonstrate ROI, identify underserved teams, or correlate Copilot adoption with shipping velocity—but the API only returns a rolling 28-day window, so any trend analysis beyond a month requires your own persistence layer.

A Cloudflare Worker scheduled with a Cron Trigger can poll the Metrics API once per day, normalise the response into a relational schema, and upsert rows into a D1 SQLite database. Because D1 is globally replicated and queryable over SQL, the same data drives both a REST endpoint for internal tools and direct queries from Cloudflare Analytics Engine for aggregated time-series visualisations without spinning up a separate data warehouse.

The pattern also serves compliance use cases: enterprises subject to software development productivity audits can export the D1 table to a signed R2 object as a quarterly snapshot and share the URL with auditors without granting GitHub API access.

## Context

- API: `GET /orgs/{org}/copilot/metrics` (requires `copilot_usage_breakdown` scope on a GitHub App or fine-grained PAT)
- Scheduler: Cloudflare Workers Cron Trigger (daily at 06:00 UTC)
- Storage: D1 database `copilot_metrics` with a `daily_stats` table
- Dashboards: Cloudflare Analytics Engine for time-series, custom Workers endpoint for JSON exports
- Auth: GitHub App private key stored as a Workers Secret, generating short-lived installation tokens

## D1 Schema

```sql
-- migrations/0001_copilot_metrics.sql
CREATE TABLE IF NOT EXISTS daily_stats (
  date             TEXT    NOT NULL,
  team_slug        TEXT    NOT NULL DEFAULT '__org__',
  active_users     INTEGER NOT NULL DEFAULT 0,
  engaged_users    INTEGER NOT NULL DEFAULT 0,
  suggestions_shown    INTEGER NOT NULL DEFAULT 0,
  suggestions_accepted INTEGER NOT NULL DEFAULT 0,
  lines_suggested  INTEGER NOT NULL DEFAULT 0,
  lines_accepted   INTEGER NOT NULL DEFAULT 0,
  acceptance_rate  REAL    GENERATED ALWAYS AS (
    CASE WHEN suggestions_shown = 0 THEN 0
         ELSE CAST(suggestions_accepted AS REAL) / suggestions_shown
    END
  ) VIRTUAL,
  fetched_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (date, team_slug)
);

CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats (date DESC);
```

## Scheduled Worker: Fetching and Persisting Metrics

```ts
// src/metrics-collector.ts
import { createAppAuth } from "@octokit/auth-app";

export interface Env {
  DB: D1Database;
  ANALYTICS: AnalyticsEngineDataset;
  GH_APP_ID: string;
  GH_APP_PRIVATE_KEY: string;       // PEM, stored as Workers Secret
  GH_APP_INSTALLATION_ID: string;
  GH_ORG: string;
}

interface CopilotDayMetrics {
  date: string;
  total_active_users: number;
  total_engaged_users: number;
  copilot_ide_code_completions?: {
    total_suggestions_count: number;
    total_acceptances_count: number;
    total_lines_suggested: number;
    total_lines_accepted: number;
  };
}

async function getInstallationToken(env: Env): Promise<string> {
  const auth = createAppAuth({
    appId: env.GH_APP_ID,
    privateKey: env.GH_APP_PRIVATE_KEY,
    installationId: env.GH_APP_INSTALLATION_ID,
  });
  const { token } = await auth({ type: "installation" });
  return token;
}

async function fetchOrgMetrics(token: string, org: string): Promise<CopilotDayMetrics[]> {
  const res = await fetch(
    `https://api.github.com/orgs/${org}/copilot/metrics`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
    }
  );
  if (!res.ok) throw new Error(`GitHub API ${res.status}: ${await res.text()}`);
  return res.json<CopilotDayMetrics[]>();
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const token = await getInstallationToken(env);
    const days = await fetchOrgMetrics(token, env.GH_ORG);

    const stmt = env.DB.prepare(`
      INSERT OR REPLACE INTO daily_stats
        (date, team_slug, active_users, engaged_users,
         suggestions_shown, suggestions_accepted, lines_suggested, lines_accepted)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);

    const batch = days.map((day) => {
      const completions = day.copilot_ide_code_completions;
      const row = stmt.bind(
        day.date,
        "__org__",
        day.total_active_users,
        day.total_engaged_users,
        completions?.total_suggestions_count ?? 0,
        completions?.total_acceptances_count ?? 0,
        completions?.total_lines_suggested ?? 0,
        completions?.total_lines_accepted ?? 0,
      );

      // Mirror to Analytics Engine for time-series aggregation
      env.ANALYTICS.writeDataPoint({
        blobs: [env.GH_ORG, "__org__"],
        doubles: [
          day.total_active_users,
          day.total_engaged_users,
          completions?.total_suggestions_count ?? 0,
          completions?.total_acceptances_count ?? 0,
        ],
        timestamps: [new Date(day.date).getTime()],
        indexes: [day.date],
      });

      return row;
    });

    await env.DB.batch(batch);
    console.log(`Upserted ${days.length} metric days for ${env.GH_ORG}`);
  },

  // HTTP handler for internal dashboards
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/metrics/summary") {
      const rows = await env.DB.prepare(`
        SELECT date, active_users, engaged_users, acceptance_rate,
               lines_accepted
        FROM daily_stats
        WHERE team_slug = '__org__'
        ORDER BY date DESC
        LIMIT 90
      `).all();
      return Response.json(rows.results);
    }
    return new Response("Not Found", { status: 404 });
  },
};
```

## wrangler.toml Configuration

```toml
# wrangler.toml
name = "copilot-metrics-collector"
main = "src/metrics-collector.ts"
compatibility_date = "2026-01-01"

[triggers]
crons = ["0 6 * * *"]   # 06:00 UTC daily

[[d1_databases]]
binding = "DB"
database_name = "copilot-metrics"
database_id = "<your-d1-database-id>"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "copilot_usage"

[vars]
GH_ORG = "my-org"
GH_APP_ID = "123456"
GH_APP_INSTALLATION_ID = "78901234"
# GH_APP_PRIVATE_KEY stored via: wrangler secret put GH_APP_PRIVATE_KEY
```

## Analytics Engine Dashboard Queries

Query the `copilot_usage` dataset from Cloudflare's GraphQL Analytics API or the Workers Analytics Engine REST API to power a dashboard without hitting D1 on every page load:

```ts
// Example GraphQL query for 30-day acceptance rate trend
const TREND_QUERY = `
  query CopilotTrend($accountId: String!, $since: String!, $until: String!) {
    viewer {
      accounts(filter: { accountTag: $accountId }) {
        copilotUsageAdaptiveGroups(
          filter: { date_geq: $since, date_leq: $until }
          groupBy: [date]
          orderBy: [date_ASC]
          limit: 90
        ) {
          date: dimensions { date }
          suggestionsShown: sum { suggestions_shown }
          suggestionsAccepted: sum { suggestions_accepted }
        }
      }
    }
  }
`;
```

## Anti-patterns

- Polling the GitHub Metrics API more than once per day — data is updated daily, extra calls waste quota and the 5000-req/hour rate limit is shared with other integrations
- Storing GitHub App private keys in `wrangler.toml` — always use `wrangler secret put`
- Selecting `SELECT *` from D1 without a `LIMIT` clause in dashboard endpoints — the table grows without bound over time
- Mixing org-level and team-level metrics in the same row without the `team_slug` discriminator — aggregation queries silently double-count
- Relying solely on Analytics Engine for compliance exports — its retention window is 18 months; D1 is permanent

## Gotchas

- The Copilot Metrics API requires the `copilot_usage_breakdown` scope on the GitHub App, which is different from the `copilot_user_management` scope for seat provisioning
- `copilot_ide_code_completions` is `undefined` for days where the org had zero activity — guard with optional chaining before accessing nested fields
- D1 `INSERT OR REPLACE` deletes and re-inserts the row (triggering the generated `acceptance_rate` column recalculation); `INSERT OR IGNORE ... ON CONFLICT DO UPDATE` is more efficient for updates
- Cloudflare Analytics Engine `writeDataPoint` is fire-and-forget; failures are not surfaced unless you wrap in try/catch and emit to a log binding
- The `crons` trigger is best-effort; if the Worker fails, it does not retry automatically — add an alerting step or a daily sanity-check query comparing `MAX(date)` to yesterday

## Verification

```ts
// Confirm the cron fires and writes at least one row
import { env } from "cloudflare:test";
import worker from "./src/metrics-collector";

test("scheduled handler upserts metric rows into D1", async () => {
  // Seed with a mock day
  await env.DB.prepare(
    "INSERT OR REPLACE INTO daily_stats (date, team_slug, active_users, engaged_users, suggestions_shown, suggestions_accepted, lines_suggested, lines_accepted) VALUES (?,?,?,?,?,?,?,?)"
  ).bind("2026-08-21", "__org__", 42, 30, 500, 350, 1200, 900).run();

  const row = await env.DB.prepare(
    "SELECT acceptance_rate FROM daily_stats WHERE date = '2026-08-21'"
  ).first<{ acceptance_rate: number }>();

  expect(row?.acceptance_rate).toBeCloseTo(0.7, 2);
});
```

## Related

- `documentation/categories/github/github-actions-cloudflare-d1-migration-pipeline.md`
- `documentation/categories/github/audit-log-streaming-siem.md`
- `documentation/categories/github/copilot-workspace-ai-development-workflows.md`

## Sources

- https://docs.github.com/en/rest/copilot/copilot-metrics?apiVersion=2022-11-28
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/d1/
- https://github.com/octokit/auth-app.js
