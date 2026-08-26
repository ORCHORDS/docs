# Deployment Approval Gates with GitHub Environments

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your staging Workers deployment is fully automated, but promoting to production requires a human to review the change and click Approve. Without enforcement, developers occasionally push directly to production workflows, skipping QA. You also need a tamper-evident audit trail of who approved what and when, stored in D1.

## Context

- GitHub Environments let you attach required-reviewer rules to a deployment job. A job targeting a protected environment is paused until a listed reviewer approves.
- The Cloudflare Workers Deployments API exposes deployment IDs that can be written back to GitHub via the Deployment Status API, linking the GitHub approval to the actual Workers rollout.
- D1 stores the full approval audit trail (approver, timestamp, GitHub run ID, Workers deployment ID) independently of GitHub, so it survives repository deletions or log retention limits.
- Automatic promotion from staging to production is triggered by GitHub Actions after all staging checks pass, but the production job still requires a human gate.

## Solution

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

permissions:
  deployments: write
  id-token: write
  contents: read

jobs:
  # ------------------------------------------------------------------
  # 1. Deploy to staging (no approval required)
  # ------------------------------------------------------------------
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    outputs:
      workers_deployment_id: ${{ steps.deploy.outputs.workers_deployment_id }}
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Deploy to staging
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          OUTPUT=$(npx wrangler deploy --env staging --json 2>&1)
          echo "$OUTPUT"
          DEPLOYMENT_ID=$(echo "$OUTPUT" | jq -r '.deployment_id // empty')
          echo "workers_deployment_id=$DEPLOYMENT_ID" >> "$GITHUB_OUTPUT"

      - name: Run smoke tests against staging
        run: npm run test:smoke -- --base-url https://orchords-api-staging.orchords.workers.dev

      - name: Record staging deployment in D1
        env:
          AUDIT_TOKEN: ${{ secrets.AUDIT_WORKER_TOKEN }}
        run: |
          curl -sf -X POST https://orchords-audit.orchords.workers.dev/deployments \
            -H "Authorization: Bearer $AUDIT_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{
              "environment": "staging",
              "github_run_id": "${{ github.run_id }}",
              "workers_deployment_id": "${{ steps.deploy.outputs.workers_deployment_id }}",
              "sha": "${{ github.sha }}",
              "actor": "${{ github.actor }}"
            }'

  # ------------------------------------------------------------------
  # 2. Gate: manual approval required (GitHub Environment protection)
  # ------------------------------------------------------------------
  await-approval:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production-gate   # <-- protected environment with required reviewers
    steps:
      - name: Approval checkpoint
        run: echo "Approved by ${{ github.actor }} — proceeding to production."

  # ------------------------------------------------------------------
  # 3. Deploy to production after approval
  # ------------------------------------------------------------------
  deploy-production:
    needs: await-approval
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Deploy to production
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PROD }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          OUTPUT=$(npx wrangler deploy --env production --json 2>&1)
          echo "$OUTPUT"
          DEPLOYMENT_ID=$(echo "$OUTPUT" | jq -r '.deployment_id // empty')
          echo "workers_deployment_id=$DEPLOYMENT_ID" >> "$GITHUB_OUTPUT"

      - name: Record production deployment and approval in D1
        env:
          AUDIT_TOKEN: ${{ secrets.AUDIT_WORKER_TOKEN }}
        run: |
          curl -sf -X POST https://orchords-audit.orchords.workers.dev/deployments \
            -H "Authorization: Bearer $AUDIT_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{
              "environment": "production",
              "github_run_id": "${{ github.run_id }}",
              "workers_deployment_id": "${{ steps.deploy.outputs.workers_deployment_id }}",
              "sha": "${{ github.sha }}",
              "actor": "${{ github.actor }}",
              "approved_by": "${{ github.actor }}",
              "approved_at": "${{ github.event.head_commit.timestamp }}"
            }'

      - name: Update GitHub Deployment Status
        uses: chrnorm/deployment-status@v2
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          state: success
          environment-url: https://orchords-api.orchords.workers.dev
          deployment-id: ${{ github.run_id }}
```

```typescript
// src/audit-worker/index.ts
// Lightweight audit-trail Worker that records deployments and approvals in D1.

import { D1Database } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  AUDIT_TOKEN: string;
}

interface DeploymentPayload {
  environment: string;
  github_run_id: string;
  workers_deployment_id: string;
  sha: string;
  actor: string;
  approved_by?: string;
  approved_at?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Auth
    const auth = request.headers.get('Authorization') ?? '';
    if (auth !== `Bearer ${env.AUDIT_TOKEN}`) {
      return new Response('Unauthorized', { status: 401 });
    }

    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/deployments') {
      return handleDeploymentRecord(request, env);
    }

    if (request.method === 'GET' && url.pathname === '/deployments') {
      return handleDeploymentList(url, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handleDeploymentRecord(request: Request, env: Env): Promise<Response> {
  const payload = (await request.json()) as DeploymentPayload;

  await env.DB.prepare(
    `INSERT INTO deployment_audit
       (environment, github_run_id, workers_deployment_id, sha, actor, approved_by, approved_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      payload.environment,
      payload.github_run_id,
      payload.workers_deployment_id,
      payload.sha,
      payload.actor,
      payload.approved_by ?? null,
      payload.approved_at ?? null,
    )
    .run();

  return Response.json({ ok: true });
}

async function handleDeploymentList(url: URL, env: Env): Promise<Response> {
  const environment = url.searchParams.get('environment') ?? 'production';
  const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '25', 10), 100);

  const rows = await env.DB.prepare(
    `SELECT * FROM deployment_audit
     WHERE environment = ?
     ORDER BY recorded_at DESC
     LIMIT ?`,
  )
    .bind(environment, limit)
    .all();

  return Response.json(rows.results);
}
```

```sql
-- D1 migration: create deployment_audit table
CREATE TABLE IF NOT EXISTS deployment_audit (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  environment            TEXT    NOT NULL,
  github_run_id          TEXT    NOT NULL,
  workers_deployment_id  TEXT,
  sha                    TEXT    NOT NULL,
  actor                  TEXT    NOT NULL,
  approved_by            TEXT,
  approved_at            TEXT,
  recorded_at            TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_env_recorded ON deployment_audit(environment, recorded_at DESC);
```

## Implementation Details

**GitHub Environment setup** — In GitHub repository Settings > Environments, create `staging`, `production-gate`, and `production`. On `production-gate`, enable "Required reviewers" and add the names of your release managers. This is the only job that pauses for human input.

**Separation of gate and deploy** — The `await-approval` job has no Cloudflare credentials; it only waits. The `deploy-production` job has production credentials but only runs after the gate job succeeds, ensuring credentials are never available at the approval step.

**Reviewer assignment** — GitHub lets you specify up to 6 individual accounts or teams as required reviewers per environment. The approver must be distinct from the actor who pushed the commit (configurable via the "Prevent self-review" checkbox).

**Deployment Status API** — After the Workers deploy, the workflow posts a `success` status back to GitHub via `chrnorm/deployment-status`. This links the GitHub deployment event (visible in the repository's Deployments tab) to the actual Workers rollout, giving a clickable audit trail.

**Automatic promotion** — The `deploy-production` job depends on `await-approval`, which depends on `deploy-staging`. If staging smoke tests fail, the approval gate is never reached and production is never updated — fully automated gate-keeping for green builds.

**D1 audit trail** — Because GitHub's deployment history is tied to repository retention policies, storing the same data in D1 provides a durable, queryable audit log. The `deployment_audit` table records the approver's GitHub username and timestamp, the Workers deployment ID, and the exact git SHA deployed.

## Anti-patterns

- Putting Cloudflare production API tokens in the `staging` job — if staging is compromised, production is exposed. Use separate tokens per environment.
- Using a single GitHub Environment called `production` for both the gate and the deploy — mixing concerns makes it impossible to query "who approved" separately from "what was deployed".
- Relying solely on GitHub's deployment history for compliance audit — GitHub log retention is configurable and can be reset; D1 is your source of truth.
- Skipping the smoke-test step in staging — the approval gate only works if humans trust the signal they are approving.

## Gotchas

- GitHub Environment protection rules are only enforced on **Jobs**, not Steps. The gate must be a separate job.
- `GITHUB_TOKEN` automatic permissions do not include `deployments: write` by default — add it explicitly in the `permissions` block.
- If the `await-approval` job times out (default 6 hours for environment deployments), the production deploy is cancelled. Adjust the timeout in the Environment settings.
- `wrangler deploy --json` was added in Wrangler 3.22; ensure your CI uses a pinned version that supports it.
- The Workers Deployments API returns a `deployment_id` only when using the Versions API (gradual rollout). For standard deploys, capture the deployment tag from `wrangler deployments list`.

## Verification

```bash
# List recent production deployments with approvers
curl -s \
  -H "Authorization: Bearer $AUDIT_TOKEN" \
  "https://orchords-audit.orchords.workers.dev/deployments?environment=production&limit=10" \
  | jq '[.[] | {sha: .sha[0:7], actor: .actor, approved_by: .approved_by, recorded_at: .recorded_at}]'

# Confirm the protection rule is set on the GitHub Environment
gh api repos/example-org/example-repo/environments/production-gate \
  --jq '.protection_rules[] | select(.type == "required_reviewers") | .reviewers[].reviewer.login'
```

## Related

- `documentation/categories/deploy/workers-zero-downtime-d1-migration.md` — running migrations as part of the deployment pipeline
- `documentation/categories/deploy/workers-version-pinning-gradual-rollout.md` — gradual traffic rollout after approval
- `documentation/categories/deploy/workers-secrets-rotation-automation.md` — secret rotation triggered post-deploy
- GitHub Docs: Using environments for deployment
- Cloudflare Workers Deployments API

## Sources

- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- https://developers.cloudflare.com/workers/platform/deployments/
- https://developers.cloudflare.com/api/resources/workers/subresources/deployments/
- https://github.com/chrnorm/deployment-status
