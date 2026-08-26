# Pages Preview Deployment Cleanup Automation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After several months of active development the example project Cloudflare Pages project
accumulates hundreds of stale preview deployments. Each deployment maps to a unique
subdomain (`<hash>.example project-pages.pages.dev`), consumes a deployment slot counted
against the plan limit, and remains discoverable by anyone who has the URL.

Symptoms include:
- Cloudflare dashboard shows 400+ deployments; the Pages plan cap is approached
- Pull requests merged months ago still have live preview URLs crawled by bots
- Old preview deployments reference outdated environment bindings (D1 databases,
  KV namespaces that have since been rotated)
- Manual cleanup via the dashboard is time-prohibitive

## Context

Cloudflare Pages does not natively garbage-collect preview deployments when a
branch is deleted or a pull request is closed. Deployments live until explicitly
deleted via the API. The Pages REST API provides per-deployment delete endpoints
that are safe to call in automation.

The example project convention:
- `production` deployment — never deleted by automation
- `staging` branch deployment — retained for 30 days after last push
- Pull-request preview deployments — deleted when the PR is merged or closed

---

## Section 1 — Pages API Overview

```typescript
// lib/pages-api.ts
const BASE = 'https://api.cloudflare.com/client/v4';

export interface PagesDeployment {
  id: string;
  url: string;
  environment: 'production' | 'preview';
  created_on: string;
  latest_stage: { status: string };
  deployment_trigger: {
    type: 'push' | 'adhoc';
    metadata?: { branch?: string; commit_hash?: string };
  };
}

export async function listDeployments(
  accountId: string,
  projectName: string,
  token: string,
  page = 1,
  perPage = 25,
): Promise<PagesDeployment[]> {
  const url = new URL(
    `${BASE}/accounts/${accountId}/pages/projects/${projectName}/deployments`,
  );
  url.searchParams.set('page', String(page));
  url.searchParams.set('per_page', String(perPage));

  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` },
  });
  const json = (await res.json()) as { result: PagesDeployment[] };
  return json.result ?? [];
}

export async function deleteDeployment(
  accountId: string,
  projectName: string,
  deploymentId: string,
  token: string,
): Promise<void> {
  const url = `${BASE}/accounts/${accountId}/pages/projects/${projectName}/deployments/${deploymentId}`;
  const res = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`DELETE ${deploymentId} failed (${res.status}): ${body}`);
  }
}
```

## Section 2 — Cleanup Script (TypeScript)

```typescript
// scripts/cleanup-preview-deployments.ts
import { listDeployments, deleteDeployment, PagesDeployment } from '../lib/pages-api';

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const PROJECT = process.env.CF_PAGES_PROJECT ?? 'example project';
const TOKEN = process.env.CF_API_TOKEN!;
const DRY_RUN = process.argv.includes('--dry-run');

// Retain production deployments always; keep previews younger than this
const PREVIEW_MAX_AGE_DAYS = parseInt(process.env.PREVIEW_MAX_AGE_DAYS ?? '30', 10);

async function collectAllDeployments(): Promise<PagesDeployment[]> {
  const all: PagesDeployment[] = [];
  let page = 1;
  while (true) {
    const batch = await listDeployments(ACCOUNT_ID, PROJECT, TOKEN, page, 25);
    if (batch.length === 0) break;
    all.push(...batch);
    page++;
  }
  return all;
}

function isEligibleForDeletion(d: PagesDeployment): boolean {
  if (d.environment === 'production') return false;
  const ageMs = Date.now() - new Date(d.created_on).getTime();
  const ageDays = ageMs / 86_400_000;
  return ageDays > PREVIEW_MAX_AGE_DAYS;
}

async function main(): Promise<void> {
  console.log(`[cleanup] Project: ${PROJECT}, dry-run: ${DRY_RUN}`);
  const deployments = await collectAllDeployments();
  const eligible = deployments.filter(isEligibleForDeletion);

  console.log(`[cleanup] Total deployments: ${deployments.length}`);
  console.log(`[cleanup] Eligible for deletion: ${eligible.length}`);

  let deleted = 0;
  let failed = 0;

  for (const d of eligible) {
    const branch = d.deployment_trigger.metadata?.branch ?? 'unknown';
    const age = Math.round(
      (Date.now() - new Date(d.created_on).getTime()) / 86_400_000,
    );
    console.log(`  [${DRY_RUN ? 'DRY' : 'DEL'}] ${d.id} branch=${branch} age=${age}d url=${d.url}`);

    if (!DRY_RUN) {
      try {
        await deleteDeployment(ACCOUNT_ID, PROJECT, d.id, TOKEN);
        deleted++;
        // Rate-limit: 2 req/s to stay within Pages API limits
        await new Promise((r) => setTimeout(r, 500));
      } catch (err) {
        console.error(`  [FAIL] ${d.id}: ${(err as Error).message}`);
        failed++;
      }
    }
  }

  console.log(`[cleanup] Done. Deleted: ${deleted}, Failed: ${failed}`);
  if (failed > 0) process.exit(1);
}

main();
```

## Section 3 — GitHub Actions Workflow

```yaml
# .github/workflows/cleanup-preview-deployments.yml
name: Cleanup Stale Pages Preview Deployments

on:
  # Run on PR close/merge
  pull_request:
    types: [closed]

  # Also run nightly for age-based cleanup
  schedule:
    - cron: '0 3 * * *'

  # Allow manual trigger with dry-run option
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Dry run (no deletions)'
        type: boolean
        default: true

jobs:
  cleanup:
    name: Delete stale preview deployments
    runs-on: ubuntu-latest
    environment: production  # gates on manual approval in sensitive envs

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Run cleanup
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_PAGES_CLEANUP_TOKEN }}
          CF_PAGES_PROJECT: example project
          PREVIEW_MAX_AGE_DAYS: '30'
        run: |
          FLAGS=""
          # On PR close, always clean up immediately (age=0 override not needed
          # because we target by branch name — see branch-targeted variant below)
          if [ "${{ github.event_name }}" = "workflow_dispatch" ] && \
             [ "${{ inputs.dry_run }}" = "true" ]; then
            FLAGS="--dry-run"
          fi
          npx ts-node scripts/cleanup-preview-deployments.ts $FLAGS
```

## Section 4 — Branch-Targeted Cleanup on PR Close

```typescript
// scripts/cleanup-branch-deployments.ts
// Called with: CF_BRANCH=<branch> ts-node cleanup-branch-deployments.ts
import { listDeployments, deleteDeployment } from '../lib/pages-api';

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const PROJECT = process.env.CF_PAGES_PROJECT ?? 'example project';
const TOKEN = process.env.CF_API_TOKEN!;
const TARGET_BRANCH = process.env.CF_BRANCH!;

if (!TARGET_BRANCH) {
  console.error('CF_BRANCH must be set');
  process.exit(1);
}

async function main(): Promise<void> {
  console.log(`[branch-cleanup] Removing all deployments for branch: ${TARGET_BRANCH}`);
  const all = await collectAll();
  const matching = all.filter(
    (d) =>
      d.environment === 'preview' &&
      d.deployment_trigger.metadata?.branch === TARGET_BRANCH,
  );
  console.log(`[branch-cleanup] Found ${matching.length} deployment(s)`);

  for (const d of matching) {
    await deleteDeployment(ACCOUNT_ID, PROJECT, d.id, TOKEN);
    console.log(`  Deleted ${d.id} (${d.url})`);
    await new Promise((r) => setTimeout(r, 500));
  }
}

async function collectAll() {
  const { listDeployments: list } = await import('../lib/pages-api');
  const out = [];
  let page = 1;
  while (true) {
    const batch = await list(ACCOUNT_ID, PROJECT, TOKEN, page++, 25);
    if (!batch.length) break;
    out.push(...batch);
  }
  return out;
}

main();
```

```yaml
# In the PR close job:
- name: Delete preview deployments for closed branch
  if: github.event_name == 'pull_request' && github.event.action == 'closed'
  env:
    CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
    CF_API_TOKEN: ${{ secrets.CF_PAGES_CLEANUP_TOKEN }}
    CF_PAGES_PROJECT: example project
    CF_BRANCH: ${{ github.head_ref }}
  run: npx ts-node scripts/cleanup-branch-deployments.ts
```

## Section 5 — API Token Scoping

The cleanup token requires minimal permissions. Do not reuse the full deploy token.

```bash
# Required Pages API token permissions (Cloudflare dashboard):
# Zone: Pages — Edit (allows deployment delete)
# Account: Cloudflare Pages — Edit
#
# Recommended: create a dedicated API token named cf-pages-cleanup-token
# with these permissions only — do not include Workers, D1, or KV.
```

## Anti-patterns

- **Using the global API key** for cleanup automation — a leaked script credential
  would expose the entire Cloudflare account.
- **Deleting production-environment deployments** — the `environment === 'production'`
  guard must be present and tested. The Pages API will allow deleting production
  deployments; the platform will just re-create the active deployment, but
  temporarily breaking the production URL during deletion is a real risk.
- **Batching deletes without rate limiting** — the Pages API has undocumented rate
  limits around 5–10 req/s. Exceeding them returns 429 and some deletions fail
  silently. Use `setTimeout(500)` between requests.
- **Running cleanup in the same job as deploy** — if the deploy job fails and is
  retried, the cleanup already ran and the retried deploy has no preview URL to
  target.

## Gotchas

- Deleted deployments still appear in `wrangler pages deployment list` output for
  up to 5 minutes due to API propagation delay.
- A Pages deployment with `latest_stage.status === 'active'` can still be deleted
  via the API. There is no deletion guard based on stage status — the guard must be
  implemented in the script (check `environment`).
- If the Pages project has a custom domain pointing at a specific deployment ID
  (rare, but possible with direct upload workflows), deleting that deployment breaks
  the custom domain until the next deploy. Always check custom domain routing before
  bulk-deleting.
- The `per_page` maximum for `listDeployments` is 25. Pagination is required for
  any project with more than 25 deployments.
- GitHub Actions `pull_request.closed` fires for both merged and abandoned PRs.
  Both should trigger cleanup — do not guard on `merged === true`.

## Verification

```bash
# Count current preview deployments
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/example project/deployments?per_page=25" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '[.result[] | select(.environment == "preview")] | length'

# Dry-run cleanup to see what would be deleted
CF_ACCOUNT_ID=xxx CF_API_TOKEN=xxx CF_PAGES_PROJECT=example project PREVIEW_MAX_AGE_DAYS=30 \
  npx ts-node scripts/cleanup-preview-deployments.ts --dry-run

# Confirm a specific deployment is gone
DEPLOY_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/example project/deployments/${DEPLOY_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.success, .errors'
```

## Related

- `cloudflare-pages-preview-deployments.md`
- `cloudflare-pages-branch-deploy-preview-d1-seeding.md`
- `environment-teardown-hygiene.md`
- `oidc-federated-deploy-credentials.md`
- `pages-functions-env-var-management.md`

## Sources

- Cloudflare Pages REST API — Deployments: https://developers.cloudflare.com/api/resources/pages/subresources/projects/subresources/deployments/
- Pages deployment limits: https://developers.cloudflare.com/pages/platform/limits/
- Cloudflare API token permissions: https://developers.cloudflare.com/fundamentals/api/reference/permissions/
