# GitHub Issue Metrics Collection via Workers + Analytics Engine

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Engineering teams need visibility into issue health: how many issues are open right now, how quickly they close, how old the backlog is, and whether the trend is improving or degrading. Exporting this data on a schedule and querying it over time requires a durable write path and a fast aggregate read path.

## Context

Cloudflare Analytics Engine is a time-series columnar store designed for high-frequency writes and SQL aggregation. A Worker can call `env.ANALYTICS.writeDataPoint()` from a Cron Trigger, record snapshots of GitHub issue state, and then serve a dashboard endpoint that queries those snapshots with the `analytics_engine_datasets` SQL API.

Key limits to know:
- Analytics Engine blobs: up to 20 blob columns and 20 double columns per dataset.
- Writes are fire-and-forget; there is no confirmation that a point landed.
- The SQL API is available at `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`.

## Solution

### wrangler.toml binding

```toml
name = "issue-metrics"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "METRICS"
dataset = "github_issue_metrics"

[triggers]
crons = ["0 * * * *"]  # every hour

[vars]
GH_OWNER = "orchords"
GH_REPO = "example project"
```

### Types

```typescript
export interface Env {
  METRICS: AnalyticsEngineDataset;
  GH_TOKEN: string;       // secret
  CF_ACCOUNT_ID: string;  // secret
  CF_API_TOKEN: string;   // secret
  GH_OWNER: string;
  GH_REPO: string;
}

interface IssueSnapshot {
  openCount: number;
  closedLast24h: number;
  medianAgeHours: number;
  p90AgeHours: number;
  labelCounts: Record<string, number>;
}
```

### GitHub data collection helper

```typescript
async function fetchIssueSnapshot(env: Env): Promise<IssueSnapshot> {
  const headers = {
    Authorization: `Bearer ${env.GH_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };

  // 1. Open issue count
  const openRes = await fetch(
    `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/issues?state=open&per_page=1`,
    { headers }
  );
  const linkHeader = openRes.headers.get("Link") ?? "";
  const lastPageMatch = linkHeader.match(/page=(\d+)>; rel="last"/);
  const openCount = lastPageMatch ? parseInt(lastPageMatch[1], 10) : 1;

  // 2. Issues closed in last 24 h
  const since = new Date(Date.now() - 86_400_000).toISOString();
  const closedRes = await fetch(
    `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/issues?state=closed&since=${since}&per_page=100`,
    { headers }
  );
  const closedIssues: any[] = await closedRes.json();
  const closedLast24h = closedIssues.filter((i) => !i.pull_request).length;

  // 3. Age distribution — sample first 100 open issues
  const ageRes = await fetch(
    `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/issues?state=open&per_page=100&sort=created&direction=asc`,
    { headers }
  );
  const openIssues: any[] = await ageRes.json();
  const now = Date.now();
  const agesHours = openIssues
    .filter((i) => !i.pull_request)
    .map((i) => (now - new Date(i.created_at).getTime()) / 3_600_000)
    .sort((a, b) => a - b);

  const medianAgeHours = agesHours[Math.floor(agesHours.length / 2)] ?? 0;
  const p90AgeHours = agesHours[Math.floor(agesHours.length * 0.9)] ?? 0;

  // 4. Label distribution
  const labelCounts: Record<string, number> = {};
  for (const issue of openIssues) {
    for (const label of issue.labels as { name: string }[]) {
      labelCounts[label.name] = (labelCounts[label.name] ?? 0) + 1;
    }
  }

  return { openCount, closedLast24h, medianAgeHours, p90AgeHours, labelCounts };
}
```

### Analytics Engine write

```typescript
function writeSnapshot(env: Env, snapshot: IssueSnapshot): void {
  // blobs[0] = top label name, blobs[1] = repo slug
  const topLabel =
    Object.entries(snapshot.labelCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "none";

  env.METRICS.writeDataPoint({
    indexes: [`${env.GH_OWNER}/${env.GH_REPO}`],
    blobs: [topLabel, `${env.GH_OWNER}/${env.GH_REPO}`],
    doubles: [
      snapshot.openCount,
      snapshot.closedLast24h,
      snapshot.medianAgeHours,
      snapshot.p90AgeHours,
    ],
  });
}
```

### SQL aggregation query helper

```typescript
async function queryMetrics(env: Env, sql: string): Promise<any> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "text/plain",
      },
      body: sql,
    }
  );
  if (!res.ok) throw new Error(`Analytics SQL error: ${res.status}`);
  return res.json();
}
```

### Dashboard endpoint + trend detection

```typescript
async function handleDashboard(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const days = parseInt(url.searchParams.get("days") ?? "7", 10);

  const trendSql = `
    SELECT
      toStartOfHour(timestamp) AS hour,
      SUM(_sample_interval * double1) / SUM(_sample_interval) AS avg_open,
      SUM(_sample_interval * double2) / SUM(_sample_interval) AS avg_closed_24h,
      SUM(_sample_interval * double3) / SUM(_sample_interval) AS avg_median_age_h
    FROM github_issue_metrics
    WHERE
      timestamp > NOW() - INTERVAL '${days}' DAY
      AND index1 = '${env.GH_OWNER}/${env.GH_REPO}'
    GROUP BY hour
    ORDER BY hour ASC
  `;

  const data = await queryMetrics(env, trendSql);
  const rows: any[] = data.data ?? [];

  // Simple trend: compare first half vs second half average open count
  const mid = Math.floor(rows.length / 2);
  const firstHalf = rows.slice(0, mid);
  const secondHalf = rows.slice(mid);
  const avg = (arr: any[]) =>
    arr.reduce((s, r) => s + (r.avg_open ?? 0), 0) / (arr.length || 1);
  const trend = avg(secondHalf) > avg(firstHalf) ? "rising" : "falling";

  return Response.json({ trend, rows });
}
```

### Worker entry point

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const snapshot = await fetchIssueSnapshot(env);
    writeSnapshot(env, snapshot);
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (pathname === "/dashboard") return handleDashboard(request, env);
    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

- `_sample_interval` is the Analytics Engine sampling weight column; always multiply doubles by it before summing to get correct weighted averages.
- GitHub's Link header pagination trick (checking `rel="last"`) avoids fetching all pages just to get a count.
- The Worker only samples the first 100 open issues for age calculations — sufficient for trend analysis. For exact distributions, paginate all pages inside the Cron job.
- Store `CF_API_TOKEN` and `GH_TOKEN` as Worker secrets via `wrangler secret put`.

## Anti-patterns

- **Do not query Analytics Engine directly from a user-facing request without a cache layer.** SQL queries can take hundreds of milliseconds; put a Cache API or KV TTL in front.
- **Do not write a data point per issue.** Write aggregate snapshots. Analytics Engine is designed for time-series counters, not row-per-entity records.
- **Do not use `writeDataPoint` inside `fetch` handlers on every request.** Rate-limit writes to scheduled jobs.

## Gotchas

- Analytics Engine datasets must be declared in `wrangler.toml`; the binding name and dataset name are independent strings.
- The `doubles` array positions are fixed at schema definition time (implicitly by your first write). Document the column order in code comments or a migration note.
- GitHub API rate limit for unauthenticated calls is 60/hour. Always pass a token. With a PAT the limit is 5,000/hour.

## Verification

```bash
# Trigger the Cron manually via wrangler
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+*+*+*+*"

# Check dashboard locally
curl "http://localhost:8787/dashboard?days=1"
```

In production, verify data landed by hitting the SQL API:

```bash
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: text/plain" \
  --data "SELECT count() FROM github_issue_metrics LIMIT 1"
```

## Related

- workers-issue-sla-tracker-d1
- workers-github-issue-webhook-router
- workers-issue-auto-assignment-d1

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://docs.github.com/en/rest/issues/issues
