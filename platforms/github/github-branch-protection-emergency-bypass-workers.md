# Emergency Deploy Bypass: Disable Branch Protection, Deploy, Re-enable, Audit in D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A P0 incident requires deploying a hotfix to a Cloudflare Worker immediately. Branch protection rules on `main` require 2 approvals and passing CI — but CI is slow (8 min) and the second reviewer is unavailable. You need a controlled, audited procedure to temporarily bypass branch protection, deploy the fix, and immediately restore protection, with every step logged to D1 for the post-incident review.

## Context

The approach uses the GitHub REST API to disable branch protection rules, performs a direct `wrangler deploy`, then re-enables the original rules via API. All steps are logged with timestamps, actor, reason, and outcome to a D1 `emergency_deploys` audit table. The bypass window is minimized by scripting the entire sequence. The bypass requires a GitHub token with `admin:repo` scope (repo admin only).

---

## Section 1: D1 Audit Schema

```sql
-- migrations/0001_emergency_deploys.sql
CREATE TABLE IF NOT EXISTS emergency_deploys (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  actor            TEXT    NOT NULL,
  repo             TEXT    NOT NULL,
  branch           TEXT    NOT NULL DEFAULT 'main',
  reason           TEXT    NOT NULL,
  worker_name      TEXT    NOT NULL,
  deploy_sha       TEXT,
  bypass_started   TEXT    NOT NULL,
  deploy_completed TEXT,
  bypass_ended     TEXT,
  restored_rules   TEXT,        -- JSON snapshot of re-applied rules
  outcome          TEXT    NOT NULL DEFAULT 'in_progress',  -- in_progress | success | failed
  notes            TEXT
);
```

## Section 2: Emergency Deploy Script (TypeScript)

```typescript
// scripts/emergency-deploy.ts
// Usage: npx tsx scripts/emergency-deploy.ts --reason "P0: login broken" --worker api-gateway

import { execSync, ExecSyncOptions } from 'node:child_process';
import { parseArgs } from 'node:util';

const { values } = parseArgs({
  options: {
    reason:  { type: 'string' },
    worker:  { type: 'string' },
    repo:    { type: 'string', default: process.env.GITHUB_REPO ?? 'example-org/example-repo' },
    branch:  { type: 'string', default: 'main' },
    actor:   { type: 'string', default: process.env.GITHUB_ACTOR ?? process.env.USER ?? 'unknown' },
  },
});

const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
if (!GITHUB_TOKEN) throw new Error('GITHUB_TOKEN env var required');
if (!values.reason) throw new Error('--reason is required');
if (!values.worker) throw new Error('--worker is required');

const [owner, repo] = (values.repo as string).split('/');
const branch = values.branch as string;
const actor = values.actor as string;
const workerName = values.worker as string;
const reason = values.reason as string;

async function githubApi(path: string, method = 'GET', body?: unknown): Promise<unknown> {
  const res = await fetch(`https://api.github.com${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`GitHub API ${method} ${path} → ${res.status}: ${text}`);
  return text ? JSON.parse(text) : null;
}

function run(cmd: string, opts?: ExecSyncOptions): string {
  console.log(`$ ${cmd}`);
  return execSync(cmd, { encoding: 'utf8', stdio: 'pipe', ...opts }) as string;
}

async function main() {
  console.log(`\n=== EMERGENCY DEPLOY ===`);
  console.log(`Actor:  ${actor}`);
  console.log(`Worker: ${workerName}`);
  console.log(`Reason: ${reason}`);
  console.log(`Repo:   ${owner}/${repo}  Branch: ${branch}`);
  console.log('========================\n');

  const bypassStarted = new Date().toISOString();

  // --- Step 1: Snapshot existing branch protection rules ---
  console.log('[1/5] Snapshotting branch protection rules...');
  const rules = await githubApi(
    `/repos/${owner}/${repo}/branches/${branch}/protection`
  ) as Record<string, unknown>;
  console.log('Current rules:', JSON.stringify(rules, null, 2));

  // --- Step 2: Disable required reviews temporarily ---
  console.log('[2/5] Disabling required reviews...');
  await githubApi(
    `/repos/${owner}/${repo}/branches/${branch}/protection/required_pull_request_reviews`,
    'DELETE'
  );

  // --- Step 3: Deploy Worker ---
  console.log('[3/5] Deploying worker...');
  const deploySha = run('git rev-parse HEAD').trim();
  let deployOutcome = 'failed';
  let deployNotes = '';

  try {
    run(`npx wrangler deploy --env production`, {
      cwd: `workers/${workerName}`,
      env: { ...process.env },
    });
    deployOutcome = 'success';
    console.log(`[3/5] Deploy succeeded (SHA: ${deploySha})`);
  } catch (err) {
    deployNotes = String(err);
    console.error('[3/5] Deploy FAILED:', deployNotes);
  }

  // --- Step 4: Re-enable branch protection ---
  console.log('[4/5] Restoring branch protection rules...');
  const prReviews = rules['required_pull_request_reviews'] as Record<string, unknown> | undefined;
  if (prReviews) {
    await githubApi(
      `/repos/${owner}/${repo}/branches/${branch}/protection/required_pull_request_reviews`,
      'PATCH',
      {
        required_approving_review_count:
          (prReviews['required_approving_review_count'] as number) ?? 2,
        dismiss_stale_reviews: prReviews['dismiss_stale_reviews'] ?? true,
        require_code_owner_reviews: prReviews['require_code_owner_reviews'] ?? false,
      }
    );
  }
  const bypassEnded = new Date().toISOString();
  console.log(`[4/5] Branch protection restored at ${bypassEnded}`);

  // --- Step 5: Write audit log to D1 via Wrangler ---
  console.log('[5/5] Writing audit log to D1...');
  const auditSQL = [
    `INSERT INTO emergency_deploys`,
    `  (actor, repo, branch, reason, worker_name, deploy_sha,`,
    `   bypass_started, deploy_completed, bypass_ended, restored_rules, outcome, notes)`,
    `VALUES (`,
    `  '${actor.replace(/'/g, "''")}',`,
    `  '${owner}/${repo}',`,
    `  '${branch}',`,
    `  '${reason.replace(/'/g, "''")}',`,
    `  '${workerName}',`,
    `  '${deploySha}',`,
    `  '${bypassStarted}',`,
    `  '${new Date().toISOString()}',`,
    `  '${bypassEnded}',`,
    `  '${JSON.stringify(rules).replace(/'/g, "''")}',`,
    `  '${deployOutcome}',`,
    `  '${deployNotes.replace(/'/g, "''")}'`,
    `)`,
  ].join(' ');

  run(`npx wrangler d1 execute audit-db --remote --command "${auditSQL.replace(/"/g, '\\"')}"`);

  // --- Result ---
  if (deployOutcome === 'failed') {
    console.error('\nEMERGENCY DEPLOY FAILED — protection restored, incident open');
    process.exit(1);
  }

  console.log('\nEMERGENCY DEPLOY COMPLETE');
  console.log(`SHA: ${deploySha}`);
  console.log(`Bypass window: ${bypassStarted} → ${bypassEnded}`);
}

main().catch(err => { console.error(err); process.exit(1); });
```

## Section 3: GitHub Actions Manual Trigger

```yaml
# .github/workflows/emergency-deploy.yml
name: Emergency Deploy (Bypass Branch Protection)

on:
  workflow_dispatch:
    inputs:
      worker:
        description: 'Worker name (e.g. api-gateway)'
        required: true
      reason:
        description: 'P0 reason (written to audit log)'
        required: true

permissions:
  contents: write   # required to modify branch protection via Actions token

jobs:
  emergency-deploy:
    runs-on: ubuntu-latest
    environment: emergency   # requires manual approval from repo admins

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Emergency Deploy
        env:
          GITHUB_TOKEN: ${{ secrets.EMERGENCY_GITHUB_TOKEN }}   # token with admin:repo
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          GITHUB_ACTOR: ${{ github.actor }}
          GITHUB_REPO: ${{ github.repository }}
        run: |
          npx tsx scripts/emergency-deploy.ts \
            --reason "${{ inputs.reason }}" \
            --worker "${{ inputs.worker }}"
```

## Section 4: Audit Query Worker

```typescript
// workers/audit-api/src/index.ts
// Read-only API for reviewing emergency deploys
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/emergency-deploys') return new Response('Not Found', { status: 404 });

    const limit = Number(url.searchParams.get('limit') ?? '20');
    const rows = await env.DB
      .prepare(
        `SELECT id, actor, worker_name, reason, bypass_started, bypass_ended, outcome
         FROM emergency_deploys
         ORDER BY id DESC
         LIMIT ?`
      )
      .bind(Math.min(limit, 100))
      .all();

    return Response.json(rows.results);
  },
};
```

## Anti-patterns

- **Leaving branch protection disabled**: The bypass window must be as short as possible. Always re-enable in a `finally` block or equivalent, even if the deploy fails.
- **Using a shared long-lived admin token**: Create a dedicated `EMERGENCY_GITHUB_TOKEN` PAT with minimum required scopes (`repo`, `admin:repo`), stored as a GitHub secret, rotated quarterly.
- **Running this from a local machine without audit trail**: Always go through GitHub Actions `workflow_dispatch` so the triggering actor is recorded in the Actions audit log in addition to D1.
- **No environment protection**: Wrap the job in a GitHub Environment (`emergency`) that requires manual approval from at least one admin before the bypass starts.

## Gotchas

- The GitHub token used in Actions (`GITHUB_TOKEN`) typically does NOT have permission to update branch protection. You need a PAT or GitHub App installation token with `admin:repo` scope, stored as a separate secret.
- `DELETE /protection/required_pull_request_reviews` only removes the review requirement; other rules (status checks, signed commits) remain active. If CI status checks also block you, you need to update those separately.
- The `bypassEnded` timestamp is recorded after the protection is restored, not after the deploy. The actual deploy window is `bypass_started → deploy_completed`.
- SQLite string quoting in D1 uses single quotes. The audit log insertion double-escapes single quotes (`''`) to avoid SQL injection from user-supplied reason strings. For production, use D1 prepared statements instead.

## Verification

```bash
# Check current branch protection rules
gh api repos/{owner}/{repo}/branches/main/protection | jq .

# Run emergency deploy (dry-run by echoing commands)
GITHUB_TOKEN=ghp_xxx \
npx tsx scripts/emergency-deploy.ts \
  --reason 'P0 test' \
  --worker api-gateway

# Query audit log
npx wrangler d1 execute audit-db --remote \
  --command 'SELECT actor, worker_name, reason, outcome, bypass_started FROM emergency_deploys ORDER BY id DESC LIMIT 5;'
```

## Related

- `documentation/categories/github/github-actions-workers-post-deploy-health-check.md`
- `documentation/categories/github/github-issue-linear-sync-workers-webhook.md`
- `documentation/workers/workers-wrangler-toml-environments.md`

## Sources

- https://docs.github.com/en/rest/branches/branch-protection
- https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
