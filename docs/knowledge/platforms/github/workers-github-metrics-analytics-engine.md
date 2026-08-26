# GitHub Repository Metrics Collection via Workers and Analytics Engine

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Engineering managers want continuous visibility into PR cycle time, review turnaround, and merge rate across dozens of repositories — without deploying a separate metrics service. You need a Cloudflare Workers scheduled job that pulls data from the GitHub API, writes data points to Cloudflare Analytics Engine, and exposes a SQL query endpoint for team dashboards.

## Context

Cloudflare Analytics Engine is a time-series store built into Workers. Each data point is an `AEDataset.writeDataPoint` call with:
- **indexes** — low-cardinality grouping strings (org, repo, team).
- **blobs** — arbitrary string labels per data point.
- **doubles** — up to 20 numeric values.

The Analytics Engine SQL API (`https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`) accepts Cloudflare SQL dialect queries for aggregation and export.

Scheduled Workers trigger via cron. GitHub API responses are paginated; the Worker must exhaust all pages before computing metrics.

## Solution

### Wrangler configuration

```toml
# wrangler.toml
name = "github-metrics"
main = "src/index.ts"
compatibility_date = "2024-11-01"

[triggers]
crons = ["0 * * * *"]  # Every hour

[[analytics_engine_datasets]]
binding = "METRICS"
dataset = "github_metrics"
```

### Types

```typescript
// src/types.ts
export interface Env {
  METRICS: AnalyticsEngineDataset;
  GITHUB_TOKEN: string;          // Fine-grained PAT or installation token
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;          // Token with Analytics Engine read permission
  ORGS: string;                  // Comma-separated list of orgs to monitor
}

export interface PullRequest {
  number: number;
  title: string;
  state: "open" | "closed";
  created_at: string;
  merged_at: string | null;
  closed_at: string | null;
  user: { login: string };
  base: { repo: { name: string; owner: { login: string } } };
  requested_reviewers: Array<{ login: string }>;
  labels: Array<{ name: string }>;
  draft: boolean;
}

export interface Review {
  submitted_at: string;
  state: string;
  user: { login: string };
}
```

### GitHub API pagination helper

```typescript
// src/github.ts
const GH = "https://api.github.com";

export async function paginatedFetch<T>(
  token: string,
  url: string
): Promise<T[]> {
  const results: T[] = [];
  let next: string | null = url;

  while (next) {
    const resp = await fetch(next, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "orchords-metrics/1.0",
      },
    });

    if (resp.status === 422 || resp.status === 404) break;
    if (!resp.ok) throw new Error(`GitHub API error: ${resp.status} ${next}`);

    const page = (await resp.json()) as T[];
    results.push(...page);

    const link = resp.headers.get("Link") ?? "";
    const match = link.match(/<([^>]+)>;\s*rel="next"/);
    next = match ? match[1] : null;
  }

  return results;
}

export async function fetchClosedPRs(
  token: string,
  owner: string,
  repo: string,
  since: string // ISO-8601
): Promise<PullRequest[]> {
  const url = `${GH}/repos/${owner}/${repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100`;
  const all = await paginatedFetch<PullRequest>(token, url);
  return all.filter(
    (pr) => pr.merged_at !== null && pr.merged_at >= since
  );
}

export async function fetchPRReviews(
  token: string,
  owner: string,
  repo: string,
  prNumber: number
): Promise<Review[]> {
  return paginatedFetch<Review>(
    token,
    `${GH}/repos/${owner}/${repo}/pulls/${prNumber}/reviews`
  );
}
```

### Metric computation

```typescript
// src/metrics.ts
import { fetchClosedPRs, fetchPRReviews } from "./github";
import type { Env, PullRequest, Review } from "./types";

function hoursElapsed(from: string, to: string): number {
  return (new Date(to).getTime() - new Date(from).getTime()) / 3_600_000;
}

function firstReviewTime(pr: PullRequest, reviews: Review[]): number | null {
  const submitted = reviews
    .map((r) => r.submitted_at)
    .filter(Boolean)
    .sort();
  if (!submitted.length) return null;
  return hoursElapsed(pr.created_at, submitted[0]);
}

export async function collectRepoMetrics(
  env: Env,
  owner: string,
  repo: string
): Promise<void> {
  const since = new Date(Date.now() - 7 * 24 * 3_600_000).toISOString(); // last 7 days
  const prs = await fetchClosedPRs(env.GITHUB_TOKEN, owner, repo, since);

  for (const pr of prs) {
    if (!pr.merged_at) continue;
    const reviews = await fetchPRReviews(env.GITHUB_TOKEN, owner, repo, pr.number);

    const cycleTime = hoursElapsed(pr.created_at, pr.merged_at);
    const reviewTime = firstReviewTime(pr, reviews) ?? -1;
    const reviewCount = reviews.filter((r) =>
      ["APPROVED", "CHANGES_REQUESTED", "COMMENTED"].includes(r.state)
    ).length;
    const isHotfix = pr.labels.some((l) => l.name === "hotfix");

    env.METRICS.writeDataPoint({
      indexes: [owner, repo, pr.user.login],
      blobs: [
        pr.number.toString(),
        pr.title.slice(0, 64),
        isHotfix ? "hotfix" : "standard",
      ],
      doubles: [
        cycleTime,     // double[0]: cycle time hours
        reviewTime,    // double[1]: first review time hours (-1 = no review)
        reviewCount,   // double[2]: total review submissions
        1,             // double[3]: merged PR count (for SUM aggregation)
      ],
    });
  }
}
```

### Scheduled handler

```typescript
// src/index.ts
import { collectRepoMetrics } from "./metrics";
import type { Env } from "./types";

const GH = "https://api.github.com";

async function listOrgRepos(token: string, org: string): Promise<string[]> {
  const resp = await fetch(
    `${GH}/orgs/${org}/repos?type=all&per_page=100`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "orchords-metrics/1.0",
      },
    }
  );
  const repos = (await resp.json()) as Array<{ name: string; archived: boolean }>;
  return repos.filter((r) => !r.archived).map((r) => r.name);
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const orgs = env.ORGS.split(",").map((o) => o.trim());
    const tasks: Promise<void>[] = [];

    for (const org of orgs) {
      const repos = await listOrgRepos(env.GITHUB_TOKEN, org);
      for (const repo of repos) {
        tasks.push(collectRepoMetrics(env, org, repo));
      }
    }

    ctx.waitUntil(Promise.allSettled(tasks));
  },

  // Dashboard query endpoint
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const org = url.searchParams.get("org") ?? "";
    const repo = url.searchParams.get("repo") ?? "";
    const days = parseInt(url.searchParams.get("days") ?? "30", 10);

    const sql = `
      SELECT
        blob1 AS repo,
        AVG(double1) AS avg_cycle_time_hours,
        AVG(double2) AS avg_first_review_hours,
        SUM(double4) AS merged_prs,
        toStartOfInterval(timestamp, INTERVAL '1' DAY) AS day
      FROM github_metrics
      WHERE
        index1 = '${org}'
        ${repo ? `AND index2 = '${repo}'` : ""}
        AND timestamp > now() - INTERVAL '${days}' DAY
      GROUP BY day, blob1
      ORDER BY day DESC
    `;

    const resp = await fetch(
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

    const data = await resp.json();
    return new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

### Team dashboard — top-level aggregation

```typescript
// src/dashboard.ts
export async function getTeamSummary(
  accountId: string,
  cfToken: string,
  org: string
): Promise<Response> {
  const sql = `
    SELECT
      index2 AS repo,
      AVG(double1) AS avg_cycle_time_h,
      AVG(IF(double2 >= 0, double2, NULL)) AS avg_first_review_h,
      SUM(double4) AS total_merged,
      AVG(double3) AS avg_reviews_per_pr
    FROM github_metrics
    WHERE index1 = '${org}'
      AND timestamp > now() - INTERVAL '7' DAY
    GROUP BY repo
    ORDER BY total_merged DESC
    LIMIT 20
  `;

  return fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${cfToken}`, "Content-Type": "text/plain" },
      body: sql,
    }
  );
}
```

## Implementation Details

- `writeDataPoint` is synchronous and non-blocking — it queues the point locally and flushes automatically. There is no acknowledgement; points may be dropped if the Worker is evicted immediately after writing.
- Analytics Engine imposes a **25 doubles, 25 blobs, 5 indexes** limit per data point and a **~20 write/s** rate per Worker invocation.
- The SQL API returns results in JSON with a `data` array. Timestamps are UTC strings.
- `AVG(IF(double2 >= 0, double2, NULL))` excludes the sentinel `-1` used for unreviewed PRs.

## Anti-patterns

- **Running one API call per PR sequentially** — Fetching reviews per PR in a tight loop hits rate limits. Batch with `Promise.allSettled` and add exponential back-off on `429`.
- **Using personal access tokens for org-wide metrics** — Personal tokens expose all repos the user can see. Use a GitHub App installation token scoped to the specific org (see `workers-github-app-installation-auth.md`).
- **Hardcoding the 7-day window** — Different teams need different windows. Make `since` configurable via a KV key so it can be adjusted without redeployment.

## Gotchas

- Analytics Engine data is available for query after a propagation delay of ~1 minute. Do not query immediately after writing in tests.
- The GitHub API rate limit for authenticated requests is 5,000/hour. An org with 100 repos and 50 closed PRs per repo in the window requires 100 + 100*50 = 5,100 API calls — above the limit. Implement request throttling with `setTimeout`-based queuing or spread collection across multiple cron firings.
- `toStartOfInterval` in Cloudflare SQL requires the `INTERVAL` keyword — it does not accept plain integers.

## Verification

```bash
# Trigger the scheduled worker immediately for testing
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+*+*+*+*"

# Query Analytics Engine via REST
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: text/plain" \
  --data "SELECT COUNT() FROM github_metrics WHERE timestamp > now() - INTERVAL '1' HOUR"
```

## Related

- `documentation/docs/policies/github/workers-github-app-installation-auth.md`
- `documentation/docs/policies/github/workers-github-release-automation.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://docs.github.com/en/rest/pulls/pulls#list-pull-requests
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
