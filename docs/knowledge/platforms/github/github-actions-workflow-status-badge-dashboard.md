# Aggregating Workflow Status Badges into a Living CI Dashboard

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Monorepos and multi-service platforms accumulate dozens of GitHub Actions workflows; engineers waste time clicking through the Actions tab to understand overall health when a single generated dashboard page with live status badges and run history would surface failures instantly.

## Context
GitHub exposes a workflow status badge URL for every named workflow (`/actions/workflows/{workflow_id}/badge.svg`). A scheduled GitHub Actions job can query the Workflow Runs API, aggregate status across workflows and repositories, and push a rendered `STATUS.md` or trigger a GitHub Pages deploy with a richer HTML view. For Cloudflare Workers shops the same job can post a summary to a Workers KV namespace consumed by a status Worker serving the internal tools site.

## Discovering Workflow IDs Programmatically

```typescript
// scripts/collect-workflow-status.ts
const ORG = process.env.GH_ORG!;
const TOKEN = process.env.GH_TOKEN!;
const REPOS = (process.env.REPOS ?? '').split(',').map((r) => r.trim()).filter(Boolean);

interface WorkflowRun {
  name: string;
  workflow_id: number;
  status: string;
  conclusion: string | null;
  html_url: string;
  updated_at: string;
}

interface WorkflowSummary {
  repo: string;
  name: string;
  badgeUrl: string;
  lastRun: WorkflowRun | null;
}

async function ghFetch(path: string) {
  const res = await fetch(`https://api.github.com${path}`, {
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
  });
  if (!res.ok) throw new Error(`GitHub API ${res.status} for ${path}: ${await res.text()}`);
  return res.json();
}

async function getWorkflowSummaries(repo: string): Promise<WorkflowSummary[]> {
  const { workflows } = await ghFetch(`/repos/${ORG}/${repo}/actions/workflows?per_page=100`);
  const summaries: WorkflowSummary[] = [];

  for (const wf of workflows) {
    const { workflow_runs } = await ghFetch(
      `/repos/${ORG}/${repo}/actions/workflows/${wf.id}/runs?per_page=1&branch=main`,
    );
    summaries.push({
      repo,
      name: wf.name,
      badgeUrl: `https://github.com/${ORG}/${repo}/actions/workflows/${wf.path.split('/').pop()}/badge.svg?branch=main`,
      lastRun: workflow_runs[0] ?? null,
    });
  }
  return summaries;
}

const all = (await Promise.all(REPOS.map(getWorkflowSummaries))).flat();
process.stdout.write(JSON.stringify(all, null, 2));
```

## GitHub Actions Workflow

```yaml
# .github/workflows/ci-dashboard.yml
name: Refresh CI Dashboard

on:
  schedule:
    - cron: '*/15 * * * *'   # every 15 minutes
  workflow_dispatch: {}

permissions:
  contents: write   # to push STATUS.md
  id-token: write   # for Workers KV OIDC

jobs:
  refresh:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.DASHBOARD_PUSH_PAT }}

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Collect workflow status
        id: collect
        env:
          GH_ORG: ${{ vars.GH_ORG }}
          GH_TOKEN: ${{ secrets.DASHBOARD_READ_TOKEN }}
          REPOS: ${{ vars.MONITORED_REPOS }}
        run: pnpm tsx scripts/collect-workflow-status.ts > /tmp/status.json

      - name: Render STATUS.md
        env:
          ORG: ${{ vars.GH_ORG }}
        run: pnpm tsx scripts/render-status-md.ts /tmp/status.json > STATUS.md

      - name: Commit and push
        run: |
          git config user.name  "ci-dashboard[bot]"
          git config user.email "ci-dashboard[bot]@users.noreply.github.com"
          git add STATUS.md
          git diff --cached --quiet || git commit -m "chore: refresh CI dashboard [skip ci]"
          git push
```

## Rendering STATUS.md

```typescript
// scripts/render-status-md.ts
import { readFileSync } from 'node:fs';

const summaries = JSON.parse(readFileSync(process.argv[2], 'utf8'));

const lines: string[] = [
  '# CI Dashboard',
  '',
  `_Last updated: ${new Date().toUTCString()}_`,
  '',
];

const byRepo = new Map<string, typeof summaries>();
for (const s of summaries) {
  if (!byRepo.has(s.repo)) byRepo.set(s.repo, []);
  byRepo.get(s.repo)!.push(s);
}

for (const [repo, workflows] of byRepo.entries()) {
  lines.push(`## ${repo}`, '', '| Workflow | Status | Last Run |', '|---|---|---|');
  for (const wf of workflows) {
    const conclusion = wf.lastRun?.conclusion ?? 'unknown';
    const runLink = wf.lastRun?.html_url
      ? `${new Date(wf.lastRun.updated_at).toISOString().slice(0, 16)}`
      : '—';
    const badge = `*${wf.name}*`;
    lines.push(`| ${wf.name} | ${badge} \`${conclusion}\` | ${runLink} |`);
  }
  lines.push('');
}

process.stdout.write(lines.join('\n'));
```

## Publishing to Cloudflare Workers KV

```yaml
      - name: Push status JSON to Workers KV
        env:
          CF_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
          CF_KV_NAMESPACE_ID: ${{ vars.CI_DASHBOARD_KV_ID }}
          CF_API_TOKEN: ${{ secrets.CF_KV_WRITE_TOKEN }}
        run: |
          curl -s --fail-with-body \
            -X PUT \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${CF_KV_NAMESPACE_ID}/values/ci-status" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            --data-binary @/tmp/status.json
```

The status Worker reads the KV value and renders an HTML dashboard:

```typescript
// workers/status-dashboard/src/index.ts
export interface Env {
  CI_STATUS: KVNamespace;
}

export default {
  async fetch(_request: Request, env: Env): Promise<Response> {
    const raw = await env.CI_STATUS.get('ci-status');
    if (!raw) return new Response('No data yet', { status: 503 });

    const summaries = JSON.parse(raw) as Array<{
      repo: string; name: string; lastRun: { conclusion: string; html_url: string } | null;
    }>;

    const failing = summaries.filter(
      (s) => s.lastRun?.conclusion && !['success', 'skipped'].includes(s.lastRun.conclusion),
    );

    return Response.json({
      updated: new Date().toISOString(),
      total: summaries.length,
      failing: failing.length,
      failures: failing.map((s) => ({ repo: s.repo, workflow: s.name, url: s.lastRun!.html_url })),
    });
  },
};
```

## Anti-patterns
- Polling every minute — GitHub's secondary rate limit for authenticated REST requests is 900 per minute per token; a 15-minute interval is safe for up to ~50 workflows across 5 repos.
- Using `GITHUB_TOKEN` for cross-repository reads — it is scoped to the current repository; use a fine-grained PAT with `actions: read` on the monitored repositories.
- Committing `STATUS.md` with `--force` or amending history — use `[skip ci]` in the commit message to prevent a feedback loop but never force-push `main`.
- Storing the KV namespace ID in a secret — it is not sensitive; use a `vars` variable so it is visible in workflow logs for debugging.

## Gotchas
- Badge SVGs from `badge.svg?branch=main` are cached by GitHub's CDN for up to 5 minutes; the badge may lag behind the actual workflow conclusion.
- Workflow files that were renamed retain the old `workflow_id`; the old ID's badge URL 404s until GitHub GC's it. Filter out workflows with no recent runs.
- The `[skip ci]` commit message convention only skips the standard push-triggered CI patterns; workflows using `workflow_run` as a trigger will still fire.
- GitHub Pages deployments from the `contents: write` approach require branch protection rules to allow bot commits on `main`; alternatively deploy to a `gh-pages` branch.

## Verification
1. Trigger `ci-dashboard.yml` manually and confirm `STATUS.md` is committed with the current timestamp.
2. Break a workflow intentionally on the monitored repo and wait for the next scheduled run; confirm the dashboard shows `failure` for that workflow.
3. Check the KV namespace in the Cloudflare dashboard to confirm the `ci-status` key updated within the schedule window.
4. Hit the status Worker endpoint and confirm `failing` count matches the number of broken workflows.

## Related
- `github-actions-notify-slack.md`
- `github-actions-job-summaries-annotations-reporting.md`
- `github-actions-workflow-dispatch.md`
- `github-actions-cache-invalidation-workers-builds.md`

## Sources
- https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/adding-a-workflow-status-badge
- https://docs.github.com/en/rest/actions/workflow-runs
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
