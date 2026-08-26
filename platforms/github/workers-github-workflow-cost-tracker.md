# GitHub Actions Workflow Cost and Duration Tracking with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Engineering leaders have no visibility into which GitHub Actions workflows consume the most compute minutes or incur the most billing cost. GitHub's built-in usage reports are aggregate and monthly; there is no per-workflow, per-team, or per-PR breakdown available via the UI.

You need a Cloudflare Worker that captures every `workflow_run` webhook event, extracts job durations and billable minutes, stores them in D1, exposes a cost-report JSON endpoint, and fires budget-alert comments on PRs when a team's monthly spend exceeds a configured threshold.

---

## Context

- GitHub emits a `workflow_run` event with actions `completed`, `requested`, `in_progress`.
- On `completed`, the payload includes `run_duration_ms` (total), but not per-job billable minutes.
- Billable minutes per OS multiplier (Linux ×1, Windows ×2, macOS ×10) require a separate API call: `GET /repos/{owner}/{repo}/actions/runs/{run_id}/timing`.
- D1 stores the cost data with indexes for per-repo and per-team queries.
- KV stores team-to-repo mappings and budget thresholds.
- The cost-report endpoint is a standard `GET` route on the same Worker.

---

## Solution

### wrangler.toml

```toml
name = "workflow-cost-tracker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "workflow-costs"
database_id = "YOUR_D1_DATABASE_ID"

[[kv_namespaces]]
binding = "CONFIG_KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
GITHUB_WEBHOOK_SECRET = "YOUR_WEBHOOK_SECRET"
```

### D1 migration

```sql
-- migrations/0001_init.sql
CREATE TABLE IF NOT EXISTS workflow_runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  owner           TEXT    NOT NULL,
  repo            TEXT    NOT NULL,
  team            TEXT,
  workflow_name   TEXT    NOT NULL,
  run_id          INTEGER NOT NULL UNIQUE,
  head_branch     TEXT,
  head_sha        TEXT,
  event           TEXT,
  conclusion      TEXT,
  run_started_at  TEXT,
  run_duration_ms INTEGER,
  linux_minutes   INTEGER NOT NULL DEFAULT 0,
  windows_minutes INTEGER NOT NULL DEFAULT 0,
  macos_minutes   INTEGER NOT NULL DEFAULT 0,
  billable_minutes INTEGER NOT NULL DEFAULT 0,
  estimated_cost_usd REAL NOT NULL DEFAULT 0,
  recorded_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wf_repo_date
  ON workflow_runs (owner, repo, run_started_at DESC);

CREATE INDEX IF NOT EXISTS idx_wf_team_date
  ON workflow_runs (team, run_started_at DESC);

CREATE TABLE IF NOT EXISTS budget_alerts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  team        TEXT    NOT NULL,
  month       TEXT    NOT NULL, -- YYYY-MM
  threshold   REAL    NOT NULL,
  alerted_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (team, month)
);
```

### src/types.ts

```typescript
export interface WorkflowRunPayload {
  action: 'completed' | 'requested' | 'in_progress';
  workflow_run: {
    id: number;
    name: string;
    head_branch: string;
    head_sha: string;
    event: string;
    conclusion: string | null;
    run_started_at: string;
    run_duration_ms: number;
    repository: { owner: { login: string }; name: string };
  };
  repository: { owner: { login: string }; name: string };
}

export interface WorkflowTiming {
  billable: {
    UBUNTU?:  { total_ms: number; jobs: number };
    WINDOWS?: { total_ms: number; jobs: number };
    MACOS?:   { total_ms: number; jobs: number };
  };
  run_duration_ms: number;
}

export interface TeamConfig {
  team: string;
  repos: string[];  // repo names belonging to this team
  monthlyBudgetUsd: number;
}

// GitHub Actions pricing per minute (as of 2026)
export const PRICING = {
  UBUNTU:  0.008,  // per minute
  WINDOWS: 0.016,  // per minute (2× Linux)
  MACOS:   0.08,   // per minute (10× Linux)
} as const;
```

### src/github.ts

```typescript
const UA = 'workflow-cost-tracker/1.0';

export async function fetchWorkflowTiming(
  owner: string,
  repo: string,
  runId: number,
  token: string,
): Promise<WorkflowTiming> {
  const resp = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/runs/${runId}/timing`,
    { headers: { Authorization: `Bearer ${token}`, 'User-Agent': UA } },
  );
  if (!resp.ok) throw new Error(`fetchWorkflowTiming ${runId} → ${resp.status}`);
  return resp.json() as Promise<WorkflowTiming>;
}

export async function postPrComment(
  owner: string,
  repo: string,
  prNumber: number,
  body: string,
  token: string,
): Promise<void> {
  await fetch(`https://api.github.com/repos/${owner}/${repo}/issues/${prNumber}/comments`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': UA,
    },
    body: JSON.stringify({ body }),
  });
}

export async function findPrForSha(
  owner: string,
  repo: string,
  sha: string,
  token: string,
): Promise<number | null> {
  const resp = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/commits/${sha}/pulls`,
    { headers: { Authorization: `Bearer ${token}`, 'User-Agent': UA, Accept: 'application/vnd.github+json' } },
  );
  if (!resp.ok) return null;
  const prs: Array<{ number: number; state: string }> = await resp.json();
  const open = prs.find(p => p.state === 'open');
  return open?.number ?? null;
}
```

### src/cost.ts

```typescript
import type { WorkflowTiming } from './types';
import { PRICING } from './types';

export interface CostBreakdown {
  linuxMinutes: number;
  windowsMinutes: number;
  macosMinutes: number;
  totalBillableMinutes: number;
  estimatedCostUsd: number;
}

export function calculateCost(timing: WorkflowTiming): CostBreakdown {
  const linuxMs   = timing.billable.UBUNTU?.total_ms  ?? 0;
  const windowsMs = timing.billable.WINDOWS?.total_ms ?? 0;
  const macosMs   = timing.billable.MACOS?.total_ms   ?? 0;

  // GitHub bills in whole minutes, rounding up per job
  const linuxMinutes   = Math.ceil(linuxMs   / 60_000);
  const windowsMinutes = Math.ceil(windowsMs / 60_000);
  const macosMinutes   = Math.ceil(macosMs   / 60_000);

  const estimatedCostUsd =
    linuxMinutes   * PRICING.UBUNTU +
    windowsMinutes * PRICING.WINDOWS +
    macosMinutes   * PRICING.MACOS;

  return {
    linuxMinutes,
    windowsMinutes,
    macosMinutes,
    totalBillableMinutes: linuxMinutes + windowsMinutes + macosMinutes,
    estimatedCostUsd: Math.round(estimatedCostUsd * 10000) / 10000,
  };
}

export function buildBudgetAlertComment(
  team: string,
  month: string,
  spent: number,
  threshold: number,
): string {
  const pct = Math.round((spent / threshold) * 100);
  return [
    `## GitHub Actions Budget Alert — ${team}`,
    '',
    `Team **${team}** has used **\$${spent.toFixed(2)}** of the **\$${threshold.toFixed(2)}** monthly budget (**${pct}%**) as of ${month}.`,
    '',
    '| Metric | Value |',
    '|--------|-------|',
    `| Month | ${month} |`,
    `| Spent | \$${spent.toFixed(2)} |`,
    `| Budget | \$${threshold.toFixed(2)} |`,
    `| Used | ${pct}% |`,
    '',
    '> Review and optimize workflows that consume the most minutes. Run the cost report endpoint for a per-workflow breakdown.',
  ].join('\n');
}
```

### src/index.ts

```typescript
import { fetchWorkflowTiming, postPrComment, findPrForSha } from './github';
import { calculateCost, buildBudgetAlertComment } from './cost';
import { DEFAULT_CONFIG, type WorkflowRunPayload, type TeamConfig } from './types';

export interface Env {
  DB: D1Database;
  CONFIG_KV: KVNamespace;
  GITHUB_TOKEN: string;
  GITHUB_WEBHOOK_SECRET: string;
}

async function verifySignature(req: Request, secret: string, body: string): Promise<boolean> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const buf = await crypto.subtle.sign('HMAC', key, enc.encode(body));
  const hex = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
  return (req.headers.get('x-hub-signature-256') ?? '') === `sha256=${hex}`;
}

async function getTeamForRepo(kv: KVNamespace, owner: string, repoName: string): Promise<string | null> {
  const raw = await kv.get(`team-map:${owner}`);
  if (!raw) return null;
  const teams: TeamConfig[] = JSON.parse(raw);
  return teams.find(t => t.repos.includes(repoName))?.team ?? null;
}

async function getMonthlySpend(db: D1Database, team: string, month: string): Promise<number> {
  const result = await db
    .prepare(`SELECT COALESCE(SUM(estimated_cost_usd), 0) AS total FROM workflow_runs WHERE team = ? AND strftime('%Y-%m', run_started_at) = ?`)
    .bind(team, month)
    .first<{ total: number }>();
  return result?.total ?? 0;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Cost report endpoint
    if (request.method === 'GET' && url.pathname === '/report') {
      const repo  = url.searchParams.get('repo') ?? '';
      const team  = url.searchParams.get('team') ?? '';
      const month = url.searchParams.get('month') ?? new Date().toISOString().slice(0, 7);

      const rows = await env.DB.prepare(
        `SELECT workflow_name, COUNT(*) AS runs,
                SUM(billable_minutes) AS total_minutes,
                SUM(estimated_cost_usd) AS total_cost,
                AVG(run_duration_ms) / 60000.0 AS avg_duration_min
         FROM workflow_runs
         WHERE (? = '' OR repo = ?)
           AND (? = '' OR team = ?)
           AND strftime('%Y-%m', run_started_at) = ?
         GROUP BY workflow_name
         ORDER BY total_cost DESC
         LIMIT 50`,
      ).bind(repo, repo, team, team, month).all();

      return new Response(JSON.stringify(rows.results), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Webhook handler
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.text();
    if (!(await verifySignature(request, env.GITHUB_WEBHOOK_SECRET, body)))
      return new Response('Unauthorized', { status: 401 });

    if (request.headers.get('x-github-event') !== 'workflow_run')
      return new Response('Ignored', { status: 200 });

    const payload: WorkflowRunPayload = JSON.parse(body);
    if (payload.action !== 'completed') return new Response('Not completed', { status: 200 });

    const { workflow_run: run, repository: repo } = payload;
    const owner    = repo.owner.login;
    const repoName = repo.name;

    // Fetch billable timing
    const timing = await fetchWorkflowTiming(owner, repoName, run.id, env.GITHUB_TOKEN);
    const cost   = calculateCost(timing);
    const team   = await getTeamForRepo(env.CONFIG_KV, owner, repoName);
    const month  = run.run_started_at.slice(0, 7); // YYYY-MM

    // Store in D1
    await env.DB.prepare(
      `INSERT OR IGNORE INTO workflow_runs
         (owner, repo, team, workflow_name, run_id, head_branch, head_sha, event, conclusion,
          run_started_at, run_duration_ms, linux_minutes, windows_minutes, macos_minutes,
          billable_minutes, estimated_cost_usd)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        owner, repoName, team, run.name, run.id, run.head_branch, run.head_sha,
        run.event, run.conclusion, run.run_started_at, run.run_duration_ms,
        cost.linuxMinutes, cost.windowsMinutes, cost.macosMinutes,
        cost.totalBillableMinutes, cost.estimatedCostUsd,
      )
      .run();

    // Budget alert check
    if (team) {
      const teamRaw = await env.CONFIG_KV.get(`team-map:${owner}`);
      const teams: TeamConfig[] = teamRaw ? JSON.parse(teamRaw) : [];
      const teamConfig = teams.find(t => t.team === team);
      if (teamConfig) {
        const spent = await getMonthlySpend(env.DB, team, month);
        if (spent >= teamConfig.monthlyBudgetUsd) {
          // Only alert once per month per team
          const alreadyAlerted = await env.DB
            .prepare('SELECT id FROM budget_alerts WHERE team = ? AND month = ?')
            .bind(team, month)
            .first();
          if (!alreadyAlerted) {
            await env.DB
              .prepare('INSERT OR IGNORE INTO budget_alerts (team, month, threshold) VALUES (?, ?, ?)')
              .bind(team, month, teamConfig.monthlyBudgetUsd)
              .run();

            // Post comment to the PR associated with this run's head SHA
            const prNumber = await findPrForSha(owner, repoName, run.head_sha, env.GITHUB_TOKEN);
            if (prNumber) {
              const comment = buildBudgetAlertComment(team, month, spent, teamConfig.monthlyBudgetUsd);
              await postPrComment(owner, repoName, prNumber, comment, env.GITHUB_TOKEN);
            }
          }
        }
      }
    }

    return new Response(JSON.stringify({ run_id: run.id, ...cost }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Implementation Details

- **Billing multipliers**: GitHub multiplies raw job minutes by OS tier. The `PRICING` constants reflect current GitHub public pricing. Review pricing at https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions and update the constants at the start of each billing cycle.
- **INSERT OR IGNORE**: the `run_id UNIQUE` constraint makes the insert idempotent. GitHub retries `workflow_run` webhooks on 5xx; duplicate events are silently dropped.
- **Monthly spend aggregation**: `strftime('%Y-%m', run_started_at)` partitions rows by calendar month in D1 (SQLite). This is UTC-based; adjust if your org's billing cycle is non-UTC.
- **Team mapping in KV**: stored at key `team-map:{owner}` as a JSON array of `TeamConfig`. A single KV key per org avoids key-per-repo proliferation and makes team re-orgs a single KV put.
- **`/report` endpoint**: protected only by network policy (e.g., Cloudflare Access rule) in this implementation. Add `Authorization` header validation if exposing publicly.

---

## Anti-patterns

- **Do not use `run_duration_ms` from the payload for billing**: it is wall-clock time. Billable minutes come from the `/timing` API which applies the OS multiplier and job-level ceiling rounding.
- **Do not sum billable minutes across OS tiers without multiplier**: Linux, Windows, and macOS minutes are not equivalent for cost purposes. Always store them in separate columns.
- **Do not alert on every run that exceeds budget**: use the `budget_alerts` table to deduplicate; one alert per team per month is sufficient.
- **Do not store the full timing API response in D1**: it is a large JSON blob. Extract only the per-OS totals and discard the per-job breakdown unless you need job-level reporting.

---

## Gotchas

- The `/timing` API returns `total_ms` as 0 for workflows that ran on self-hosted runners. Self-hosted runner minutes are not billed by GitHub; exclude them or track them separately with a custom cost-per-minute config.
- `workflow_run` `completed` events are emitted after all jobs finish. If a workflow is cancelled mid-run, the `conclusion` is `cancelled` and partial billable minutes still accrue — they will be in the `/timing` response.
- D1 has a 10MB row limit and a 100,000-row write limit per day on the free plan. A high-volume org with 1,000 workflow runs/day will exhaust the free quota. Use the paid plan or archive rows older than 90 days with a scheduled Worker.
- The `findPrForSha` call uses `GET /repos/{owner}/{repo}/commits/{sha}/pulls`, which requires the `repo` scope. On GitHub Apps, the `pull_requests: read` permission is needed.

---

## Verification

```bash
# Run D1 migration
npx wrangler d1 execute workflow-costs --file migrations/0001_init.sql

# Deploy
npx wrangler deploy

# Set team map in KV
npx wrangler kv key put 'team-map:orchords' \
  '[{"team":"platform","repos":["api","infra"],"monthlyBudgetUsd":50},{"team":"frontend","repos":["app"],"monthlyBudgetUsd":20}]' \
  --binding CONFIG_KV

# Fetch cost report for the current month
curl 'https://workflow-cost-tracker.YOUR_SUBDOMAIN.workers.dev/report?team=platform&month=2026-08'

# Query D1 directly for top-cost workflows
npx wrangler d1 execute workflow-costs \
  --command "SELECT workflow_name, SUM(estimated_cost_usd) AS total FROM workflow_runs WHERE team='platform' GROUP BY workflow_name ORDER BY total DESC LIMIT 10;"
```

---

## Related

- `documentation/categories/github/workers-github-pr-size-labeler.md`
- `documentation/categories/github/workers-github-repo-archival-bot.md`
- GitHub Actions billing: https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/

---

## Sources

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://docs.github.com/en/rest/actions/workflow-runs
- https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_run
