# GitHub Deployments API Environment Promotion and Lifecycle Management from Workers CI

2026-08-24 / example.com / production

---

## Symptom / Use-case

A Cloudflare Workers CI pipeline deploys the same build artefact across three environments
(preview → staging → production). GitHub's Deployments API lets each environment transition be
recorded with a deployment record and a deployment status, making the promotion chain visible in
the GitHub UI (branch graph, PR checks, environment dashboards). Without this, a single PR shows
no environment history and operators cannot tell whether the build currently in production came
from main or from a previous release. This article covers creating deployments, advancing statuses
(`queued → in_progress → success`), marking superseded deployments `inactive`, and rolling back
by pointing the production environment at an earlier deployment SHA.

## Context

GitHub Deployments API objects:

| Object | Description |
|---|---|
| **Deployment** | Immutable record: ref, SHA, environment, payload |
| **Deployment Status** | Mutable progress record attached to a deployment |

Valid `state` values: `error`, `failure`, `inactive`, `in_progress`, `queued`, `pending`,
`success`. The transition `inactive` is used to mark a deployment that was superseded; GitHub
displays only the latest non-inactive deployment per environment on the repository home page.

```
PR merge to main
    │
    ▼
[1] Create deployment (env: preview, ref: SHA)
    deployment_id = 1234
    │
    ▼
[2] Set status: queued   (1234)
[3] wrangler deploy --env preview
[4] Set status: success  (1234)  → "preview" environment shows green tick
    │
    ▼  (after smoke tests pass)
[5] Create deployment (env: staging, ref: SHA)  deployment_id = 1235
[6] Set status: in_progress (1235)
[7] wrangler deploy --env staging
[8] Set status: success     (1235)
    │
    ▼  (manual approval or auto-promote)
[9] Mark previous production deployment inactive
[10] Create deployment (env: production, ref: SHA)  deployment_id = 1236
[11] Set status: in_progress (1236)
[12] wrangler deploy --env production
[13] Set status: success     (1236)
```

## Code

### GitHub Deployments API helper in TypeScript

```typescript
// src/github-deployments.ts

interface DeploymentOptions {
  owner: string;
  repo: string;
  ref: string;       // git SHA or branch name
  environment: string;
  description?: string;
  payload?: Record<string, unknown>;
  token: string;
}

interface StatusOptions {
  owner: string;
  repo: string;
  deploymentId: number;
  state: "queued" | "in_progress" | "success" | "failure" | "error" | "inactive";
  environmentUrl?: string;
  logUrl?: string;
  description?: string;
  token: string;
}

export async function createDeployment(opts: DeploymentOptions): Promise<number> {
  const res = await fetch(
    `https://api.github.com/repos/${opts.owner}/${opts.repo}/deployments`,
    {
      method: "POST",
      headers: githubHeaders(opts.token),
      body: JSON.stringify({
        ref: opts.ref,
        environment: opts.environment,
        description: opts.description ?? `Deploy to ${opts.environment}`,
        auto_merge: false,
        required_contexts: [],  // skip status checks; CI already passed
        payload: opts.payload ?? {},
      }),
    },
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`createDeployment failed ${res.status}: ${body}`);
  }

  const { id } = (await res.json()) as { id: number };
  return id;
}

export async function setDeploymentStatus(opts: StatusOptions): Promise<void> {
  const res = await fetch(
    `https://api.github.com/repos/${opts.owner}/${opts.repo}/deployments/${opts.deploymentId}/statuses`,
    {
      method: "POST",
      headers: githubHeaders(opts.token),
      body: JSON.stringify({
        state: opts.state,
        environment_url: opts.environmentUrl,
        log_url: opts.logUrl,
        description: opts.description,
      }),
    },
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`setDeploymentStatus failed ${res.status}: ${body}`);
  }
}

export async function markEnvironmentDeploymentsInactive(
  owner: string,
  repo: string,
  environment: string,
  exceptDeploymentId: number,
  token: string,
): Promise<void> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/deployments?environment=${environment}&per_page=30`,
    { headers: githubHeaders(token) },
  );

  const deployments = (await res.json()) as Array<{ id: number }>;

  await Promise.all(
    deployments
      .filter((d) => d.id !== exceptDeploymentId)
      .map((d) =>
        setDeploymentStatus({
          owner,
          repo,
          deploymentId: d.id,
          state: "inactive",
          description: `Superseded by deployment ${exceptDeploymentId}`,
          token,
        }),
      ),
  );
}

function githubHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "orchords-ci/1.0",
  };
}
```

### GitHub Actions workflow — full promotion chain

```yaml
# .github/workflows/promote.yml
name: Build → Preview → Staging → Production

on:
  push:
    branches: [main]

permissions:
  contents: read
  deployments: write  # Required to create deployments and statuses

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    environment: preview
    outputs:
      deployment-id: ${{ steps.create.outputs.id }}
    steps:
      - uses: actions/checkout@v4

      - name: Create preview deployment
        id: create
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: |
          ID=$(gh api repos/${{ github.repository }}/deployments \
            -X POST \
            --field ref=${{ github.sha }} \
            --field environment=preview \
            --field auto_merge=false \
            --field 'required_contexts[]=' \
            -q .id)
          echo "id=$ID" >> "$GITHUB_OUTPUT"
          gh api repos/${{ github.repository }}/deployments/$ID/statuses \
            -X POST --field state=in_progress

      - name: Deploy to preview
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: npx wrangler deploy --env preview

      - name: Set preview deployment success
        if: success()
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: |
          gh api repos/${{ github.repository }}/deployments/${{ steps.create.outputs.id }}/statuses \
            -X POST \
            --field state=success \
            --field environment_url=https://preview.example.workers.dev \
            --field description="Preview deployment succeeded"

      - name: Set preview deployment failure
        if: failure()
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: |
          gh api repos/${{ github.repository }}/deployments/${{ steps.create.outputs.id }}/statuses \
            -X POST \
            --field state=failure

  deploy-staging:
    needs: deploy-preview
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - name: Promote to staging
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: |
          ID=$(gh api repos/${{ github.repository }}/deployments \
            -X POST \
            --field ref=${{ github.sha }} \
            --field environment=staging \
            --field auto_merge=false \
            --field 'required_contexts[]=' \
            -q .id)
          echo "DEPLOY_ID=$ID" >> "$GITHUB_ENV"
          gh api repos/${{ github.repository }}/deployments/$ID/statuses \
            -X POST --field state=in_progress

      - name: Deploy to staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}
        run: npx wrangler deploy --env staging

      - name: Set staging success
        if: success()
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: |
          gh api repos/${{ github.repository }}/deployments/$DEPLOY_ID/statuses \
            -X POST \
            --field state=success \
            --field environment_url=https://staging.example.com

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval
    steps:
      - uses: actions/checkout@v4

      - name: Create production deployment and mark previous inactive
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: |
          NEW_ID=$(gh api repos/${{ github.repository }}/deployments \
            -X POST \
            --field ref=${{ github.sha }} \
            --field environment=production \
            --field auto_merge=false \
            --field 'required_contexts[]=' \
            -q .id)
          echo "DEPLOY_ID=$NEW_ID" >> "$GITHUB_ENV"

          gh api repos/${{ github.repository }}/deployments \
            --field environment=production \
            --field per_page=30 \
            -q '.[] | select(.id != '"$NEW_ID"') | .id' |
          while read OLD_ID; do
            gh api repos/${{ github.repository }}/deployments/$OLD_ID/statuses \
              -X POST --field state=inactive || true
          done

          gh api repos/${{ github.repository }}/deployments/$NEW_ID/statuses \
            -X POST --field state=in_progress

      - name: Deploy to production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PROD }}
        run: npx wrangler deploy --env production

      - name: Set production success
        if: success()
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: |
          gh api repos/${{ github.repository }}/deployments/$DEPLOY_ID/statuses \
            -X POST \
            --field state=success \
            --field environment_url=https://api.example.com \
            --field description="Production deployment succeeded"
```

### Rollback — redeploy a previous SHA via the Deployments API

```shell
#!/usr/bin/env bash
# rollback.sh — find the last successful production deployment and redeploy it

REPO="${GITHUB_REPOSITORY}"
GH_TOKEN="${GH_TOKEN}"

# Find SHA of the last-but-one successful production deployment
PREV_SHA=$(gh api \
  "repos/${REPO}/deployments?environment=production&per_page=10" \
  -q '[.[] | select(.id != '"$CURRENT_DEPLOY_ID"')] | .[0].sha')

echo "Rolling back production to $PREV_SHA"

# Check out that SHA and deploy
git checkout "$PREV_SHA"
CLOUDFLARE_API_TOKEN="$CF_API_TOKEN_PROD" npx wrangler deploy --env production

# Record the rollback as a new deployment
gh api "repos/${REPO}/deployments" \
  -X POST \
  --field ref="$PREV_SHA" \
  --field environment=production \
  --field auto_merge=false \
  --field 'required_contexts[]=' \
  --field description="Rollback to $PREV_SHA"
```

## Anti-patterns

- **Omitting the `deployments: write` permission.** Without it, `gh api … deployments` returns
  `403 Resource not accessible by integration` and the step fails silently if `|| true` is used.
- **Creating a deployment with `auto_merge: true` on a branch that has pending checks.** GitHub
  will wait until the checks pass before creating the deployment record, blocking the pipeline.
  Set `auto_merge: false` and `required_contexts: []` when CI controls the deploy gate.
- **Never marking old deployments `inactive`.** The GitHub "Environments" tab lists every
  historical non-inactive deployment. After 50+ deploys, the UI becomes hard to read and the API
  response for `GET /deployments` grows unbounded.
- **Using the deployment `payload` field to store secrets.** Deployment payloads are readable by
  anyone with read access to the repository. Use it only for non-sensitive build metadata.

## Gotchas

- A deployment record cannot be deleted via API once created; it can only be marked `inactive`.
  Plan your environment naming carefully before deploying at scale.
- `required_contexts: []` bypasses required status checks at the deployment creation step. This
  is correct when the workflow already enforces status checks as a required job; if status checks
  are the only gate, remove this field.
- The `environment_url` field on a status is what appears as the "View deployment" button in the
  GitHub PR checks list. If omitted, no link is shown. Always set it to the live environment URL.
- GitHub imposes a rate limit of 100 deployments/hour per repository. High-frequency deploys
  (e.g. preview environments per commit) may hit this limit; batch or throttle in that case.

## Verification

```shell
# List all deployments for a given environment
gh api "repos/$GITHUB_REPOSITORY/deployments?environment=production&per_page=5" \
  --jq '.[] | {id, sha, created_at}'

# Check the latest status for a deployment
gh api "repos/$GITHUB_REPOSITORY/deployments/$DEPLOY_ID/statuses?per_page=1" \
  --jq '.[0] | {state, description, environment_url, created_at}'

# Verify the PR checks block shows the environment link
gh pr view $PR_NUMBER --json statusCheckRollup \
  --jq '.statusCheckRollup[] | select(.context == "production")'
```

## Related

- `github-deployment-api-workers-status-tracking.md`
- `github-commit-status-workers-deployment.md`
- `github-actions-deployment-gates.md`
- `github-environments-approval-gates.md`
- `github-actions-workers-canary-traffic-split.md`

## Sources

- <https://docs.github.com/en/rest/deployments/deployments>
- <https://docs.github.com/en/rest/deployments/statuses>
- <https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/using-environments-for-deployment>
- <https://developers.cloudflare.com/workers/wrangler/environments/>
