# Detecting GitHub Issue SLA Breaches with a Cron Worker

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your engineering team commits to response SLAs for GitHub issues by label priority (P1 = 4 h, P2 = 24 h, P3 = 72 h), but breaches go unnoticed until a customer escalates. You need a scheduled Cloudflare Worker that polls the GitHub API, compares each open issue's age against the appropriate threshold, persists new breaches to D1, and fires a Slack alert with the issue link.

---

## Context
The GitHub REST API `/repos/{owner}/{repo}/issues` endpoint returns open issues with `labels` and `created_at`. A Cron Worker running every 30 minutes iterates over all open issues, determines the SLA tier from the label list, and checks whether `now - created_at > threshold`. Breaches are deduplicated in a D1 `sla_breaches` table keyed on `(repo, issue_number)` so the same issue is not re-alerted on every Cron run. Resolved issues (state = `closed`) are marked `resolved` in D1 on the next scan. Slack alerts are batched per run to avoid flooding the channel.

---

## Section 1 — D1 Schema & wrangler.toml

```sql
CREATE TABLE IF NOT EXISTS sla_breaches (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  repo         TEXT    NOT NULL,           -- owner/repo
  issue_number INTEGER NOT NULL,
  issue_title  TEXT    NOT NULL,
  issue_url    TEXT    NOT NULL,
  label_tier   TEXT    NOT NULL,           -- P1 | P2 | P3
  created_at   TEXT    NOT NULL,           -- issue created_at from GitHub
  breached_at  TEXT    NOT NULL,           -- when we first detected the breach
  alerted_at   TEXT,                       -- when Slack alert was sent
  resolved_at  TEXT,
  UNIQUE (repo, issue_number)
);

CREATE INDEX IF NOT EXISTS idx_sla_repo ON sla_breaches (repo);
CREATE INDEX IF NOT EXISTS idx_sla_resolved ON sla_breaches (resolved_at);
```

```toml
# wrangler.toml
name = "sla-breach-detector"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[triggers]
crons = ["*/30 * * * *"]

[[d1_databases]]
binding    = "DB"
database_name = "sla-breach-db"
database_id   = "<your-d1-id>"

[vars]
GITHUB_REPO    = "myorg/myrepo"
SLACK_WEBHOOK  = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

---

## Section 2 — SLA detection Worker

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  GITHUB_TOKEN: string;   // Worker secret
  SLACK_WEBHOOK: string;
  GITHUB_REPO: string;    // e.g. "myorg/myrepo"
}

const SLA_HOURS: Record<string, number> = {
  P1: 4,
  P2: 24,
  P3: 72,
};

interface GitHubIssue {
  number: number;
  title: string;
  html_url: string;
  state: string;
  created_at: string;
  labels: Array<{ name: string }>;
}

export default {
  async fetch(_req: Request, _env: Env): Promise<Response> {
    return new Response('SLA breach detector — triggered via Cron', { status: 200 });
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(detectBreaches(env));
  },
};

async function fetchOpenIssues(repo: string, token: string): Promise<GitHubIssue[]> {
  const issues: GitHubIssue[] = [];
  let page = 1;

  while (true) {
    const url = `https://api.github.com/repos/${repo}/issues?state=open&per_page=100&page=${page}`;
    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'sla-breach-detector/1.0',
      },
    });
    if (!res.ok) throw new Error(`GitHub API error: ${res.status}`);
    const batch: GitHubIssue[] = await res.json();
    if (!batch.length) break;
    // GitHub issues endpoint returns PRs too — filter them out
    issues.push(...batch.filter((i) => !i.html_url.includes('/pull/')));
    if (batch.length < 100) break;
    page++;
  }
  return issues;
}

function getTier(labels: Array<{ name: string }>): string | null {
  for (const tier of ['P1', 'P2', 'P3']) {
    if (labels.some((l) => l.name.toUpperCase() === tier)) return tier;
  }
  return null;
}

async function detectBreaches(env: Env): Promise<void> {
  const issues = await fetchOpenIssues(env.GITHUB_REPO, env.GITHUB_TOKEN);
  const now = Date.now();
  const newBreaches: GitHubIssue[] = [];

  for (const issue of issues) {
    const tier = getTier(issue.labels);
    if (!tier) continue;

    const ageMs = now - new Date(issue.created_at).getTime();
    const thresholdMs = SLA_HOURS[tier] * 60 * 60 * 1000;
    if (ageMs <= thresholdMs) continue;

    // Upsert — ignore if already recorded
    const result = await env.DB.prepare(
      `INSERT OR IGNORE INTO sla_breaches
         (repo, issue_number, issue_title, issue_url, label_tier, created_at, breached_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        env.GITHUB_REPO,
        issue.number,
        issue.title,
        issue.html_url,
        tier,
        issue.created_at,
        new Date(now).toISOString()
      )
      .run();

    // meta.changes > 0 means it was a new insert (not a duplicate)
    if (result.meta.changes > 0) {
      newBreaches.push(issue);
    }
  }

  // Mark resolved issues
  const openNumbers = issues.map((i) => i.number);
  if (openNumbers.length > 0) {
    // Only mark resolved those NOT in the current open set
    await env.DB.prepare(
      `UPDATE sla_breaches
       SET resolved_at = datetime('now')
       WHERE repo = ? AND resolved_at IS NULL
         AND issue_number NOT IN (${openNumbers.map(() => '?').join(',')})`
    )
      .bind(env.GITHUB_REPO, ...openNumbers)
      .run();
  }

  if (newBreaches.length > 0) {
    await sendSlackBatch(env.SLACK_WEBHOOK, newBreaches, env.GITHUB_REPO);
    // Record alerted_at
    const ts = new Date().toISOString();
    for (const issue of newBreaches) {
      await env.DB.prepare(
        `UPDATE sla_breaches SET alerted_at = ? WHERE repo = ? AND issue_number = ?`
      ).bind(ts, env.GITHUB_REPO, issue.number).run();
    }
  }
}
```

---

## Section 3 — Slack batch-alert handler

```typescript
async function sendSlackBatch(
  webhook: string,
  issues: GitHubIssue[],
  repo: string
): Promise<void> {
  const lines = issues.map((i) => {
    const tier = getTier(i.labels) ?? 'P?';
    const slaH = SLA_HOURS[tier] ?? '?';
    return `• *[${tier}]* <${i.html_url}|#${i.number}: ${i.title}> — SLA: ${slaH}h`;
  });

  const body = {
    text: `*SLA Breach Alert* — ${issues.length} issue(s) in \`${repo}\``,
    blocks: [
      {
        type: 'header',
        text: { type: 'plain_text', text: `SLA Breach: ${issues.length} issue(s) overdue` },
      },
      {
        type: 'section',
        text: { type: 'mrkdwn', text: lines.join('\n') },
      },
      {
        type: 'context',
        elements: [{ type: 'mrkdwn', text: `Repository: \`${repo}\` | Detected at <!date^${Math.floor(Date.now() / 1000)}^{date_short_pretty} {time}|now>` }],
      },
    ],
  };

  const res = await fetch(webhook, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    console.error(`Slack webhook failed: ${res.status} ${await res.text()}`);
  }
}
```

---

## Anti-patterns
- **Alerting every Cron run for the same breach** — use `INSERT OR IGNORE` + `alerted_at` column to deduplicate.
- **Fetching only page 1** — paginate until `batch.length < 100`; repos with many open issues will silently miss breaches.
- **Including PRs in the issue scan** — filter by checking `html_url` contains `/issues/` not `/pull/`.
- **Hard-coding SLA thresholds in Slack messages only** — keep them in a single `SLA_HOURS` map shared across detection and messaging.

---

## Gotchas
- GitHub secondary rate limits apply to API calls; a Cron every 30 min for a repo with 100+ issues pages will generate ~2 API calls — well within limits.
- `INSERT OR IGNORE` requires a `UNIQUE` constraint on `(repo, issue_number)` — confirm the constraint exists before deploying.
- GitHub returns issues and PRs from the same endpoint; PRs have a `pull_request` key in the JSON — filter defensively on `html_url` path.
- The `X-GitHub-Api-Version` header is required for the fine-grained PAT token flow.

---

## Verification
```bash
# Deploy
npx wrangler deploy

# Set secrets
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put SLACK_WEBHOOK  # if not in vars

# Test the Cron handler locally
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*/30+*+*+*+*"

# Inspect D1 for recorded breaches
npx wrangler d1 execute sla-breach-db \
  --command "SELECT repo, issue_number, label_tier, breached_at, alerted_at FROM sla_breaches ORDER BY breached_at DESC LIMIT 10;"
```

---

## Related
- `workers-error-budget-tracking-analytics-engine.md`
- `on-call-rotation-workers-pagerduty-slack.md`

---

## Sources
- GitHub REST API — Issues — https://docs.github.com/en/rest/issues/issues
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Slack Block Kit reference — https://api.slack.com/block-kit
