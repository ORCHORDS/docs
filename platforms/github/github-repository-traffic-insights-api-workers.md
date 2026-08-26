# GitHub Repository Traffic Insights API with Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

GitHub's **Traffic** tab in a repository shows views, unique visitors, clones, referring sites,
and popular content paths — but only for the **last 14 days**, and there is no native export or
alerting. You need to:

- Retain historical traffic data beyond GitHub's 14-day rolling window
- Build an org-wide traffic dashboard across dozens of repositories
- Alert when a repository's traffic spikes (viral article, CVE mention, HackerNews front page)
- Feed clone counts into a Cloudflare D1 database for trend reporting

A scheduled Cloudflare Worker polling the GitHub Traffic API solves all of these. Data must
be collected at least every 14 days to avoid gaps; daily polling is recommended.

---

## Context

The GitHub Traffic API endpoints are under `GET /repos/{owner}/{repo}/traffic/`. They require
a token with `repo` scope (PAT) or a GitHub App with `metadata:read` and `administration:read`
permissions. Fine-grained PATs need the **"Repository traffic"** (read) permission explicitly.

Available endpoints and their data windows:

| Endpoint | Granularity | Window |
|----------|------------|--------|
| `/traffic/views` | daily buckets | 14 days |
| `/traffic/clones` | daily buckets | 14 days |
| `/traffic/referrers` | aggregate | last 14 days, top 10 |
| `/traffic/popular/paths` | aggregate | last 14 days, top 10 |

All counts include both unique visitors/cloners and total counts.

---

## D1 Schema

```sql
-- migrations/0001_traffic_tables.sql

CREATE TABLE IF NOT EXISTS repo_views (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  repo        TEXT    NOT NULL,
  date        TEXT    NOT NULL,   -- ISO-8601 date "2026-08-22"
  count       INTEGER NOT NULL,
  uniques     INTEGER NOT NULL,
  captured_at TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE(repo, date)
);

CREATE TABLE IF NOT EXISTS repo_clones (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  repo        TEXT    NOT NULL,
  date        TEXT    NOT NULL,
  count       INTEGER NOT NULL,
  uniques     INTEGER NOT NULL,
  captured_at TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE(repo, date)
);

CREATE TABLE IF NOT EXISTS repo_referrers (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  repo        TEXT    NOT NULL,
  referrer    TEXT    NOT NULL,
  count       INTEGER NOT NULL,
  uniques     INTEGER NOT NULL,
  captured_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS repo_popular_paths (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  repo        TEXT    NOT NULL,
  path        TEXT    NOT NULL,
  title       TEXT,
  count       INTEGER NOT NULL,
  uniques     INTEGER NOT NULL,
  captured_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_views_repo_date  ON repo_views (repo, date);
CREATE INDEX IF NOT EXISTS idx_clones_repo_date ON repo_clones (repo, date);
```

---

## Worker Implementation

```typescript
// src/workers/traffic-collector.ts
export interface Env {
  DB: D1Database;
  GITHUB_PAT: string;       // stored as a Worker secret
  REPOS: string;            // comma-separated "owner/repo" list, Worker variable
}

interface TrafficBucket {
  timestamp: string;        // ISO-8601 e.g. "2026-08-22T00:00:00Z"
  count: number;
  uniques: number;
}

interface TrafficResponse {
  count: number;
  uniques: number;
  views?: TrafficBucket[];
  clones?: TrafficBucket[];
}

interface Referrer {
  referrer: string;
  count: number;
  uniques: number;
}

interface PopularPath {
  path: string;
  title: string;
  count: number;
  uniques: number;
}

async function ghGet<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`https://api.github.com${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "acme-traffic-collector/1.0",
    },
  });
  if (!res.ok) {
    throw new Error(`GitHub API ${path} returned ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

async function collectRepo(repo: string, token: string, db: D1Database): Promise<void> {
  const [viewsData, clonesData, referrers, paths] = await Promise.all([
    ghGet<TrafficResponse>(`/repos/${repo}/traffic/views`, token),
    ghGet<TrafficResponse>(`/repos/${repo}/traffic/clones`, token),
    ghGet<Referrer[]>(`/repos/${repo}/traffic/referrers`, token),
    ghGet<PopularPath[]>(`/repos/${repo}/traffic/popular/paths`, token),
  ]);

  const stmts: D1PreparedStatement[] = [];

  // Upsert daily view buckets
  for (const bucket of viewsData.views ?? []) {
    const date = bucket.timestamp.slice(0, 10); // "2026-08-22"
    stmts.push(
      db
        .prepare(
          `INSERT INTO repo_views (repo, date, count, uniques)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(repo, date) DO UPDATE
             SET count = excluded.count,
                 uniques = excluded.uniques,
                 captured_at = datetime('now')`,
        )
        .bind(repo, date, bucket.count, bucket.uniques),
    );
  }

  // Upsert daily clone buckets
  for (const bucket of viewsData.clones ?? clonesData.clones ?? []) {
    const date = bucket.timestamp.slice(0, 10);
    stmts.push(
      db
        .prepare(
          `INSERT INTO repo_clones (repo, date, count, uniques)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(repo, date) DO UPDATE
             SET count = excluded.count,
                 uniques = excluded.uniques,
                 captured_at = datetime('now')`,
        )
        .bind(repo, date, bucket.count, bucket.uniques),
    );
  }

  // Insert latest referrer snapshot (no de-dup — append for history)
  for (const ref of referrers) {
    stmts.push(
      db
        .prepare(
          `INSERT INTO repo_referrers (repo, referrer, count, uniques)
           VALUES (?, ?, ?, ?)`,
        )
        .bind(repo, ref.referrer, ref.count, ref.uniques),
    );
  }

  // Insert latest popular paths snapshot
  for (const p of paths) {
    stmts.push(
      db
        .prepare(
          `INSERT INTO repo_popular_paths (repo, path, title, count, uniques)
           VALUES (?, ?, ?, ?, ?)`,
        )
        .bind(repo, p.path, p.title, p.count, p.uniques),
    );
  }

  // Batch-write all statements in one round-trip
  await db.batch(stmts);
}

export default {
  // Triggered by a Cron Trigger (see wrangler.toml)
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const repos = env.REPOS.split(",").map((r) => r.trim()).filter(Boolean);

    for (const repo of repos) {
      try {
        await collectRepo(repo, env.GITHUB_PAT, env.DB);
        console.log(`[traffic] collected ${repo}`);
      } catch (err) {
        console.error(`[traffic] failed for ${repo}:`, err);
        // Continue with remaining repos rather than aborting
      }
    }
  },

  // Optional: expose a simple query endpoint
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname, searchParams } = new URL(request.url);

    if (pathname === "/views") {
      const repo = searchParams.get("repo");
      const since = searchParams.get("since") ?? "2020-01-01";
      if (!repo) return new Response("Missing ?repo=", { status: 400 });

      const rows = await env.DB.prepare(
        `SELECT date, count, uniques
         FROM repo_views
         WHERE repo = ? AND date >= ?
         ORDER BY date ASC`,
      )
        .bind(repo, since)
        .all();

      return Response.json(rows.results);
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## `wrangler.toml` Configuration

```toml
name = "traffic-collector"
main = "src/workers/traffic-collector.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding = "DB"
database_name = "traffic-insights"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
REPOS = "acme-corp/api-gateway,acme-corp/frontend,acme-corp/workers-kit"

# Daily at 06:00 UTC — well within the 14-day window
[[triggers]]
crons = ["0 6 * * *"]

# GITHUB_PAT is set as a secret:
# wrangler secret put GITHUB_PAT
```

---

## GitHub Actions: Trigger Manual Backfill

```yaml
# .github/workflows/traffic-backfill.yml
name: Trigger traffic backfill
on:
  workflow_dispatch:
    inputs:
      since:
        description: "Earliest date to backfill (YYYY-MM-DD)"
        required: false
        default: ""

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: Invoke Worker scheduled event via wrangler
        run: |
          npx wrangler@latest dispatch-scheduled-event \
            --name traffic-collector \
            --cron "0 6 * * *"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

---

## Anti-patterns

- **Polling more than once per hour** — the Traffic API caches at the hourly granularity; polling
  more frequently wastes rate-limit budget without new data. Daily polling is optimal.

- **Storing referrers and popular paths as point-in-time upserts** — referrer data is an aggregate
  over 14 days, not a daily breakdown. Upserting overwrites history; appending builds a time-series
  of snapshots (use `captured_at` to distinguish snapshots).

- **Using the default `GITHUB_TOKEN` in Actions to read traffic** — `GITHUB_TOKEN` in a workflow
  does **not** have `administration:read`, so it cannot access traffic endpoints. Use a PAT or
  GitHub App token with the correct scope.

- **Assuming the API returns all 14 days** — recently created repos or repos with zero traffic on
  some days may return fewer buckets. Always upsert rather than assume a fixed array length.

---

## Gotchas

- **Traffic API requires push access** — the authenticated user or app must have **push** (write)
  access to the repository, not just read access. A read-only collaborator cannot call traffic
  endpoints even with `repo` scope.

- **Rate limits** — Traffic endpoints count against the same 5 000 req/hr REST limit as other
  authenticated requests. A 100-repo org using 4 endpoints per repo = 400 requests per daily run,
  well within limits.

- **Forked repositories** — traffic data is not propagated to forks. The fork's own traffic
  is tracked separately and requires access to the fork.

- **`count` vs `uniques`** — `count` is total page views/clones; `uniques` is unique
  visitors/cloners. GitHub's definition of "unique" uses a 24-hour cookie window, not a
  session window.

- **UTC timestamps** — all `timestamp` fields are midnight UTC. A view at 23:00 London time
  on Monday appears in Tuesday's UTC bucket.

---

## Verification

```bash
# Confirm the Worker can reach the API
curl -s \
  -H "Authorization: Bearer $GITHUB_PAT" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/acme-corp/api-gateway/traffic/views" \
  | jq '{count, uniques, days: (.views | length)}'

# After a scheduled run, query D1 to confirm rows exist
wrangler d1 execute traffic-insights \
  --command "SELECT repo, MIN(date) as oldest, MAX(date) as newest, COUNT(*) as days
             FROM repo_views GROUP BY repo"
```

---

## Related

- `github-audit-log-api.md` — org-wide audit events
- `github-graphql-api-patterns.md` — GraphQL API usage patterns
- `github-api-rate-limits.md` — rate limit management
- `github-apps-installation-token-workers-api-client.md` — GitHub App tokens for API access

---

## Sources

- https://docs.github.com/en/rest/metrics/traffic
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#fine-grained-personal-access-tokens
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-events/
- https://developers.cloudflare.com/d1/
