# Inactive Repository Archival Automation with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Organizations accumulate dozens or hundreds of stale repositories over time. GitHub's default interface provides no automated archival. Manual audits happen quarterly at best, leaving abandoned repos as security and maintenance risks.

You need a scheduled Cloudflare Worker that scans all org repos weekly, identifies those that have been inactive beyond a configurable threshold, opens a warning issue #<number> days before archival, and finally archives the repo — unless it appears in a KV exclusion list.

---

## Context

- The GitHub Repos API (`GET /orgs/{org}/repos`) supports pagination and returns `pushed_at` as the last push timestamp.
- Archiving uses `PATCH /repos/{owner}/{repo}` with `{ "archived": true }`.
- A warning issue is opened via `POST /repos/{owner}/{repo}/issues`.
- Workers Cron Triggers fire the scan on a schedule.
- KV stores: the exclusion list (`exclude:{owner}/{repo}` keys), the warning-sent log (`warned:{owner}/{repo}`), and global config (thresholds).
- The bot requires a GitHub App or PAT with `repo` and `admin:org` scopes.

---

## Solution

### wrangler.toml

```toml
name = "repo-archival-bot"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[triggers]
crons = ["0 9 * * 1"]  # Every Monday at 09:00 UTC

[[kv_namespaces]]
binding = "STATE_KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
GITHUB_ORG = "orchords"
```

### src/types.ts

```typescript
export interface ArchivalConfig {
  inactiveDaysThreshold: number;   // default: 365
  warningDaysBeforeArchival: number; // default: 14
  dryRun: boolean;                  // if true, log actions but do not call GitHub API
}

export const DEFAULT_CONFIG: ArchivalConfig = {
  inactiveDaysThreshold: 365,
  warningDaysBeforeArchival: 14,
  dryRun: false,
};

export interface GitHubRepo {
  id: number;
  name: string;
  full_name: string;
  archived: boolean;
  disabled: boolean;
  pushed_at: string | null;  // ISO 8601
  fork: boolean;
  private: boolean;
  html_url: string;
  topics: string[];
}

export interface RepoDecision {
  repo: string;
  action: 'skip' | 'warn' | 'archive' | 'excluded' | 'already-warned';
  reason: string;
  daysInactive: number;
}
```

### src/github.ts

```typescript
const UA = 'repo-archival-bot/1.0';

export async function listOrgRepos(
  org: string,
  token: string,
): Promise<GitHubRepo[]> {
  const repos: GitHubRepo[] = [];
  let page = 1;
  while (true) {
    const resp = await fetch(
      `https://api.github.com/orgs/${org}/repos?type=all&per_page=100&page=${page}`,
      { headers: { Authorization: `Bearer ${token}`, 'User-Agent': UA } },
    );
    if (!resp.ok) throw new Error(`listOrgRepos page ${page} → ${resp.status}`);
    const batch: GitHubRepo[] = await resp.json();
    if (batch.length === 0) break;
    repos.push(...batch);
    page++;
  }
  return repos;
}

export async function openWarningIssue(
  owner: string,
  repo: string,
  daysInactive: number,
  archivalDate: string,
  token: string,
): Promise<number> {
  const body = [
    `## Repository Inactivity Warning`,
    '',
    `This repository has been inactive for **${daysInactive} days** and is scheduled for archival on **${archivalDate}**.`,
    '',
    '### What does archival mean?',
    '- The repository becomes read-only.',
    '- No new issues, PRs, or commits can be created.',
    '- The repository remains publicly visible (or privately accessible).',
    '- Archival can be reversed by an org admin at any time.',
    '',
    '### To prevent archival',
    '1. Push a commit, open an issue, or merge a PR to this repository.',
    '2. Or ask an org admin to add this repo to the exclusion list.',
    '',
    `> Automated by example.com repo-archival-bot. Last push detected more than ${daysInactive} days ago.`,
  ].join('\n');

  const resp = await fetch(`https://api.github.com/repos/${owner}/${repo}/issues`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': UA,
    },
    body: JSON.stringify({
      title: `[Archival Notice] This repository will be archived on ${archivalDate}`,
      body,
      labels: ['archival-notice'],
    }),
  });
  const issue: { number: number } = await resp.json();
  return issue.number;
}

export async function archiveRepo(
  owner: string,
  repo: string,
  token: string,
): Promise<void> {
  const resp = await fetch(`https://api.github.com/repos/${owner}/${repo}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': UA,
    },
    body: JSON.stringify({ archived: true }),
  });
  if (!resp.ok) throw new Error(`archiveRepo ${owner}/${repo} → ${resp.status}`);
}
```

### src/scanner.ts

```typescript
import type { GitHubRepo, ArchivalConfig, RepoDecision } from './types';

export function daysSince(dateStr: string | null): number {
  if (!dateStr) return Infinity;
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24));
}

export function addDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().split('T')[0];
}

export function shouldSkip(repo: GitHubRepo): { skip: boolean; reason: string } {
  if (repo.archived)   return { skip: true, reason: 'already archived' };
  if (repo.disabled)   return { skip: true, reason: 'disabled' };
  if (repo.fork)       return { skip: true, reason: 'fork — skip by default' };
  if (repo.topics.includes('no-archive')) return { skip: true, reason: 'has no-archive topic' };
  return { skip: false, reason: '' };
}

export async function classifyRepo(
  repo: GitHubRepo,
  config: ArchivalConfig,
  kv: KVNamespace,
  owner: string,
): Promise<RepoDecision> {
  const { skip, reason } = shouldSkip(repo);
  if (skip) return { repo: repo.name, action: 'skip', reason, daysInactive: 0 };

  // Check exclusion list
  const excluded = await kv.get(`exclude:${owner}/${repo.name}`);
  if (excluded !== null) {
    return { repo: repo.name, action: 'excluded', reason: excluded || 'in exclusion list', daysInactive: 0 };
  }

  const daysInactive = daysSince(repo.pushed_at);
  if (daysInactive < config.inactiveDaysThreshold) {
    return { repo: repo.name, action: 'skip', reason: `only ${daysInactive} days inactive`, daysInactive };
  }

  // Check if warning was already sent
  const warnedAt = await kv.get(`warned:${owner}/${repo.name}`);
  if (warnedAt === null) {
    return { repo: repo.name, action: 'warn', reason: 'threshold exceeded, warning not yet sent', daysInactive };
  }

  const warnedDaysAgo = daysSince(warnedAt);
  if (warnedDaysAgo >= config.warningDaysBeforeArchival) {
    return { repo: repo.name, action: 'archive', reason: `warned ${warnedDaysAgo} days ago, grace period elapsed`, daysInactive };
  }

  return {
    repo: repo.name,
    action: 'already-warned',
    reason: `warning sent ${warnedDaysAgo} days ago, ${config.warningDaysBeforeArchival - warnedDaysAgo} days until archival`,
    daysInactive,
  };
}
```

### src/index.ts

```typescript
import { listOrgRepos, openWarningIssue, archiveRepo } from './github';
import { classifyRepo, addDays } from './scanner';
import { DEFAULT_CONFIG, type ArchivalConfig } from './types';

export interface Env {
  STATE_KV: KVNamespace;
  GITHUB_TOKEN: string;
  GITHUB_ORG: string;
}

export default {
  // Webhook handler (manual trigger / health check)
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'POST' && new URL(request.url).pathname === '/scan') {
      await runScan(env);
      return new Response('Scan complete', { status: 200 });
    }
    return new Response('repo-archival-bot running', { status: 200 });
  },

  // Scheduled cron trigger
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await runScan(env);
  },
};

async function runScan(env: Env): Promise<void> {
  const configRaw = await env.STATE_KV.get('config:global');
  const config: ArchivalConfig = configRaw ? JSON.parse(configRaw) : DEFAULT_CONFIG;
  const org = env.GITHUB_ORG;

  const repos = await listOrgRepos(org, env.GITHUB_TOKEN);
  const results: Array<{ repo: string; action: string; reason: string }> = [];

  // Process in batches of 5 to avoid rate-limit burst
  for (let i = 0; i < repos.length; i += 5) {
    const batch = repos.slice(i, i + 5);
    await Promise.all(
      batch.map(async repo => {
        const decision = await classifyRepo(repo, config, env.STATE_KV, org);
        results.push({ repo: decision.repo, action: decision.action, reason: decision.reason });

        if (config.dryRun) return; // log only

        if (decision.action === 'warn') {
          const archivalDate = addDays(config.warningDaysBeforeArchival);
          await openWarningIssue(org, repo.name, decision.daysInactive, archivalDate, env.GITHUB_TOKEN);
          await env.STATE_KV.put(`warned:${org}/${repo.name}`, new Date().toISOString(), {
            expirationTtl: 60 * 60 * 24 * 60, // auto-expire after 60 days in case repo becomes active
          });
        }

        if (decision.action === 'archive') {
          await archiveRepo(org, repo.name, env.GITHUB_TOKEN);
          await env.STATE_KV.delete(`warned:${org}/${repo.name}`);
        }
      }),
    );
  }

  console.log(JSON.stringify({ scan: 'complete', org, repoCount: repos.length, results }));
}
```

---

## Implementation Details

- **Fork skipping**: By default the bot skips forked repos (`repo.fork === true`) because forks are typically inactive by nature and belong to an upstream project lifecycle.
- **Topic-based opt-out**: Adding the `no-archive` GitHub topic to a repo is the self-service exclusion path for repo owners. This avoids requiring admin intervention for every exception.
- **Warning TTL**: The KV entry `warned:{owner}/{repo}` expires after 60 days. If a repo is saved from archival (a new commit is pushed), the `pushed_at` will drop below the threshold and the warning entry will never be used. At expiration, a future scan that finds the repo inactive again will restart the warning cycle.
- **Grace period precision**: `daysSince` uses UTC day boundaries. The cron fires weekly, so the grace period is accurate to ±7 days. A daily cron (`0 9 * * *`) provides day-level accuracy at the cost of more API calls.
- **Rate limit**: listing 1,000 repos consumes 10 paginated API calls. Opening 20 warning issues + archiving 5 repos = 25 more. Total: well within the 5,000-requests/hour PAT limit.

---

## Anti-patterns

- **Do not archive repos with open issues or unmerged PRs**: add a check — `GET /repos/{owner}/{repo}` returns `open_issues_count`; skip archival if non-zero, or separate the archival decision from issue count.
- **Do not set the KV `warned` key without a TTL**: stale `warned` entries block re-warning if the grace period logic changes. Always set `expirationTtl`.
- **Do not run the cron more than daily**: listOrgRepos is a full paginated scan. Running it hourly wastes quota and provides no benefit since `pushed_at` only changes on pushes.
- **Do not archive repos with active deploy integrations**: check Cloudflare Pages, Vercel, or other integrations before archiving. Use a KV exclusion list updated by those platform bots.

---

## Gotchas

- `pushed_at` reflects pushes to any branch, including automated dependency update branches (Renovate, Dependabot). A repo may appear active because a bot opened a PR, even if no human has touched it in years. Use the Commits API to check for human commits in the last N days for stricter detection.
- Archiving a repo via API succeeds silently even if the repo already has archived set. The PATCH endpoint is idempotent.
- Opening an issue on an already-archived repo returns HTTP 410 Gone. The bot should check `repo.archived` before opening a warning issue (handled by `shouldSkip`).
- The GitHub Apps permission `administration: write` is required to archive repos. A standard `repo` scope PAT does not grant archival rights — you must use a PAT with `delete_repo` or a GitHub App with the administration permission.

---

## Verification

```bash
# Enable dry-run mode
npx wrangler kv key put 'config:global' \
  '{"inactiveDaysThreshold":365,"warningDaysBeforeArchival":14,"dryRun":true}' \
  --binding STATE_KV

# Trigger a manual scan
curl -X POST https://repo-archival-bot.YOUR_SUBDOMAIN.workers.dev/scan

# Check Worker logs for dry-run output
npx wrangler tail repo-archival-bot

# Add a repo to the exclusion list
npx wrangler kv key put 'exclude:example-org/example-repo' \
  'preserved: active infrastructure' --binding STATE_KV

# Disable dry-run and deploy
npx wrangler kv key put 'config:global' \
  '{"inactiveDaysThreshold":365,"warningDaysBeforeArchival":14,"dryRun":false}' \
  --binding STATE_KV
```

---

## Related

- `documentation/docs/policies/github/workers-github-commit-signing-verification.md`
- `documentation/docs/policies/github/workers-github-workflow-cost-tracker.md`
- GitHub Repositories API — update: https://docs.github.com/en/rest/repos/repos#update-a-repository
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/

---

## Sources

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/kv/
- https://docs.github.com/en/rest/repos/repos
- https://docs.github.com/en/rest/issues/issues
